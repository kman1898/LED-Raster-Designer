"""Old pull-sheet edits follow the renamed rows, and every paper labels a
distro box the same way (owner rulings, 2026-10-21).

  * An edit saved by 1.5.2 or a 1.5.3 beta is keyed on the row's old name.
    Where the new name depends on the position's rows, the edit is read
    against them, so a hide or a count is never lost:
      - an old data word ("Ether-con|25'", "Data Cable|25'", "Barrel|EA")
        is the position's Cat6 row, else its etherCON row;
      - an old snake key with no snake on it ("Ether-con Snake|100'",
        "Cat6 Snake|100'", "Snake|100'") is the position's ONE snake row
        of that type and length; with several it stays stale;
      - "Tru-1 Power Jump|6'" is the TRUE1 jumper row, else the powerCON
        one of that length;
      - "Edison 2fer|EA", "L6-20 3fer|EA" ... are "<panel input> Nfer";
      - a 1.5.2 extension printed as "Ether-con|25'" stays on the home run.
    The writers (an edit, a hide, a restore, a reset) find the old edit
    the same way, so it takes the new key instead of leaving a twin.
  * The breakout a second screen on a shared multi takes is labelled by
    the box's own label, like its Multi and first Breakout.
  * Two boxes typed the same name read "-1" / "-2" on the binder's
    brackets (the per-screen boxes) and the map's band, as on the pull
    sheet.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_pull_old_edits.py -q --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_pull_list import SEED_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    pg.wait_for_timeout(1500)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    yield pg, ids, errors
    context.close()


@pytest.fixture()
def seeded(page):
    """The seeded page with no edits left behind."""
    yield page
    page[0].evaluate("""() => {
        const app = window.app;
        delete app.project.pullSheetEdits;
        app._circuitTailCache = null;
    }""")


# ── the rule, on the keys alone ──────────────────────────────────────────

RESOLVE_CASES = [
    # an old data word: Cat6, else etherCON, else stale on Cat6; where the
    # old row is BOTH now it answers to neither (owner, 2026-10-22: a count
    # goes stale - a hide covers both, test_paper_rulings_1022.py)
    ("Ether-con|25'", ["Cat6|25'"], "Cat6|25'"),
    ("Ether-con|25'", ["etherCON|25'"], "etherCON|25'"),
    ("Ether-con|25'", ["Cat6|25'", "etherCON|25'"], "Ether-con|25'"),
    ("Ether-con|25'", ["Cat6|50'"], "Cat6|25'"),
    ("Data Cable|25'", ["etherCON|25'"], "etherCON|25'"),
    ('Ether-con Barrel|EA', ['etherCON Barrel|EA'], 'etherCON Barrel|EA'),
    ('Barrel|EA', ['Cat6 Barrel|EA', 'etherCON Barrel|EA'], 'Barrel|EA'),
    # a snake with no snake id: the one snake of that type and length
    ("Ether-con Snake|100'", ["Cat6 Snake|100'|snake:a"], "Cat6 Snake|100'|snake:a"),
    ("Ether-con Snake|100'", ["etherCON Snake|100'|snake:b"], "etherCON Snake|100'|snake:b"),
    ("Snake|100'", ["Cat6 Snake|100'|snake:a", "Cat6 Snake|50'|snake:c"], "Cat6 Snake|100'|snake:a"),
    ("Cat6 Snake|100'", ["Cat6 Snake|100'|snake:a"], "Cat6 Snake|100'|snake:a"),
    ("Cat6 Snake|100'", ["etherCON Snake|100'|snake:a"], "Cat6 Snake|100'"),
    ("Ether-con Snake|100'", ["Cat6 Snake|100'|snake:a", "Cat6 Snake|100'|snake:b"], "Cat6 Snake|100'"),
    ("Ether-con Snake|100'", ["Cat6 Snake|50'|snake:a"], "Cat6 Snake|100'"),
    # the old power jumper: TRUE1, else powerCON, its member kept; both
    # there, neither
    ("Tru-1 Power Jump|6'", ["powerCON Power Jump|6'"], "powerCON Power Jump|6'"),
    ("Tru-1 Power Jump|6'", ["TRUE1 Power Jump|6'", "powerCON Power Jump|6'"], "Tru-1 Power Jump|6'"),
    ("Tru-1 Power Jump|6'|WALL-B", ["powerCON Power Jump|6'|WALL-B"], "powerCON Power Jump|6'|WALL-B"),
    ("Tru-1 Power Jump|6'", ["powerCON Power Jump|2'"], "TRUE1 Power Jump|6'"),
    # splitters: the panel input the position has
    ('Edison 2fer|EA', ['powerCON 2fer|EA'], 'powerCON 2fer|EA'),
    ('Edison 2fer|EA', ['TRUE1 2fer|EA'], 'TRUE1 2fer|EA'),
    ('L6-20 3fer|EA', ['powerCON 3fer|EA', 'TRUE1 2fer|EA'], 'powerCON 3fer|EA'),
    ('Tru-1 2fer|EA', ['powerCON 2fer|EA'], 'powerCON 2fer|EA'),
    ('Edison 2fer|EA', [], 'Edison 2fer|EA'),
    # keys that need no rows are pullEditKey's
    ("Multi|100'", ["Multi|100'"], "Multi|100'"),
    ('TRUE1 2fer|EA', ['powerCON 2fer|EA'], 'TRUE1 2fer|EA'),
    ('Tessera XD|EA', ['XD|EA'], 'XD|EA'),
    ("Cat6 Snake|100'|snake:a", ["Cat6 Snake|100'|snake:b"], "Cat6 Snake|100'|snake:a"),
]


def test_an_old_key_is_read_against_its_positions_rows(seeded):
    pg, _ids, errors = seeded
    got = pg.evaluate("""(cases) => cases.map(([key, live]) =>
        window.app._pullResolveEditKey(key, new Set(live)))""",
                      [[k, live] for k, live, _ in RESOLVE_CASES])
    bad = [(k, live, g, want) for (k, live, want), g in zip(RESOLVE_CASES, got) if g != want]
    assert not bad, bad
    assert errors == [], errors


# ── the rule, on a show ──────────────────────────────────────────────────

POS_JS = """(name) => {
    const app = window.app;
    app._circuitTailCache = null;
    const pos = app.buildPullList().positions.find(p => p.name === name);
    return pos ? app.pullPositionKey(pos) : null;
}"""


def test_old_data_edits_land_on_the_snake_cat6_and_ethercon_rows(seeded):
    """SR Beach's one snake takes "Ether-con Snake|100'"; CENTER's 50'
    cable takes "Ether-con|50'" as its Cat6 row and, once its plug is
    etherCON, as its etherCON row. Nothing is stale, and an edit on the
    row moves the old key onto the new one."""
    pg, ids, errors = seeded
    g1, center = pg.evaluate(POS_JS, 'SR Beach'), pg.evaluate(POS_JS, 'CENTER')
    out = pg.evaluate("""async ([ids, g1, center]) => {
        const app = window.app;
        const sock = String(ids.sockets['CENTER'][0]);
        const card = async (portCables) => {
            await fetch(`/api/processors/${ids.procId}/cards/${ids.cardId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ portCables })});
            await app.refreshProcessors();
            app._circuitTailCache = null;
        };
        app.project.pullSheetEdits = { positions: {
            [g1]: { rows: [{ key: "Ether-con Snake|100'", notes: 'old snake' }], added: [] },
            [center]: { rows: [{ key: "Ether-con|50'", qty: 3 }], added: [] },
        } };
        const read = () => {
            app._circuitTailCache = null;
            const sheet = app.buildPullSheet();
            const pos = (k) => sheet.positions.find(p => app.pullPositionKey(p) === k).rows;
            return {
                snake: pos(g1).filter(r => /Snake$/.test(r.type)).map(r => [r.type, r.length, r.notes]),
                center: pos(center).filter(r => r.length === "50'").map(r => [r.type, r.qty]),
                stale: app.pullSheetStaleEdits().map(s => s.key),
            };
        };
        const cat6 = read();
        await card({ [sock]: { ft: 50, connector: 'ethercon' } });
        const ethercon = read();
        // the editor's write: the old edit takes the row's key, no twin
        app.setPullSheetRowEdit(center, "etherCON|50'", { qty: 4 });
        const stored = JSON.parse(JSON.stringify(app.project.pullSheetEdits.positions[center].rows));
        // a reset forgets the old snake edit
        app._circuitTailCache = null;
        const snakeKey = app.pullRowKey(app.buildPullList().positions
            .find(p => app.pullPositionKey(p) === g1).rows.find(r => /Snake$/.test(r.type)));
        const reset = app.resetPullSheetRow(g1, snakeKey);
        const left = app.project.pullSheetEdits.positions[g1] || null;
        await card({ [sock]: { ft: 50 } });
        delete app.project.pullSheetEdits;
        return { cat6, ethercon, stored, reset, left };
    }""", [ids, g1, center])
    assert out['cat6']['snake'] == [['Cat6 Snake', "100'", 'old snake']], out
    assert out['cat6']['center'] == [['Cat6', 3]], out
    assert out['cat6']['stale'] == [], out
    assert out['ethercon']['center'] == [['etherCON', 3]], out
    assert out['ethercon']['stale'] == [], out
    assert out['stored'] == [{'key': "etherCON|50'", 'qty': 4}], out
    assert out['reset'] is True and out['left'] is None, out
    assert errors == [], errors


def test_old_jumper_and_splitter_edits_follow_the_panel_input(seeded):
    """WALL-B made a powerCON screen: its "Tru-1 Power Jump" edit lands on
    its powerCON jumper row. CENTER's "Edison 2fer|EA" is its TRUE1 2fer,
    and its powerCON 2fer once its panel input is powerCON."""
    pg, ids, errors = seeded
    g1, center = pg.evaluate(POS_JS, 'SR Beach'), pg.evaluate(POS_JS, 'CENTER')
    out = pg.evaluate("""([ids, g1, center]) => {
        const app = window.app;
        const B = app.project.layers.find(l => l.id === ids.b);
        const C = app.project.layers.find(l => l.id === ids.c);
        const keep = { b: B.powerBreakoutType, c: C.powerPanelInput };
        B.powerBreakoutType = 'soca-powercon';
        app._circuitTailCache = null;
        const jump = app.buildPullList().positions.find(p => app.pullPositionKey(p) === g1)
            .rows.find(r => r.type === 'powerCON Power Jump' && r.split === 'WALL-B');
        const oldJump = `Tru-1 Power Jump|${jump.length}|WALL-B`;
        app.project.pullSheetEdits = { positions: {
            [g1]: { rows: [{ key: oldJump, notes: 'old jumper' }], added: [] },
            [center]: { rows: [{ key: 'Edison 2fer|EA', qty: 5 }], added: [] },
        } };
        const read = () => {
            app._circuitTailCache = null;
            const sheet = app.buildPullSheet();
            const pos = (k) => sheet.positions.find(p => app.pullPositionKey(p) === k).rows;
            return {
                jump: pos(g1).filter(r => /Power Jump$/.test(r.type) && r.notes)
                    .map(r => [r.type, r.split, r.notes]),
                fer: pos(center).filter(r => /fer$/.test(r.type)).map(r => [r.type, r.qty]),
                stale: app.pullSheetStaleEdits().map(s => s.key),
            };
        };
        const true1 = read();
        C.powerPanelInput = 'powercon';
        const powercon = read();
        // a hide found through the old key: no second edit is stored
        app.removePullSheetRow(center, 'powerCON 2fer|EA');
        const stored = JSON.parse(JSON.stringify(app.project.pullSheetEdits.positions[center].rows));
        B.powerBreakoutType = keep.b;
        if (keep.c === undefined) delete C.powerPanelInput; else C.powerPanelInput = keep.c;
        delete app.project.pullSheetEdits;
        app._circuitTailCache = null;
        return { true1, powercon, stored };
    }""", [ids, g1, center])
    assert out['true1']['jump'] == [['powerCON Power Jump', 'WALL-B', 'old jumper']], out
    assert out['true1']['fer'] == [['TRUE1 2fer', 5]], out
    assert out['true1']['stale'] == [], out
    assert out['powercon']['fer'] == [['powerCON 2fer', 5]], out
    assert out['powercon']['stale'] == [], out
    assert out['stored'] == [{'key': 'powerCON 2fer|EA', 'qty': 5, 'removed': True}], out
    assert errors == [], errors


# ── a box's label on every paper ─────────────────────────────────────────

def test_a_shared_multis_second_breakout_wears_the_boxs_label(seeded):
    """WALL-A's box 1 typed MAIN; WALL-B (a powerCON screen) moved onto it:
    the Multi, the TRUE1 Breakout AND the powerCON Breakout read MAIN -
    never "SR1", the distro's name glued to the number."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const A = app.project.layers.find(l => l.id === ids.a);
        const B = app.project.layers.find(l => l.id === ids.b);
        const keep = { names: A.powerSocaNames, num: B.powerSocaNumber, brk: B.powerBreakoutType };
        A.powerSocaNames = { 1: 'MAIN' };
        B.powerSocaNumber = { 1: 1 };
        B.powerBreakoutType = 'soca-powercon';
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const rows = list.positions.flatMap(p => p.rows)
            .filter(r => r.type === 'Multi' || /Breakout$/.test(r.type))
            .map(r => [r.type, r.label]);
        const hw = list.hardware.find(h => h.kind === 'distro').rows
            .filter(r => /Breakout$/.test(r.type)).map(r => [r.type, r.label]);
        if (keep.names === undefined) delete A.powerSocaNames; else A.powerSocaNames = keep.names;
        B.powerSocaNumber = keep.num;
        B.powerBreakoutType = keep.brk;
        app._circuitTailCache = null;
        return { rows, hw };
    }""", ids)
    assert sorted(out['rows']) == [['Multi', 'MAIN'], ['TRUE1 Breakout', 'MAIN'],
                                   ['powerCON Breakout', 'MAIN']], out
    assert sorted(out['hw']) == [['TRUE1 Breakout', 'MAIN'], ['powerCON Breakout', 'MAIN']], out
    assert errors == [], errors


def test_two_boxes_of_one_name_read_minus_one_and_two_on_every_paper(seeded):
    """Both walls' boxes typed MAIN: the per-screen boxes the binder's
    brackets print and the map's band read MAIN-1 and MAIN-2."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const r = window.canvasRenderer;
        const A = app.project.layers.find(l => l.id === ids.a);
        const B = app.project.layers.find(l => l.id === ids.b);
        A.powerSocaNames = { 1: 'MAIN' };
        B.powerSocaNames = { 1: 'MAIN' };
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const boxes = [A, B].map(l => list.byScreen[l.id].boxes.map(b => b.name));
        const bands = [];
        const orig = r._fillText;
        r._fillText = function (text, ...rest) { bands.push(String(text)); return orig.call(this, text, ...rest); };
        try {
            for (const l of [A, B]) r.renderSocaBrackets(l);
        } finally { r._fillText = orig; }
        delete A.powerSocaNames; delete B.powerSocaNames;
        app._circuitTailCache = null;
        return { boxes, bands: bands.filter(t => t.startsWith('MAIN')) };
    }""", ids)
    assert out['boxes'] == [['MAIN-1'], ['MAIN-2']], out
    assert [b.split(' · ')[0] for b in out['bands']] == ['MAIN-1', 'MAIN-2'], out
    assert errors == [], errors
