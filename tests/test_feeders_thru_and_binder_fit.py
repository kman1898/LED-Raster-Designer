"""Feeders fed thru another distro, the services they count on, and the
binder's distro and pull tables printing whole (owner rulings, 2026-10-21).

  * THRU LOADS: a distro fed thru another (its feeder's `from`) counts on
    the SERVICE that one is on, never on the pass-through distro's legs.
    B fed thru A, A on HOUSE: B is in HOUSE's leg sums, its imbalance and
    its ratings added up, even though B was never put on HOUSE. The card's
    FEEDS chip says "SR 400 A thru SL"; the binder's Service sheet lists
    "SR · thru SL". B on a DIFFERENT service from A's is refused, saying
    why, whichever way round it is tried. "Thru" is offered only to a
    distro of the same system.
  * Removing a distro clears every other distro's feeder `from` naming it,
    so a later distro reusing the id is never read as the one fed thru.
  * The feeder length: "30m" in a feet show is accepted as 98.4 ft and
    said; text that is no length is refused, saying so, and the length
    that was there stays. The gear's first pick says "Fed from: none" on a
    distro with no service. A service is named "HOUSE · 400 A · ...".
  * A distro another distro is fed thru, or with a feeder set, is on the
    pull sheet (its Distro row and its feeder row) and its own pull list
    even with nothing plugged in; a distro with nothing at all stays off.
  * The binder: every distro's rating reads "400 A service · 120/208V 3φ",
    an old-style one too; the distro sheet's block is INPUT, its rows never
    print over each other and a number keeps its unit when a row wraps; a
    row with no length says "no length" on the pull pages and the distro
    Pull lists, and a feeder's "5-wire" rides with its type where there is
    no Notes column; the CABLE and NAME columns print whole or wrap, never
    cut; a meters show's map bracket "DISTRO 1-4 · 50 m+20 m" wraps rather
    than being cut.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_feeders_thru_and_binder_fit.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_services import (  # noqa: E402
    SEED_JS, US, SVC, HIST_JS, TOASTS_JS, _open, setup, read)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg, errors = _open(pw_browser, e2e_server)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def thru(i, name, src, rating=400, system='120/208', **kw):
    return dict(US(i, name, rating, system), feeder={'from': src}, **kw)


# Every sheet of the show, its texts in paint order, and the KV blocks the
# binder built ({title, pairs}).
BINDER_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        caught.push({ title, pairs: pairs.map(p => p.slice()) });
        return orig.apply(this, arguments);
    };
    // Letter: the size these sheets were read on (the dialog's select,
    // unsynced, said Letter until 1.6.0 read the saved size instead)
    const opts = Object.assign(app.readBinderOptions(),
        { sheet: 'letter', scope: { kind: 'show' }, hardware: true, pull: true, cover: false, wiring: false,
          sides: { power: true, data: false } });
    let plan;
    try { plan = app.planBinder(opts); } finally { app._bKvLines = orig; }
    const pages = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        pages.push({ title: plan[i].title, kind: plan[i].kind,
                     texts: r.record.ops.filter(o => o.op === 'text' && String(o.text).trim())
                              .map(o => ({ t: String(o.text), x: o.x, y: o.y, size: o.size })) });
    }
    return { pages, caught };
}"""


def cut(pages, kinds=None):
    """Every text the binder cut with an ellipsis (a folded run of names,
    "DISTRO 1-1 … 1-7", is not a cut)."""
    return [(p['title'], t['t']) for p in pages if kinds is None or p['kind'] in kinds
            for t in p['texts'] if t['t'].endswith('…')]


# ── thru loads on the service ─────────────────────────────────────────────

def test_a_distro_fed_thru_counts_on_the_service_not_the_pass_through(page):
    """SL on HOUSE with five full multis (165 A a leg); SR fed thru SL with
    five more, never put on HOUSE. HOUSE reads 330 A a leg; its ratings
    are SL's 400 A alone - SR draws thru SL's rating, not beside it (1.6.0
    beta.4 QA: "800 A on 400 A"). SL's own legs stay 165 A. The card's chip
    says SR is thru SL; the binder's Service sheet lists it."""
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), thru('d2', 'SR', 'd1')],
          services=[SVC(rating=400)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2']])
    out = read(pg)
    assert out['serviceIds'] == {'d1': 's1', 'd2': None}, out['serviceIds']
    assert out['distros']['d1']['legs'] == [165, 165, 165], out['distros']
    assert out['distros']['d2']['legs'] == [165, 165, 165], out['distros']
    s = out['services']['s1']
    assert s['distros'] == ['d1', 'd2'], s
    assert s['legs'] == [330, 330, 330] and s['over'], s
    assert s['ratingSum'] == 400 and not s['ratingsOver'], s
    assert s['chips'] == ['SL 400 A', 'SR 400 A thru SL'], s['chips']
    eff = pg.evaluate("() => window.app.getDistros().map(d => "
                      "(window.app.distroEffectiveService(d) || {}).id || null)")
    assert eff == ['s1', 's1'], eff
    # the binder's Service sheet: both distros, SR said to be thru SL
    b = pg.evaluate(BINDER_JS)
    sheet = next(p for p in b['pages'] if p['kind'] == 'service')
    texts = [t['t'] for t in sheet['texts']]
    assert 'SR · thru SL' in texts and 'SL' in texts, texts
    assert '2 DISTROS' in texts and '800 A' not in texts, texts
    svc = next(c for c in b['caught'] if c['title'] == 'Service')
    assert dict(svc['pairs'])['Distros'] == 'ratings 400 A on 400 A', svc
    # a thru distro of another system never counts
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), thru('d2', 'GEN', 'd1', 100, '120/240')],
          services=[SVC(rating=400)])
    assert read(pg)['services']['s1']['distros'] == ['d1']
    assert not errors, errors


def test_a_distro_fed_thru_another_on_a_different_service_is_refused(page):
    """SR fed thru SL (on HOUSE) cannot go on GEN; SR on HOUSE is fine. A
    distro on GEN cannot be fed thru SL; SL cannot go on HOUSE while SR,
    fed thru it, is on GEN. Each refusal says why and takes no history.
    Thru is offered only to a distro of the same system."""
    pg, errors = page
    two = [SVC(rating=400), SVC('s2', 'GEN', 400)]
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), thru('d2', 'SR', 'd1'), US('d3', 'FOH'),
                       US('d4', 'AUX', 100, '120/240')],
          services=two)
    n = len(pg.evaluate(HIST_JS))
    moved = pg.evaluate("() => window.app.setDistroService('d2', 's2')")
    why = ("SR is powered thru SL, which is on HOUSE. A distro powered thru another counts on that "
           "distro's service: power it from GEN directly, or leave it off a service.")
    assert moved is False and why in pg.evaluate(TOASTS_JS), pg.evaluate(TOASTS_JS)
    assert len(pg.evaluate(HIST_JS)) == n, 'a refusal took a history entry'
    assert pg.evaluate("() => window.app.setDistroService('d2', 's1')") is True
    # FOH on GEN, then fed thru SL: refused, its feeder untouched
    pg.evaluate("() => window.app.setDistroService('d3', 's2')")
    n = len(pg.evaluate(HIST_JS))
    fed = pg.evaluate("() => window.app.setDistroFeeder('d3', { from: 'd1' })")
    why = ("FOH is on GEN and SL draws from HOUSE. A distro powered thru another counts on that "
           "distro's service: take FOH off GEN first.")
    assert fed is False and why in pg.evaluate(TOASTS_JS), pg.evaluate(TOASTS_JS)
    assert pg.evaluate("() => window.app.getDistros().find(d => d.id === 'd3').feeder || null") is None
    assert len(pg.evaluate(HIST_JS)) == n
    # thru is same-system only
    sources = pg.evaluate("() => window.app.feederSources(window.app.getDistros()[0]).map(d => d.id)")
    assert 'd4' not in sources and 'd3' in sources, sources
    # the other way round: SR (thru SL) on GEN, SL on no service, then SL
    # put on HOUSE
    setup(pg, distros=[US('d1', 'SL'), thru('d2', 'SR', 'd1', serviceId='s2')], services=two)
    n = len(pg.evaluate(HIST_JS))
    moved = pg.evaluate("() => window.app.setDistroService('d1', 's1')")
    why = 'SR is powered thru SL and is on GEN. Take SR off GEN, or power it from its service, before putting SL on HOUSE.'
    assert moved is False and why in pg.evaluate(TOASTS_JS), pg.evaluate(TOASTS_JS)
    assert read(pg)['serviceIds'] == {'d1': None, 'd2': 's2'}
    assert len(pg.evaluate(HIST_JS)) == n
    assert not errors, errors


# ── the feeder ────────────────────────────────────────────────────────────

def test_removing_a_distro_clears_the_feeders_that_name_it(page):
    """SL fed thru SR; SR removed: SL's feeder forgets the `from` (and,
    empty, the key). A new distro then takes SR's old id and SL is not fed
    thru it. One undo brings SR back with SL fed thru it."""
    pg, errors = page
    setup(pg, distros=[thru('d1', 'SL', 'd2'), US('d2', 'SR')])
    out = pg.evaluate("""async () => {
        const app = window.app;
        const sl = () => app.getDistros().find(d => d.id === 'd1');
        app.removeDistro('d2');
        const after = sl().feeder || null;
        await app._distroPushQueue;
        const served = (await (await fetch('/api/project')).json()).distros.find(d => d.id === 'd1').feeder || null;
        const fresh = app.addDistro({ name: 'NEW' });
        const reads = app.distroFeeder(sl()).from;
        app.undo(); app.undo();
        return { after, served, freshId: fresh.id, reads: reads ? reads.id : null,
                 back: sl().feeder || null, ids: app.getDistros().map(d => d.id) };
    }""")
    assert out['after'] is None and out['served'] is None, out
    assert out['freshId'] == 'd2' and out['reads'] is None, out
    assert out['back'] == {'from': 'd2'} and out['ids'] == ['d1', 'd2'], out
    # a length stays when the `from` goes
    setup(pg, distros=[dict(US('d1', 'SL'), feeder={'ft': 100, 'from': 'd2'}), US('d2', 'SR')])
    assert pg.evaluate("() => { window.app.removeDistro('d2'); return window.app.getDistros()[0].feeder; }") \
        == {'ft': 100}
    assert not errors, errors


def test_a_feeder_length_in_the_other_unit_is_converted_and_junk_is_refused(page):
    """Feet show: "30m" is stored as 98.4 and said; "abc" is refused, saying
    so, and 98.4 stays; blank forgets it. A meters show reads "100 ft" as
    30.48 m. The gear's first pick says "Fed from: none" with no service,
    "from HOUSE" on one."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')], services=[SVC()])
    out = pg.evaluate("""() => {
        const app = window.app;
        const ft = () => (app.getDistros()[0].feeder || {}).ft ?? null;
        const n0 = app.history.length;
        const a = app.setDistroFeeder('d1', { ft: '30m' });
        const conv = ft();
        const b = app.setDistroFeeder('d1', { ft: 'abc' });
        const kept = ft();
        const steps = app.history.length - n0;
        const c = app.setDistroFeeder('d1', { ft: '' });
        const cleared = app.getDistros()[0].feeder || null;
        app.project.cableUnit = 'm';
        app.setDistroFeeder('d1', { ft: '100 ft' });
        const metric = ft();
        app.project.cableUnit = 'ft';
        return { a, conv, b, kept, steps, c, cleared, metric,
                 parse: ['30m', '30 m', '100', "100'", 'x', '', '0'].map(v => app.parseTypedCableLength(v)) };
    }""")
    assert out['a'] is True and out['conv'] == 98.4, out
    assert out['b'] is False and out['kept'] == 98.4 and out['steps'] == 1, out
    assert out['c'] is True and out['cleared'] is None, out
    assert out['metric'] == 30.48, out
    assert [(p['n'], p['from'], p['bad']) for p in out['parse']] == [
        (98.4, 'm', False), (98.4, 'm', False), (100, None, False), (100, None, False),
        (None, None, True), (None, None, False), (None, None, False)], out['parse']
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t.startswith('30m is 98.4 ft in this feet show.') for t in toasts), toasts
    assert any(t.startswith('"abc" is not a length.') for t in toasts), toasts
    # the picker's first option names where it is fed from
    labels = pg.evaluate("""() => {
        const app = window.app;
        const first = () => {
            const wrap = document.createElement('div');
            app._buildDistroFeederRow(app.getDistros()[0], wrap);
            return wrap.querySelector('select option').textContent;
        };
        const none = first();
        app.getDistros()[0].serviceId = 's1';
        const on = first();
        delete app.getDistros()[0].serviceId;
        return [none, on, app.serviceLabel(app.serviceById('s1'))];
    }""")
    assert labels == ['Powered from: none', 'from HOUSE', 'HOUSE · 400 A · 120/208V 3φ'], labels
    assert not errors, errors


# ── the pull sheet ────────────────────────────────────────────────────────

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const l = JSON.parse(JSON.stringify(app.buildPullList()));
    const rows = l.positions.flatMap(p => p.rows.map(r => [p.name, r.type, r.length, r.qty, r.label, r.notes]));
    return { rows, hw: l.hardware.filter(h => h.kind === 'distro')
                         .map(h => [h.id, h.rows.map(r => [r.type, r.length, r.label, r.notes])]) };
}"""


def test_a_pass_through_or_fed_distro_is_listed_with_nothing_plugged_in(page):
    """SL feeds WALL A; FOH has nothing plugged in but MON is fed thru it;
    MON has nothing plugged in but a feeder set; SPARE has nothing at all.
    FOH and MON each get their Distro row and feeder row on the pull sheet
    and their own pull list; SPARE stays off."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), US('d2', 'FOH'), dict(thru('d3', 'MON', 'd2'), input='cam400'),
                       US('d4', 'SPARE')],
          assign=[['WALL A', 0, 1, 'd1']])
    out = pg.evaluate(LIST_JS)
    labels = {n for r in out['rows'] for n in r[4].split(', ')}
    assert {'SL', 'FOH', 'MON'} <= labels and 'SPARE' not in labels, out['rows']
    named = sorted(n for r in out['rows'] if r[1] == 'Distro' for n in r[4].split(', '))
    assert named == ['FOH', 'MON', 'SL'], out['rows']
    hw = dict(out['hw'])
    assert set(hw) == {'d1', 'd2', 'd3'}, hw
    assert ['Distro', 'EA', 'FOH', ''] in hw['d2'] and ['Power in', '', 'FOH', 'no length'] in hw['d2'], hw['d2']
    assert ['400 A cam set', '', 'MON', '5-wire · no length'] in hw['d3'], hw['d3']
    # the pass-through's row lands where a screen is: WALL A's position
    assert {r[0] for r in out['rows'] if r[4] in ('FOH', 'MON')} == {'WALL A'}, out['rows']
    assert not errors, errors


# ── the binder ────────────────────────────────────────────────────────────

def test_binder_cells_rating_line_and_kv_words(page):
    """The pull tables' cells: "no length" after any separator, "5-wire"
    with the type, a blank only for an empty cell. Every rating line by its
    service size, an old-style distro's too. A KV row never wraps between
    a number and its unit, nor inside "50 m+20 m"; a words cell neither."""
    pg, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        return {
            cells: [
                app._bPullCableCells({ type: '400 A cam set', length: '', notes: '5-wire · no length' }),
                app._bPullCableCells({ type: '400 A cam set', length: "150'", notes: '5-wire' }),
                app._bPullCableCells({ type: 'Multi', length: '', notes: 'no length' }),
                app._bPullCableCells({ type: 'TAC 4', length: '', notes: 'spare; no length' }),
                app._bPullCableCells({ type: 'Spare Widget', length: '', notes: '' }),
            ],
            legacy: app._bDistroRatingText({ ratingA: 400, voltage: 208, phase: 3 }),
            words: app._bKvWords("SL, cam thru · 400 A cam set 50 m+20 m · limit 320 A (80% of 400 A)"),
            pieces: app._bCellPieces('400 A cam set · 5-wire 30 m+10 m', true),
        };
    }""")
    assert out['cells'] == [['400 A cam set · 5-wire', 'no length'], ['400 A cam set · 5-wire', "150'"],
                            ['Multi', 'no length'], ['TAC 4', 'no length'], ['Spare Widget', '']], out['cells']
    assert out['legacy'] == '400 A service · 120/208V 3φ', out['legacy']
    # (a " · " rides at the end of the word before it - 2026-10-22)
    assert '400 A' in out['words'] and '50 m+20 m ·' in out['words'] and '320 A' in out['words'], out['words']
    assert not [w for w in out['words'] if w.startswith('·')], out['words']
    assert '(80%' in out['words'] and 'A)' not in out['words'], out['words']
    assert out['pieces'] == ['400 A ', 'cam ', 'set · ', '5-wire ', '30 m+10 m'], out['pieces']
    assert not errors, errors


def test_the_kv_rows_never_draw_past_their_height(page):
    """A long "Fed from" measured at one width and drawn where the measure
    context was left in a larger bold font, and in a column narrower than
    it was measured at: every line it draws stays inside its own row."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')])
    out = pg.evaluate("""() => {
        const app = window.app;
        const book = app._binderBook(app.readBinderOptions(), { dry: true });
        book.ctx = book.ctx || app._bDryCtx(book.measureCtx);
        const pairs = [['Powered from', 'SR DISTRO B, cam thru · 400 A cam set 100\\'+25\\' · '
                        + 'HOUSE · 600 A · 120/208V 3φ · 100% rated · and some more words to wrap'],
                       ['Load', 'X 87.1 · Y 81.4 · Z 81.4 A']];
        const lines = app._bKvLines(book, 'Distro', pairs);
        const drawn = [];
        const orig = app._bText;
        app._bText = function (bk, text, x, y, o) {
            drawn.push({ text: String(text), y });
            return orig.apply(this, arguments);
        };
        const res = [];
        try {
            for (const w of [700, 520]) {
                let y0 = 0;
                for (const line of lines) {
                    book.measureCtx.font = app._bFont(30, 700);
                    drawn.length = 0;
                    line.draw(book.ctx, 0, y0, w);
                    res.push({ w, h: line.h, ys: drawn.map(d => d.y - y0) });
                    y0 += line.h;
                }
            }
        } finally { app._bText = orig; }
        return res;
    }""")
    for r in out:
        assert all(y <= r['h'] for y in r['ys']), out
    fed = [r for r in out if r['w'] == 700][1]
    assert fed['h'] > 38 and len(fed['ys']) >= 3, fed
    assert not errors, errors


def test_the_distro_sheet_prints_input_names_whole_and_no_length(page):
    """SR DISTRO B feeds WALL A and WALL B; FOH is fed thru it with a 400 A
    cam input and no length. The distro sheet: an INPUT block (no SERVICE),
    its Rating "400 A service · 120/208V 3φ", its table's names never cut;
    FOH's Pull list says "400 A cam set · 5-wire" and "no length"; no pull
    page cuts a cable, a length or a name."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SR DISTRO B'), dict(thru('d2', 'FOH', 'd1'), input='cam400')],
          assign=[['WALL A', 0, 9, 'd1'], ['WALL B', 0, 0, 'd1']])
    b = pg.evaluate(BINDER_JS)
    titles = {c['title'] for c in b['caught']}
    assert 'Distro' in titles and 'Service' not in titles, titles
    blocks = [dict(c['pairs']) for c in b['caught'] if c['title'] == 'Distro']
    assert [p['Rating'] for p in blocks] == ['400 A service · 120/208V 3φ'] * 2, blocks
    assert blocks[1]['Powered from'] == 'SR DISTRO B, cam thru · 400 A cam set, no length', blocks[1]
    sheets = [p for p in b['pages'] if p['kind'] == 'distro']
    texts = [t['t'] for p in sheets for t in p['texts']]
    assert 'DISTRO' in texts and 'SERVICE' not in texts, texts
    assert '400 A cam set · 5-wire' in texts and 'no length' in texts, texts
    assert cut(b['pages'], ('distro', 'pull', 'totals')) == [], cut(b['pages'], ('distro', 'pull', 'totals'))
    # the box names whole: on one line, or wrapped with every word there
    names = [t['t'] for t in sheets[0]['texts']]
    assert any(n.startswith('SR DISTRO B') for n in names), names
    assert not errors, errors


def test_a_meters_bracket_tag_wraps_rather_than_cut(page):
    """A meters show with 50 m and 20 m in stock: WALL B's one multi has a
    70 m home run, and "UPSTAGE CENTER DISTRO1 · 50 m+20 m" is longer than
    its bracket - so it prints as the name and the length on two lines,
    the length never split and nothing cut (it was "… · 50 m+…")."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'UPSTAGE CENTER DISTRO')], assign=[['WALL B', 0, 0, 'd1']])
    b = pg.evaluate("""(binder) => {
        const app = window.app;
        app.project.cableUnit = 'm';
        app.project.cableStock = { perKind: false, ft: { all: [] }, m: { all: [50, 20] } };
        const l = app.project.layers.find(x => x.name === 'WALL B');
        l.powerSocaLengths = { [app.getSocaPlan(l)[0].soca]: 70 };
        try { return eval(binder)(); } finally {
            delete app.project.cableStock; app.project.cableUnit = 'ft'; l.powerSocaLengths = {};
        }
    }""", BINDER_JS)
    page_b = next(p for p in b['pages'] if p['kind'] == 'power' and 'WALL B' in p['title'])
    texts = [t['t'] for t in page_b['texts']]
    assert 'UPSTAGE CENTER DISTRO1' in texts and '50 m+20 m' in texts, texts
    assert 'UPSTAGE CENTER DISTRO1 · 50 m+20 m' not in texts, texts
    # (the circuit table's own long circuit names are another column's)
    assert not [t for t in texts if t.endswith('…') and 'm+' in t], texts
    assert not errors, errors
