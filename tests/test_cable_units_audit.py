"""Cable lengths in feet or meters: what a round trip must never change.

  * the stock ladders show every number as stored, in their own unit, so
    opening and saving Preferences never rounds one (0.25 m stays 0.25 in a
    feet show);
  * a unit change relabels the pull sheet's edits BY NUMBER: m -> ft -> m
    (and ft -> m -> ft) keeps every edit key, and an edit on an engine row
    stays on it - never STALE, always exported;
  * the export dialog's unit select shows the show's unit after a change
    the user cancelled, even while it has focus;
  * the cable unit and the pull-sheet edits POST on ONE queue, so a slow
    stale POST can never land after a newer one.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_cable_units_audit.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_cable_units import _seed  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def _open_prefs(pg):
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")


def _ladders(pg):
    return pg.evaluate("() => [document.getElementById('pref-jumper-stock-ft').value,"
                       " document.getElementById('pref-jumper-stock-m').value]")


def _served_ladders(pg):
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    return [served['jumperStockFt'], served['jumperStockM']]


@pytest.mark.parametrize('unit', ['ft', 'm'])
def test_a_preferences_save_never_rounds_a_ladder(page, unit):
    """Whatever the open show's unit, each ladder shows its numbers as
    stored - 0.25 m and 2.125 ft, not 0.3 and 2.13 - and opening and
    saving Preferences writes the same ladders back."""
    pg, errors = page
    _seed(pg, unit)
    _open_prefs(pg)
    pg.fill('#pref-jumper-stock-ft', '2.125, 6, 10.55')
    pg.fill('#pref-jumper-stock-m', '0.25, 1.5, 4.125')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    assert _served_ladders(pg) == [[2.125, 6, 10.55], [0.25, 1.5, 4.125]]
    _open_prefs(pg)
    assert _ladders(pg) == ['2.125, 6, 10.55', '0.25, 1.5, 4.125']
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    assert _served_ladders(pg) == [[2.125, 6, 10.55], [0.25, 1.5, 4.125]]
    # the shipped ladders back for whatever runs next
    _open_prefs(pg)
    pg.fill('#pref-jumper-stock-ft', '3, 6, 10, 15, 25')
    pg.fill('#pref-jumper-stock-m', '1, 2, 3, 5, 10')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    assert errors == [], errors


# The edits' state: every key and added length, the STALE keys, and the
# exported Tru-1 rows that carry a note.
EDIT_STATE_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const store = app.project.pullSheetEdits || {positions: {}};
    const pos = Object.values(store.positions)[0] || {rows: [], added: []};
    const out = app.buildPullSheet();
    return {
        keys: pos.rows.map(r => r.key),
        added: pos.added.map(a => a.length),
        stale: app.pullSheetStaleEdits().map(s => s.key),
        exported: out.positions.flatMap(p => p.rows)
            .filter(r => r.notes === 'spare').map(r => [r.type, r.length]),
    };
}"""

# Circuit 2's cable to `ft`, then an edit on its engine row, a free row
# typed in the show's unit, and an edit on a row the show does not make.
EDIT_SEED_JS = """([ft, gone]) => {
    const app = window.app, wall = app.project.layers[0];
    app.setCircuitCable(wall, 2, {ft}, false);
    app.updateLayers([wall]);
    app._circuitTailCache = null;
    const list = app.buildPullList();
    const pos = list.positions.find(p => p.rows.some(r => r.type === 'Tru-1'
        && r.length === app.cableLengthText(ft)));
    const row = pos.rows.find(r => r.type === 'Tru-1' && r.length === app.cableLengthText(ft));
    const posKey = app.pullPositionKey(pos);
    app.setPullSheetRowEdit(posKey, app.pullRowKey(row), {notes: 'spare'}, row);
    app.setPullSheetRowEdit(posKey, 'Tru-1|' + app.cableLengthText(gone), {qty: 9});
    app._pullPositionEdits(posKey, true).added.push(
        {type: 'Spare Tru-1', length: app.cableLengthText(ft), qty: 1, label: '', notes: ''});
    return app.pullRowKey(row);
}"""


def test_m_to_ft_to_m_keeps_every_edit_key(page):
    """A meters show: an edit on the 7.62 m circuit cable, a free row of
    7.62 m and an edit on a 9.99 m row the show no longer makes. To feet
    they read 7.6' / 10', and back in meters every key is the one it
    started as - the edit is not STALE and it is exported."""
    pg, errors = page
    _seed(pg, 'm')
    key = pg.evaluate(EDIT_SEED_JS, [7.62, 9.99])
    assert key == 'Tru-1|7.62 m'
    start = pg.evaluate(EDIT_STATE_JS)
    assert sorted(start['keys']) == ['Tru-1|7.62 m', 'Tru-1|9.99 m'], start
    assert start['stale'] == ['Tru-1|9.99 m'] and start['exported'] == [['Tru-1', '7.62 m']], start

    pg.evaluate("() => window.app.setCableUnit('ft', false)")
    feet = pg.evaluate(EDIT_STATE_JS)
    assert sorted(feet['keys']) == ["Tru-1|10'", "Tru-1|7.6'"], feet
    assert feet['added'] == ["7.6'"] and feet['stale'] == ["Tru-1|10'"], feet
    assert feet['exported'] == [['Tru-1', "7.6'"]], feet

    pg.evaluate("() => window.app.setCableUnit('m', false)")
    back = pg.evaluate(EDIT_STATE_JS)
    assert sorted(back['keys']) == sorted(start['keys']), back
    assert back['added'] == ['7.62 m'], back
    assert back['stale'] == ['Tru-1|9.99 m'], back
    assert back['exported'] == [['Tru-1', '7.62 m']], back
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).pullSheetEdits")
    rows = [r['key'] for p in served['positions'].values() for r in p['rows']]
    assert sorted(rows) == sorted(start['keys']), served
    assert errors == [], errors


def test_ft_to_m_to_ft_keeps_every_edit_key(page):
    """A feet show whose circuit cable is 7.64 - printed 7.6' - carries an
    edit on that row. In meters the edit follows the row to 7.64 m (the
    number, not the print: never a STALE 7.6 m), and back in feet it is
    7.6' again, still exported."""
    pg, errors = page
    _seed(pg, 'ft')
    key = pg.evaluate(EDIT_SEED_JS, [7.64, 12.5])
    assert key == "Tru-1|7.6'"
    start = pg.evaluate(EDIT_STATE_JS)
    assert start['exported'] == [['Tru-1', "7.6'"]], start

    pg.evaluate("() => window.app.setCableUnit('m', false)")
    meters = pg.evaluate(EDIT_STATE_JS)
    assert sorted(meters['keys']) == ['Tru-1|12.5 m', 'Tru-1|7.64 m'], meters
    assert meters['stale'] == ['Tru-1|12.5 m'], meters
    assert meters['exported'] == [['Tru-1', '7.64 m']], meters

    pg.evaluate("() => window.app.setCableUnit('ft', false)")
    back = pg.evaluate(EDIT_STATE_JS)
    assert sorted(back['keys']) == sorted(start['keys']), back
    assert back['added'] == start['added'] == ["7.6'"], back
    assert back['stale'] == ["Tru-1|12.5'"], back
    assert back['exported'] == [['Tru-1', "7.6'"]], back
    assert errors == [], errors


def test_a_cancelled_unit_change_leaves_the_select_right(page):
    """The export dialog's unit select, focused, changed to meters on a
    show holding typed lengths: No keeps feet, and the select - still
    focused - says ft. Yes says m."""
    pg, errors = page
    _seed(pg, 'ft')
    pg.evaluate("() => window.app.openExportModal('pull-sheet')")
    pg.wait_for_timeout(200)
    pick = """() => { const s = [...document.querySelectorAll('select.cable-unit-select')]
                          .find(x => x.offsetParent !== null);
                      s.focus(); s.value = 'm'; s.dispatchEvent(new Event('change'));
                      return s.id; }"""
    state = """(id) => { const s = document.getElementById(id);
                         return [window.app.cableUnit(), s.value, document.activeElement === s]; }"""
    asked = []

    def no(d):
        asked.append(d.message)
        d.dismiss()
    pg.once('dialog', no)
    sid = pg.evaluate(pick)
    pg.wait_for_timeout(300)
    assert asked, 'the change did not ask'
    assert pg.evaluate(state, sid) == ['ft', 'ft', True]

    pg.once('dialog', lambda d: d.accept())
    pg.evaluate(pick)
    pg.wait_for_timeout(300)
    assert pg.evaluate(state, sid) == ['m', 'm', True]
    pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    assert errors == [], errors


def test_the_unit_and_the_edits_post_on_one_queue(page):
    """The cable unit's POST (with its relabelled edits) is slow; an edit
    and another edit follow it. The server must end on the LATEST edits:
    the slow POST lands first, then one POST with the newest state - never
    the stale one last."""
    pg, errors = page
    _seed(pg, 'ft')
    got = pg.evaluate("""async () => {
        const app = window.app, real = window.fetch;
        let release;
        const gate = new Promise(r => { release = r; });
        const landed = [];
        let held = false;
        window.fetch = async (url, opts) => {
            if (/\\/api\\/project$/.test(String(url)) && opts && opts.method === 'POST') {
                const body = JSON.parse(opts.body);
                if (!held) { held = true; await gate; }
                const resp = await real(url, opts);
                landed.push(body);
                return resp;
            }
            return real(url, opts);
        };
        const edits = (note) => ({positions: {q: {rows: [{key: "Tru-1|3'", notes: note}], added: []}}});
        try {
            app.project.pullSheetEdits = edits('A');
            const p1 = app._persistCableUnit(true);
            app.project.pullSheetEdits = edits('B');
            const p2 = app._persistPullSheetEdits();
            app.project.pullSheetEdits = edits('C');
            const p3 = app._persistPullSheetEdits();
            await new Promise(r => setTimeout(r, 300));
            release();
            await Promise.all([p1, p2, p3]);
            await new Promise(r => setTimeout(r, 200));
        } finally {
            window.fetch = real;
        }
        const srv = await (await real('/api/project')).json();
        delete app.project.pullSheetEdits;
        await app._persistPullSheetEdits();
        return {
            landed: landed.map(b => [Object.keys(b).sort(),
                                     b.pullSheetEdits ? b.pullSheetEdits.positions.q.rows[0].notes : null]),
            served: srv.pullSheetEdits.positions.q.rows[0].notes,
            unit: srv.cableUnit,
        };
    }""")
    assert got['served'] == 'C' and got['unit'] == 'ft', got
    assert got['landed'] == [[['cableUnit', 'pullSheetEdits'], 'A'], [['pullSheetEdits'], 'C']], got
    assert errors == [], errors
