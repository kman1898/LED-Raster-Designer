"""Two more ways to switch the OPEN show's cable unit (app-cable-units.js).

Owner ruling, 2026-10-17 - Preferences set to meters "for the show" left the
sidebar jumpers reading ft, because the preference only sets what a NEW show
starts in. Both of these, then:

  1. Saving Preferences with a changed Cable lengths unit that is not the
     open show's asks once - "Also switch the open show to meters?", the
     typed-lengths note folded into the same question. Yes switches the show
     the export dialog's way; No changes only the preference. A show that
     already reads that unit is asked nothing.
  2. An ft / m select beside the jumper fields in the Data and Power
     sidebars, the export dialog's own control (setCableUnit with the usual
     typed-lengths question).

Every unit control - both sidebar selects, the export dialog's two, every
data-cable-unit label - reads the show's unit, through undo and redo too.
Each unit control is a dropdown that LOOKS like one: theme.css's chevron is
on it, and nothing clips it.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_show_unit_switch.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

SIDEBAR_SELECTS = ('#data-jump-unit', '#power-jump-unit')
EXPORT_SELECTS = ('#export-pull-sheet-cable-unit', '#export-binder-cable-unit')
UNIT_SELECTS = SIDEBAR_SELECTS + EXPORT_SELECTS


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    # Every dialog is answered from `answer` and recorded in `asked`.
    state = {'asked': [], 'answer': False}

    def on_dialog(dialog):
        state['asked'].append(dialog.message)
        if state['answer']:
            dialog.accept()
        else:
            dialog.dismiss()
    pg.on('dialog', on_dialog)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " && window.app.project && window.app.project.layers"
                         " && window.app.project.layers.length > 0", timeout=15000)
    yield pg, errors, state
    context.close()


def _mode(pg, mode):
    pg.locator(f'[data-mode="{mode}"]').click()
    pg.wait_for_function("(m) => window.canvasRenderer && window.canvasRenderer.viewMode === m",
                         arg=mode)


def _setup(pg, state, show='ft', pref='ft', typed=False):
    """The show in `show` with an edit on it (so a Preferences save never
    takes it for the untouched startup show), the preference in `pref`,
    the first screen selected; with `typed`, its data jumper V holds 2."""
    pg.evaluate("""async ([show, pref, typed]) => {
        const app = window.app;
        const prefs = {...app.getPreferences(), cableUnit: pref};
        app._serverPreferences = prefs;
        localStorage.setItem('appPreferences', JSON.stringify(prefs));
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(prefs)});
        // The whole project replaced, the way a file open does: the server
        // holds exactly this, typed jumper lengths or none.
        const p = JSON.parse(JSON.stringify(app.project));
        p.layers = p.layers.slice(0, 1);
        p.layers[0].locked = false;
        for (const k of ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']) delete p.layers[0][k];
        if (typed) p.layers[0].dataJumpV = 2;
        p.cableUnit = show;
        delete p.pullSheetEdits;
        app.project = await (await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)})).json();
        app.dedupeProjectLayers('unit_setup');
        app.selectLayer(app.project.layers[0]);
        app.resetHistory('Unit Seed');
        app.saveState('Unit Seed Edit');
        app.updateUI();
    }""", [show, pref, typed])
    state['asked'].clear()
    state['answer'] = False
    _wait_server_unit(pg, show)
    _wait_all_read(pg, show)


def _server_unit(pg):
    return pg.evaluate("async () => (await (await fetch('/api/project')).json()).cableUnit || 'ft'")


def _wait_server_unit(pg, unit):
    got = settled(pg, lambda: _server_unit(pg), lambda v: v == unit)
    assert got == unit, f'the server project reads {got!r}, not {unit!r}'


def _controls(pg):
    """What every unit control and label on the page says."""
    return pg.evaluate("""(sels) => ({
        show: window.app.cableUnit(),
        selects: Object.fromEntries(sels.map(s => [s, document.querySelector(s).value])),
        labels: [...new Set([...document.querySelectorAll('[data-cable-unit]')].map(e => e.textContent))],
        jumperLabels: ['#data-jump-v', '#data-jump-h', '#power-jump-v', '#power-jump-h']
            .map(s => document.querySelector(s).nextElementSibling.textContent),
    })""", list(UNIT_SELECTS))


def _all_read(c, unit):
    return (c['show'] == unit and set(c['selects'].values()) == {unit}
            and c['labels'] == [unit] and set(c['jumperLabels']) == {unit})


def _wait_all_read(pg, unit):
    c = settled(pg, lambda: _controls(pg), lambda v: _all_read(v, unit))
    assert _all_read(c, unit), (unit, c)


def _save_preferences_with(pg, unit):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_function("() => getComputedStyle(document.getElementById('preferences-modal')).display !== 'none'")
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="pull"]').click()
    pg.locator('#pref-cable-unit').select_option(unit)
    pg.locator('#preferences-save').click()
    pg.wait_for_function("() => getComputedStyle(document.getElementById('preferences-modal')).display === 'none'")


def _served_pref_unit(pg):
    return pg.evaluate("async () => (await (await fetch('/api/preferences')).json()).cableUnit")


# ── 1. Preferences asks about the open show ──────────────────────────────

def test_a_preferences_save_asks_once_and_yes_switches_the_show(page):
    pg, errors, state = page
    _mode(pg, 'data-flow')
    _setup(pg, state, show='ft', pref='ft')
    state['answer'] = True
    _save_preferences_with(pg, 'm')
    assert state['asked'] == ['Also switch the open show to meters?'], state['asked']
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    assert _served_pref_unit(pg) == 'm'
    assert errors == [], errors


def test_no_changes_only_the_preference(page):
    pg, errors, state = page
    _setup(pg, state, show='ft', pref='ft')
    _save_preferences_with(pg, 'm')
    assert state['asked'] == ['Also switch the open show to meters?'], state['asked']
    assert settled(pg, lambda: _served_pref_unit(pg), lambda v: v == 'm') == 'm'
    _wait_all_read(pg, 'ft')
    assert _server_unit(pg) == 'ft'
    assert errors == [], errors


def test_nothing_is_asked_when_the_show_already_reads_the_unit(page):
    pg, errors, state = page
    _setup(pg, state, show='m', pref='ft')
    _save_preferences_with(pg, 'm')
    assert settled(pg, lambda: _served_pref_unit(pg), lambda v: v == 'm') == 'm'
    assert state['asked'] == [], state['asked']
    # nor when the preference did not change at all
    _setup(pg, state, show='ft', pref='m')
    _save_preferences_with(pg, 'm')
    assert state['asked'] == [], state['asked']
    _wait_all_read(pg, 'ft')
    assert errors == [], errors


def test_the_typed_lengths_note_rides_the_one_preferences_question(page):
    pg, errors, state = page
    _setup(pg, state, show='ft', pref='ft', typed=True)
    state['answer'] = True
    _save_preferences_with(pg, 'm')
    assert len(state['asked']) == 1, state['asked']
    q = state['asked'][0]
    assert q.startswith('Also switch the open show to meters?'), q
    assert '1 cable length already typed keep their numbers: 25 ft becomes 25 m.' in q, q
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    # the typed number keeps (relabelled, not converted)
    assert pg.evaluate("() => window.app.project.layers[0].dataJumpV") == 2
    assert errors == [], errors


# ── 2. The sidebar switch ────────────────────────────────────────────────

@pytest.mark.parametrize('mode,sel', [('data-flow', '#data-jump-unit'),
                                      ('power', '#power-jump-unit')])
def test_the_sidebar_switch_changes_the_show(page, mode, sel):
    pg, errors, state = page
    _mode(pg, mode)
    _setup(pg, state, show='ft', pref='ft')
    pg.locator(sel).select_option('m')
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    assert state['asked'] == [], 'no typed lengths: nothing to ask'
    pg.locator(sel).select_option('ft')
    _wait_all_read(pg, 'ft')
    _wait_server_unit(pg, 'ft')
    assert errors == [], errors


def test_the_sidebar_switch_asks_when_lengths_are_typed(page):
    pg, errors, state = page
    _mode(pg, 'power')
    _setup(pg, state, show='ft', pref='ft', typed=True)
    pg.locator('#power-jump-unit').select_option('m')
    assert len(state['asked']) == 1 and state['asked'][0].startswith(
        "Change this show's cable lengths to meters?"), state['asked']
    # No: the switch goes back and nothing changed
    _wait_all_read(pg, 'ft')
    assert _server_unit(pg) == 'ft'
    state['answer'] = True
    pg.locator('#power-jump-unit').select_option('m')
    assert len(state['asked']) == 2, state['asked']
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    assert errors == [], errors


def test_undo_and_redo_carry_the_unit_and_the_switches(page):
    pg, errors, state = page
    _mode(pg, 'data-flow')
    _setup(pg, state, show='ft', pref='ft')
    sel = pg.locator('#data-jump-unit')
    sel.focus()
    sel.select_option('m')
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    # the select keeps focus after the pick, the way a hand leaves it
    assert pg.evaluate("() => document.activeElement && document.activeElement.id") == 'data-jump-unit'
    pg.keyboard.press('ControlOrMeta+z')
    _wait_all_read(pg, 'ft')
    _wait_server_unit(pg, 'ft')
    pg.keyboard.press('ControlOrMeta+Shift+z')
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    pg.evaluate("() => window.app.undo()")
    _wait_all_read(pg, 'ft')
    _wait_server_unit(pg, 'ft')
    assert errors == [], errors


def test_the_export_dialog_and_the_sidebars_stay_in_step(page):
    pg, errors, state = page
    _mode(pg, 'power')
    _setup(pg, state, show='ft', pref='ft')
    pg.evaluate("() => window.app.openExportModal('pull-sheet')")
    pg.wait_for_function("() => getComputedStyle(document.getElementById('export-modal')).display !== 'none'")
    pg.locator('#export-pull-sheet-cable-unit').select_option('m')
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    pg.evaluate("() => { const m = document.getElementById('export-modal'); m.style.display = 'none'; }")
    pg.locator('#power-jump-unit').select_option('ft')
    _wait_all_read(pg, 'ft')
    _wait_server_unit(pg, 'ft')
    # a file open (the project replaced wholesale) lands every control too
    pg.evaluate("""async () => {
        const app = window.app;
        const p = await (await fetch('/api/project')).json();
        p.cableUnit = 'm';
        const loaded = await (await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)})).json();
        app.project = loaded;
        app.updateUI();
    }""")
    _wait_all_read(pg, 'm')
    # New show: it starts in the Preferences' unit (feet here), and every
    # control follows
    pg.evaluate("() => window.app.createNewProject()")
    _wait_all_read(pg, 'ft')
    _wait_server_unit(pg, 'ft')
    assert errors == [], errors


def test_a_locked_screen_does_not_hold_the_unit(page):
    pg, errors, state = page
    _mode(pg, 'data-flow')
    _setup(pg, state, show='ft', pref='ft')
    pg.evaluate("() => { const l = window.app.project.layers[0]; l.locked = true; window.app.updateUI(); }")
    pg.locator('#data-jump-unit').select_option('m')
    _wait_all_read(pg, 'm')
    _wait_server_unit(pg, 'm')
    pg.evaluate("() => { const l = window.app.project.layers[0]; l.locked = false;"
                " window.app.updateLayers([l]); }")
    assert errors == [], errors


# ── every unit control looks like a dropdown ─────────────────────────────

CHEVRON_JS = """(sel) => {
    const el = document.querySelector(sel);
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    // the chevron sits 7 px in from the right edge (theme.css); what is
    // drawn at its middle must be the select itself, not something on top
    const hit = document.elementFromPoint(r.right - 11, r.top + r.height / 2);
    // the nearest box that clips (the sidebar's scroller, the dialog body)
    let clip = el.parentElement;
    while (clip && clip !== document.body) {
        const o = getComputedStyle(clip);
        if (/(hidden|auto|scroll|clip)/.test(o.overflowX + o.overflow)) break;
        clip = clip.parentElement;
    }
    const c = (clip || document.body).getBoundingClientRect();
    return {
        image: cs.backgroundImage, repeat: cs.backgroundRepeat,
        appearance: cs.appearance || cs.webkitAppearance,
        padRight: parseFloat(cs.paddingRight), width: r.width, height: r.height,
        inside: r.left >= c.left - 0.5 && r.right <= c.right + 0.5,
        hitIsSelect: hit === el || el.contains(hit),
        tag: el.tagName,
    };
}"""


def _assert_dropdown(pg, sel):
    got = pg.evaluate(CHEVRON_JS, sel)
    assert got['tag'] == 'SELECT', (sel, got)
    assert 'svg' in got['image'] and 'M0 0l4.5 5.5L9 0z' in got['image'].replace('%20', ' '), (
        f'{sel} lost the chevron', got)
    assert got['repeat'].startswith('no-repeat') and got['appearance'] == 'none', (sel, got)
    assert got['padRight'] >= 20 and got['width'] >= got['padRight'] + 14, (sel, got)
    assert got['inside'] and got['hitIsSelect'], (f'{sel} is clipped or covered', got)


def test_every_unit_control_is_a_dropdown_with_its_chevron(page):
    pg, errors, state = page
    _setup(pg, state, show='ft', pref='ft')
    _mode(pg, 'data-flow')
    _assert_dropdown(pg, '#data-jump-unit')
    # beside the jumper fields: the row under Vertical / Horizontal
    rows = pg.evaluate("""() => ['#data-jump-h', '#data-jump-unit'].map(s => {
        const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.bottom]; })""")
    assert abs(rows[0][0] - rows[1][0]) < 1 and rows[1][1] >= rows[0][2], rows
    _mode(pg, 'power')
    _assert_dropdown(pg, '#power-jump-unit')
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_function("() => getComputedStyle(document.getElementById('preferences-modal')).display !== 'none'")
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="pull"]').click()
    pg.locator('#pref-cable-unit').scroll_into_view_if_needed()
    _assert_dropdown(pg, '#pref-cable-unit')
    pg.locator('#preferences-cancel').click()
    for kind, sel in (('pull-sheet', '#export-pull-sheet-cable-unit'),
                      ('binder', '#export-binder-cable-unit')):
        pg.evaluate("(k) => window.app.openExportModal(k)", kind)
        pg.wait_for_function("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                             " return r.width > 0 && r.height > 0; }", arg=sel)
        pg.locator(sel).scroll_into_view_if_needed()
        _assert_dropdown(pg, sel)
        pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    assert errors == [], errors


ALL_SELECTS_JS = """(modal) => [...document.querySelectorAll(`#${modal} select`)].map(el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {id: el.id || el.className, image: cs.backgroundImage, shown: r.width > 0 && r.height > 0,
            padRight: parseFloat(cs.paddingRight), width: r.width};
})"""


def _assert_every_select_is_a_dropdown(pg, modal):
    rows = pg.evaluate(ALL_SELECTS_JS, modal)
    assert rows, modal
    flat = [r['id'] for r in rows if 'svg' not in r['image']]
    assert not flat, f'selects in #{modal} drawn without the chevron: {flat}'
    cramped = [r for r in rows if r['shown'] and r['width'] < r['padRight'] + 14]
    assert not cramped, f'selects in #{modal} too narrow to show the chevron: {cramped}'


def test_every_select_in_the_two_dialogs_shows_the_chevron(page):
    """The modal rule's `background` shorthand once reset theme.css's
    chevron on every select in Preferences and Export: each read as a text
    box. Every select in both dialogs, on every Preferences tab."""
    pg, errors, state = page
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_function("() => getComputedStyle(document.getElementById('preferences-modal')).display !== 'none'")
    keys = pg.evaluate("() => [...document.querySelectorAll('#preferences-modal .pm-tabstrip .view-tab')]"
                       ".map(t => t.dataset.key)")
    assert 'pull' in keys, keys
    for key in keys:
        pg.locator(f'#preferences-modal .pm-tabstrip .view-tab[data-key="{key}"]').click()
        _assert_every_select_is_a_dropdown(pg, 'preferences-modal')
    pg.locator('#preferences-cancel').click()
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_function("() => getComputedStyle(document.getElementById('export-modal')).display !== 'none'")
    _assert_every_select_is_a_dropdown(pg, 'export-modal')
    pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    assert errors == [], errors
