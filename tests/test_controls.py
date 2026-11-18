"""Preferences > Controls: your own keys and your own 3D mouse (the owner's
rulings, 2026-11-18).

- controls.js, the plain functions (no DOM, so they run under node here and
  skip where node is not installed): the registry of rebindable actions by
  area, a key press read as a chord, the names on a Mac and on Windows, the
  keys refused (the browser's and the system's, and the fixed Enter, Esc,
  Space and arrows), the swap question's "already in use", and the 3D
  mouse map: the Standard preset reads every press exactly as the 11-08
  rules did, Orbit first and a per action change read theirs.
- The Controls tab in the browser: every action listed by area with its
  keys, the search box, a key recorded by clicking its chip and pressing
  the new one, Esc cancelling the recording, a key in use asking to swap in
  the app's own dialog (Yes moves it, No keeps both), Reset per action
  (no question) and Reset all (asks), keys the browser keeps refused, a
  change kept by Save and still there after a reload, and the new key
  working while the old one does nothing.
- Help > Keyboard Shortcuts, the menus and the tooltips say the person's
  keys.
- The 3D view on Orbit first, and on a per action change.

Run locally:
    python -m pytest tests/test_controls.py -n 4 --dist loadfile
"""

import json
import math
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROLS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'controls.js')

needs_node = pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')


def _js(expr, *args):
    """Evaluate `expr` with C bound to Controls and A to the arguments."""
    script = (f"const C = require({json.dumps(CONTROLS_JS)}); const A = {json.dumps(list(args))};"
              f"console.log(JSON.stringify({expr}));")
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# ── the registry ─────────────────────────────────────────────────────────

AREAS = ['General', 'Pixel Map', 'Data', 'Power', 'Header/Footer', '3D', 'IDM Locator']


@needs_node
def test_every_action_has_an_area_a_label_and_its_shipped_keys():
    acts = _js('C.ACTIONS')
    assert _js('C.AREAS') == AREAS
    ids = [a['id'] for a in acts]
    assert len(ids) == len(set(ids)), ids
    assert {a['area'] for a in acts} == set(AREAS)
    for a in acts:
        assert a['label'] and a['keys'], a
        assert _js('A[0].map(C.normalize)', a['keys']) == a['keys'], a
    shipped = {a['id']: a['keys'] for a in acts}
    # the keys the app always had, by area
    assert shipped['undo'] == ['mod+KeyZ'] and shipped['redo'] == ['mod+shift+KeyZ']
    assert shipped['duplicate'] == ['mod+KeyJ'] and shipped['selectAll'] == ['mod+KeyA']
    assert shipped['fitToView'] == ['mod+shift+Digit1'] and shipped['toggleSnap'] == ['mod+shift+Quote']
    assert shipped['deleteScreen'] == ['Delete', 'Backspace'] == shipped['removeBars'] == shipped['clearMark']
    assert shipped['nextPort'] == ['Tab', 'BracketRight'] == shipped['nextCircuit']
    assert shipped['snakePorts'] == ['alt+Enter']
    assert shipped['frame3d'] == ['KeyF'] and shipped['viewIso'] == ['Digit6'] and shipped['turn3d'] == ['KeyR']


@needs_node
def test_no_two_shipped_actions_fight_for_a_key():
    """Keys may repeat only between areas that never act on the same tab
    (Tab is Next Port on Data and Next Circuit on Power)."""
    clashes = _js("C.ACTIONS.flatMap(a => a.keys.map(k => [a.id, k, C.conflicts(null, a.id, k)]))"
                  ".filter(x => x[2].length)")
    assert clashes == [], clashes


@needs_node
def test_enter_and_esc_are_fixed_rules_never_an_action():
    """Enter ends an edit and Esc closes what is on top, everywhere: no
    action ships on them and neither can be recorded; Space and the arrow
    keys too. A modified Enter (Alt+Enter snakes the lit ports) is fine."""
    keys = [k for a in _js('C.ACTIONS') for k in a['keys']]
    for fixed in ('Enter', 'Escape', 'shift+Enter', 'Space', 'ArrowUp', 'PageDown'):
        assert fixed not in keys
    out = _js("['Enter', 'shift+Enter', 'Escape', 'mod+Escape', 'Space', 'ArrowUp', 'shift+ArrowLeft',"
              " 'PageDown', 'alt+Enter', 'mod+ArrowUp'].map(k => C.refusal(k, false))")
    assert out[0] == out[1] == 'Enter is fixed: it ends an edit.'
    assert out[2] == out[3] == 'Esc is fixed: it closes what is on top and cancels.'
    assert out[4] == 'Space is fixed: hold it to pan.'
    assert out[5] == out[6] == out[7] == 'The arrow keys are fixed: they move in their own direction.'
    assert out[8:] == ['', '']
    fixed = _js('C.FIXED.map(f => f.keys)')
    assert 'Enter' in fixed and 'Esc' in fixed


@needs_node
def test_keys_the_browser_or_the_system_keep_are_refused():
    win = _js("['mod+KeyW', 'mod+Tab', 'mod+shift+Tab', 'alt+F4', 'alt+Tab', 'mod+KeyN', 'mod+KeyT',"
              " 'mod+Digit3', 'meta+KeyD', 'mod+KeyD', 'mod+shift+Digit3'].map(k => C.refusal(k, false))")
    assert win[0] == "Ctrl+W belongs to the browser or the system, so the app can't use it."
    assert all(win[:8]), win
    assert win[8] == "Win+D belongs to Windows, so the app can't use it."
    assert win[9:] == ['', ''], win
    mac = _js("['mod+KeyQ', 'mod+KeyW', 'mod+Tab', 'mod+KeyH', 'mod+Space', 'mod+shift+Digit3',"
              " 'mod+KeyD', 'alt+F4'].map(k => C.refusal(k, true))")
    assert mac[0] == "Cmd+Q belongs to the browser or the system, so the app can't use it."
    assert all(mac[:6]), mac
    assert mac[6:] == ['', ''], mac


@needs_node
def test_names_say_mac_keys_on_a_mac_and_pc_keys_elsewhere():
    chords = ['mod+shift+Digit1', 'mod+alt+KeyS', 'alt+KeyS', 'mod+Comma', 'shift+Tab', 'Delete',
              'mod+shift+Quote', 'BracketLeft', 'ctrl+KeyK']
    assert _js('A[0].map(k => C.format(k, false))', chords) == [
        'Ctrl+Shift+1', 'Ctrl+Alt+S', 'Alt+S', 'Ctrl+,', 'Shift+Tab', 'Delete', "Ctrl+Shift+'", '[',
        'Control+K']
    assert _js('A[0].map(k => C.format(k, true))', chords) == [
        'Cmd+Shift+1', 'Cmd+Option+S', 'Option+S', 'Cmd+,', 'Shift+Tab', 'Delete', "Cmd+Shift+'", '[',
        'Control+K']


@needs_node
def test_a_key_press_is_read_exactly():
    """The chord a press makes, and an action matched only by exactly its
    modifiers; Undo and its family take Cmd or Ctrl as before, the 3D keys
    the letter typed, Delete any modifier."""
    ev = [{'code': 'KeyD', 'key': 'd', 'ctrlKey': True},
          {'code': 'KeyD', 'key': 'd', 'metaKey': True},
          {'code': 'Numpad3', 'key': '3'},
          {'code': 'ShiftLeft', 'key': 'Shift', 'shiftKey': True},
          {'code': 'KeyS', 'key': 'ss', 'altKey': True, 'metaKey': True}]
    assert _js('A[0].map(e => C.fromEvent(e, false))', ev) == [
        'mod+KeyD', 'meta+KeyD', 'Digit3', None, 'meta+alt+KeyS']
    assert _js('A[0].map(e => C.fromEvent(e, true))', ev)[:2] == ['ctrl+KeyD', 'mod+KeyD']
    m = lambda e, i, mac=False: _js(f'C.matches(A[0], A[1], null, {json.dumps(mac)})', e, i)  # noqa: E731
    assert m({'code': 'KeyS', 'ctrlKey': True}, 'save')
    assert not m({'code': 'KeyS', 'ctrlKey': True, 'shiftKey': True}, 'save')
    assert not m({'code': 'KeyS', 'metaKey': True}, 'save'), 'the other platform key is no Save'
    assert m({'code': 'KeyZ', 'metaKey': True}, 'undo') and m({'code': 'KeyZ', 'ctrlKey': True}, 'undo', True)
    assert not m({'code': 'KeyZ', 'ctrlKey': True, 'shiftKey': True}, 'undo')
    assert m({'code': 'KeyZ', 'ctrlKey': True, 'shiftKey': True}, 'redo')
    assert m({'code': 'KeyQ', 'key': 'f'}, 'frame3d'), 'the letter typed counts in 3D'
    assert not m({'code': 'KeyF', 'key': 'f', 'ctrlKey': True}, 'frame3d')
    assert m({'code': 'Numpad4', 'key': '4'}, 'viewRight')
    assert m({'code': 'Delete', 'ctrlKey': True}, 'clearMark') and m({'code': 'Backspace'}, 'deleteScreen')
    assert m({'code': 'BracketLeft'}, 'prevPort') and m({'code': 'Tab', 'shiftKey': True}, 'prevCircuit')
    assert not m({'code': 'Tab'}, 'prevPort')
    assert m({'code': 'Enter', 'altKey': True}, 'snakePorts')


@needs_node
def test_the_person_s_keys_replace_the_shipped_ones_and_only_changes_are_stored():
    user = {'keys': {'duplicate': ['mod+KeyD'], 'copy': [], 'nope': ['mod+KeyX'], 'paste': ['junk+']}}
    assert _js('C.keysFor(A[0], "duplicate")', user) == ['mod+KeyD']
    assert _js('C.keysFor(A[0], "copy")', user) == [], 'an empty list is an action with no key'
    assert _js('C.keysFor(A[0], "undo")', user) == ['mod+KeyZ']
    assert _js('C.matches({code: "KeyD", ctrlKey: true}, "duplicate", A[0], false)', user)
    assert not _js('C.matches({code: "KeyJ", ctrlKey: true}, "duplicate", A[0], false)', user)
    clean = _js('C.clone(A[0])', user)
    assert 'nope' not in clean['keys'] and clean['keys']['paste'] == []
    assert clean['mouse3d'] == {'preset': 'standard', 'actions': {}}
    # the shipped keys put back are not stored
    assert _js('C.withKeys(A[0], "duplicate", ["mod+KeyJ"]).keys', user).get('duplicate') is None
    assert _js('C.withKeys(A[0], "duplicate", null).keys', user).get('duplicate') is None
    assert _js('C.empty()') == {'keys': {}, 'mouse3d': {'preset': 'standard', 'actions': {}}}


@needs_node
def test_a_key_in_use_is_named_where_the_action_acts():
    user = {'keys': {'duplicate': ['mod+KeyD']}}
    assert _js('C.conflicts(A[0], "copy", "mod+KeyD")', user) == ['duplicate']
    # F is the 3D view's Frame; on Pixel Map nothing has it
    assert _js('C.conflicts(null, "deleteScreen", "KeyF")') == []
    assert _js('C.conflicts(null, "fitToView", "KeyF")') == ['frame3d'], 'a General key acts on 3D too'
    assert _js('C.conflicts(null, "nextCircuit", "Tab")') == [], 'Tab steps ports on Data, circuits on Power'


# ── the 3D mouse map ─────────────────────────────────────────────────────

def _old_standard(button, shift, alt, mod):
    """How the 3D view read a mouse press before Controls (2026-11-08):
    middle or right, or Alt+left, moved the camera (right or Shift: pan);
    any other left press selected, boxed or moved."""
    if button in (1, 2) or (button == 0 and alt):
        return {'camera': 'pan' if (button == 2 or shift) else 'orbit'}
    if button == 0:
        return {'pick': True, 'select': True, 'move': True, 'moveMod': 'none', 'box': True, 'defer': None}
    return None


@needs_node
def test_the_standard_preset_reads_every_press_as_before():
    combos = [(b, s, a, m) for b in (0, 1, 2, 3) for s in (False, True) for a in (False, True)
              for m in (False, True)]
    got = _js("A[0].map(([b, s, a, m]) => C.resolvePress(C.mouseMap(null), {button: b, shift: s, alt: a, mod: m}))",
              combos)
    want = [_old_standard(*c) for c in combos]
    assert got == want, [(c, g, w) for c, g, w in zip(combos, got, want) if g != w]
    assert _js('C.mouseMap(null).custom') is False


@needs_node
def test_orbit_first_orbits_on_an_empty_left_drag_and_boxes_with_shift():
    m = 'C.mouseMap({mouse3d: {preset: "orbitFirst"}})'
    r = lambda **ev: _js(f'C.resolvePress({m}, Object.assign({{shift: false, alt: false, mod: false}}, A[0]))', ev)  # noqa: E731
    plain = r(button=0)
    assert plain['defer'] == 'orbit' and plain['select'] and plain['move'], plain
    assert r(button=0, shift=True)['defer'] is None and r(button=0, shift=True)['box']
    assert r(button=0, mod=True)['defer'] is None and r(button=0, mod=True)['box']
    assert r(button=1) == {'camera': 'orbit'} and r(button=1, shift=True) == {'camera': 'pan'}
    assert r(button=2) == {'camera': 'pan'} and r(button=0, alt=True) == {'camera': 'orbit'}


@needs_node
def test_each_3d_action_can_take_a_button_and_a_key():
    user = {'mouse3d': {'preset': 'standard', 'actions': {
        'orbit': {'button': 'right', 'mod': 'none'}, 'pan': {'button': 'middle', 'mod': 'none'},
        'box': {'button': 'left', 'mod': 'alt'}}}}
    m = _js('C.mouseMap(A[0])', user)
    assert m['custom'] is True
    # Alt+left is the box's now: the preset's Alt+drag orbit steps aside
    assert {'action': 'orbit', 'button': 'left', 'mods': ['alt']} not in m['extras']
    r = lambda **ev: _js('C.resolvePress(C.mouseMap(A[0]), Object.assign({shift: false, alt: false, mod: false}, A[1]))', user, ev)  # noqa: E731
    assert r(button=2) == {'camera': 'orbit'}
    assert r(button=1) == {'camera': 'pan'}
    alt = r(button=0, alt=True)
    assert alt.get('pick') and alt['box'], alt
    # a zoom on a drag button
    z = _js('C.resolvePress(C.mouseMap({mouse3d: {actions: {zoom: {button: "right", mod: "shift"}}}}),'
            ' {button: 2, shift: true, alt: false, mod: false})')
    assert z == {'camera': 'zoom'}
    # two drags from empty space on one button and key fight: named
    assert _js('C.mouseConflicts(null, "orbit", {button: "right", mod: "none"})') == ['pan']
    assert _js('C.mouseConflicts(null, "select", {button: "middle", mod: "none"})') == []
    names = _js('[C.mouseName({button: "middle", mod: "none"}, false), C.mouseName({button: "left", mod: "alt"}, true),'
                ' C.mouseName({button: "left", mod: "mod"}, false, "click"), C.mouseName({button: "wheel", mod: "none"})]')
    assert names == ['Middle-drag', 'Option+drag', 'Ctrl+click', 'Wheel']


# ── in the browser ───────────────────────────────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from app_dialogs import answer_app_dialog  # noqa: E402
from test_stage3d import _context, reset, screen, stored, history_len, undo  # noqa: E402
from test_stage3d_navigation import (camera, view, drag, angle_of, fresh, selected,  # noqa: E402
                                     probe, where)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project and its preferences as found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app.project && window.canvasRenderer && window.Controls)")
    pg.wait_for_timeout(1500)
    pg.url_ = e2e_server
    yield pg
    context.close()


SET_CONTROLS_JS = """async (controls) => {
    const a = window.app;
    const prefs = Object.assign({}, a.getPreferences(), {controls});
    await fetch('/api/preferences', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                     body: JSON.stringify(prefs)});
    a._serverPreferences = prefs;
    try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (e) {}
    a.refreshControlLabels();
}"""


def set_controls(pg, controls):
    pg.evaluate(SET_CONTROLS_JS, controls)


def served(pg):
    return pg.evaluate("async () => (await (await fetch('/api/preferences')).json()).controls")


def is_mac(pg):
    return pg.evaluate('window.app._isMacPlatform()')


def mod(pg):
    return 'Meta' if is_mac(pg) else 'Control'


def mod_word(pg):
    return 'Cmd' if is_mac(pg) else 'Ctrl'


@pytest.fixture(autouse=True)
def _shipped_controls(request):
    """Each browser test starts on the shipped keys with no dialog up; the
    plain-function tests above need no page."""
    if 'page' not in request.fixturenames:
        yield
        return
    page = request.getfixturevalue('page')
    page.evaluate("""() => {
        document.querySelectorAll('.app-ask-modal').forEach(m => m.remove());
        const p = document.getElementById('preferences-modal');
        if (p) p.style.display = 'none';
        const s = document.getElementById('shortcuts-modal');
        if (s) s.style.display = 'none';
    }""")
    set_controls(page, {'keys': {}, 'mouse3d': {'preset': 'standard', 'actions': {}}})
    yield


def open_controls(pg):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="controls"]').click()
    pg.wait_for_selector('#pref-controls-list .pm-control-row', state='visible')


def chip(pg, cid, i=0):
    return pg.locator(f'#pref-controls-list .pm-key-chip[data-control="{cid}"][data-index="{i}"]')


def chips(pg, cid):
    return pg.locator(f'#pref-controls-list .pm-control-row[data-control="{cid}"] .pm-key-chip').all_inner_texts()


def note(pg):
    return pg.locator('#pref-controls-note').inner_text()


def record(pg, cid, key, i=0):
    chip(pg, cid, i).click()
    assert chip(pg, cid, i).inner_text() == 'Press a key'
    pg.keyboard.press(key)
    pg.wait_for_timeout(150)


def save(pg):
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(500)


def no_question(pg):
    return pg.locator('.app-ask-modal').count() == 0


def test_the_tab_lists_every_action_by_area_with_its_keys(page):
    open_controls(page)
    areas = page.locator('#pref-controls-list .pm-controls-area h4').all_inner_texts()
    assert [a.lower() for a in areas] == [a.lower() for a in AREAS + ['3D mouse and trackpad', 'Fixed keys']], areas
    acts = page.evaluate("() => window.Controls.ACTIONS.map(a => a.id)")
    rows = page.evaluate("() => [...document.querySelectorAll('#pref-controls-list .pm-control-row[data-control]')]"
                         ".map(r => r.dataset.control)")
    assert rows == acts
    m = mod_word(page)
    assert chips(page, 'undo') == [f'{m}+Z']
    assert chips(page, 'deleteScreen') == ['Delete', 'Backspace']
    assert chips(page, 'nextPort') == ['Tab', ']']
    assert chips(page, 'exportPng') == [('Option' if is_mac(page) else 'Alt') + '+S']
    # every Reset is off while nothing is changed
    assert page.locator('#pref-controls-list .pm-control-reset:not([disabled])').count() == 0
    # the fixed rules are listed, with no key to click
    fixed = page.locator('#pref-controls-list .pm-control-fixed').all_inner_texts()
    assert any('Enter' in f for f in fixed) and any('Esc' in f for f in fixed)
    assert page.locator('#pref-controls-list .pm-control-fixed .pm-key-chip').count() == 0
    page.locator('#preferences-cancel').click()
    assert page.errors == []


def test_the_search_box_finds_an_action_or_a_key(page):
    open_controls(page)
    box = page.locator('#pref-controls-search')
    box.fill('dupl')
    shown = page.evaluate("() => [...document.querySelectorAll('#pref-controls-list .pm-control-row[data-control]')]"
                          ".filter(r => !r.hidden).map(r => r.dataset.control)")
    assert shown == ['duplicate'], shown
    box.fill(f'{mod_word(page)}+shift'.lower())
    shown = page.evaluate("() => [...document.querySelectorAll('#pref-controls-list .pm-control-row[data-control]')]"
                          ".filter(r => !r.hidden).map(r => r.dataset.control)")
    assert set(shown) == {'redo', 'fitToView', 'zoomToSelection', 'toggleSnap'}, shown
    box.fill('orbit')
    assert page.locator('#pref-controls-list [data-mouse-row="orbit"]').is_visible()
    box.fill('zzzz nothing')
    assert 'Nothing matches' in page.locator('#pref-controls-list .pm-controls-empty').inner_text()
    box.fill('')
    page.locator('#preferences-cancel').click()


def seed_one_screen(pg):
    pg.evaluate("""async () => {
        const j = (m, u, b) => fetch(u, {method: m, headers: {'Content-Type': 'application/json'},
                                          body: b === undefined ? undefined : JSON.stringify(b)}).then(r => r.json());
        const proj = await j('GET', '/api/project');
        proj.layers = []; proj.groups = [];
        await j('PUT', '/api/project', proj);
        await j('POST', '/api/layer/add', {name: 'KEYS WALL', columns: 4, rows: 3,
                                           cabinet_width: 200, cabinet_height: 200});
    }""")


def reload_app(pg):
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app.project && window.canvasRenderer && window.Controls)")
    pg.wait_for_timeout(1500)


def screens(pg):
    return pg.evaluate("() => window.app.project.layers.length")


def test_a_new_key_works_is_kept_by_save_and_is_there_after_a_reload(page):
    m = mod(page)
    open_controls(page)
    record(page, 'duplicate', f'{m}+KeyD')
    assert chips(page, 'duplicate') == [f'{mod_word(page)}+D']
    assert page.locator('#pref-controls-list .pm-control-reset[data-control="duplicate"]').is_enabled()
    # nothing stored before Save
    assert (served(page) or {}).get('keys', {}).get('duplicate') is None
    save(page)
    assert served(page)['keys']['duplicate'] == ['mod+KeyD']
    seed_one_screen(page)
    reload_app(page)
    assert page.evaluate("() => window.app.controlKeys('duplicate')") == ['mod+KeyD']
    page.locator('[data-mode="pixel-map"]').click()
    page.evaluate("() => { window.app.selectLayer(window.app.project.layers[0]); document.activeElement.blur(); }")
    page.wait_for_timeout(300)
    assert screens(page) == 1
    page.keyboard.press(f'{m}+KeyJ')
    page.wait_for_timeout(600)
    assert screens(page) == 1, 'the old key still duplicated'
    page.keyboard.press(f'{m}+KeyD')
    page.wait_for_function("() => window.app.project.layers.length === 2", timeout=5000)
    # the tab opens on the saved key
    open_controls(page)
    assert chips(page, 'duplicate') == [f'{mod_word(page)}+D']
    page.locator('#preferences-cancel').click()
    assert page.errors == []


def test_help_menus_and_tooltips_say_the_new_key(page):
    set_controls(page, {'keys': {'duplicate': ['mod+KeyD'], 'fitToView': ['mod+alt+KeyF'],
                                 'frame3d': ['KeyQ'], 'viewFront': ['Digit7']},
                        'mouse3d': {'preset': 'standard', 'actions': {}}})
    w = mod_word(page)
    page.evaluate("() => window.app.handleMenuAction('keyboard-shortcuts')")
    page.wait_for_selector('#shortcuts-modal', state='visible')
    cell = page.locator('#shortcuts-modal td[data-sc-control="duplicate"]')
    assert cell.inner_text() == f'{w}+D'
    alt = 'Option' if is_mac(page) else 'Alt'
    assert page.locator('#shortcuts-modal td[data-sc-control="fitToView"]').inner_text() == f'{w}+{alt}+F'
    assert page.locator('#shortcuts-modal td[data-sc-control="frame3d home3d"]').inner_text() == 'Q / Home'
    # untouched rows keep their words, and the modifier still says the platform
    assert page.locator('#shortcuts-modal td[data-sc-control="undo redo"]').inner_text() == f'{w}+Z / {w}+Shift+Z'
    assert set(page.locator('#shortcuts-modal [data-sc-mod]').all_inner_texts()) == {w}
    page.locator('#shortcuts-close').click()
    # the menus
    dup = page.locator('#menu-edit .menu-option[data-action="duplicate"]').inner_text()
    assert dup == f'Duplicate ({w}+D)', dup
    fit = page.locator('#menu-view .menu-option[data-action="fit"], .menu-option[data-action="fit"]').first.inner_text()
    assert fit.endswith(f'({w}+{alt}+F)'), fit
    undo_label = page.locator('#menu-edit .menu-option[data-action="undo"]').inner_text()
    assert undo_label == f'Undo ({w}+Z)'
    # the tooltips that name a key
    tip = lambda sel: page.locator(sel).get_attribute('data-tooltip')  # noqa: E731
    assert tip('#btn-fit') == f'Fit raster to view ({w}+{alt}+F)'
    assert 'Press Q to frame the selected screens' in tip('#s3d-fit')
    assert tip('[data-s3d-view="front"]').startswith('Front (7),')
    assert tip('#btn-preferences') == f'Open Preferences ({w}+,)'
    # and the help panel reads them live as the pointer passes
    page.locator('#btn-fit').hover()
    page.wait_for_timeout(150)
    if page.locator('#help-tooltip-body').count():
        assert page.locator('#help-tooltip-body').inner_text() == f'Fit raster to view ({w}+{alt}+F)'
    # back to shipped: the template's own words again
    set_controls(page, {'keys': {}, 'mouse3d': {'preset': 'standard', 'actions': {}}})
    assert tip('#btn-fit') == f'Fit raster to view ({w}+Shift+1)'
    assert page.locator('#menu-edit .menu-option[data-action="duplicate"]').inner_text() == f'Duplicate ({w}+J)'


def test_a_key_in_use_asks_to_swap_yes_moves_it_no_keeps_both(page):
    w = mod_word(page)
    open_controls(page)
    # No: both stay as they were
    record(page, 'copy', f'{mod(page)}+KeyJ')
    asked = answer_app_dialog(page, accept=False)
    assert asked == f'{w}+J is already Duplicate. Use it here and clear Duplicate?'
    assert chips(page, 'copy') == [f'{w}+C'] and chips(page, 'duplicate') == [f'{w}+J']
    assert page.locator('#preferences-modal').is_visible(), 'the swap question closed Preferences'
    # the question is the app's own, with Yes and No
    record(page, 'copy', f'{mod(page)}+KeyJ')
    page.wait_for_selector('#controls-swap-modal', state='visible')
    buttons = page.locator('#controls-swap-modal .app-ask-buttons .btn').all_inner_texts()
    assert buttons == ['No', 'Yes'], buttons
    answer_app_dialog(page, accept=True)
    assert chips(page, 'copy') == [f'{w}+J']
    assert chips(page, 'duplicate') == []
    assert 'No key' in page.locator('#pref-controls-list .pm-control-row[data-control="duplicate"]').inner_text()
    save(page)
    keys = served(page)['keys']
    assert keys['copy'] == ['mod+KeyJ'] and keys['duplicate'] == []


def test_reset_one_action_at_once_and_reset_all_asks_first(page):
    w = mod_word(page)
    open_controls(page)
    record(page, 'paste', f'{mod(page)}+KeyB')
    record(page, 'frame3d', 'KeyQ')
    assert chips(page, 'paste') == [f'{w}+B'] and chips(page, 'frame3d') == ['Q']
    # one action: no question, straight back
    page.locator('#pref-controls-list .pm-control-reset[data-control="paste"]').click()
    page.wait_for_timeout(150)
    assert no_question(page)
    assert chips(page, 'paste') == [f'{w}+V']
    assert page.locator('#pref-controls-list .pm-control-reset[data-control="paste"]').is_disabled()
    assert 'Paste is back to' in note(page)
    # Reset all asks; No keeps what is there
    page.locator('#pref-controls-reset-all').click()
    asked = answer_app_dialog(page, accept=False)
    assert asked == 'Put every key and the 3D mouse back to their defaults?'
    assert chips(page, 'frame3d') == ['Q']
    page.locator('#pref-controls-list select[data-mouse="orbit"][data-part="button"]').select_option('right')
    answer_app_dialog(page, accept=True)   # Right-drag is already Pan: Yes
    page.locator('#pref-controls-reset-all').click()
    answer_app_dialog(page, accept=True)
    assert chips(page, 'frame3d') == ['F']
    assert page.locator('#pref-controls-list select[data-mouse="orbit"][data-part="button"]').input_value() == 'middle'
    save(page)
    assert served(page) == {'keys': {}, 'mouse3d': {'preset': 'standard', 'actions': {}}}


def press_synthetic(pg, init):
    """A key press the browser itself would keep: sent to the page as an
    event, so the test never asks the real browser to close a tab."""
    pg.evaluate("(init) => window.dispatchEvent(new KeyboardEvent('keydown', Object.assign({bubbles: true, cancelable: true}, init)))", init)
    pg.wait_for_timeout(150)


def test_keys_the_browser_or_the_system_keep_are_refused_with_a_note(page):
    mac = is_mac(page)
    w = mod_word(page)
    modkey = 'metaKey' if mac else 'ctrlKey'
    open_controls(page)
    chip(page, 'paste').click()
    press_synthetic(page, {'code': 'KeyW', 'key': 'w', modkey: True})
    assert note(page) == f"{w}+W belongs to the browser or the system, so the app can't use it."
    assert chips(page, 'paste') == [f'{w}+V']
    chip(page, 'paste').click()
    press_synthetic(page, {'code': 'Tab', 'key': 'Tab', modkey: True})
    assert note(page) == f"{w}+Tab belongs to the browser or the system, so the app can't use it."
    chip(page, 'paste').click()
    if mac:
        press_synthetic(page, {'code': 'KeyQ', 'key': 'q', 'metaKey': True})
        assert note(page) == "Cmd+Q belongs to the browser or the system, so the app can't use it."
    else:
        press_synthetic(page, {'code': 'F4', 'key': 'F4', 'altKey': True})
        assert note(page) == "Alt+F4 belongs to the browser or the system, so the app can't use it."
    assert chips(page, 'paste') == [f'{w}+V'] and no_question(page)
    page.locator('#preferences-cancel').click()


def test_enter_and_esc_are_not_rebindable_and_esc_cancels_a_recording(page):
    w = mod_word(page)
    open_controls(page)
    record(page, 'undo', 'Enter')
    assert note(page) == 'Enter is fixed: it ends an edit.'
    assert chips(page, 'undo') == [f'{w}+Z']
    record(page, 'undo', 'Space')
    assert note(page) == 'Space is fixed: hold it to pan.'
    # Esc cancels the recording, and only that: Preferences stays up
    chip(page, 'undo').click()
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)
    assert chips(page, 'undo') == [f'{w}+Z']
    assert page.locator('#preferences-modal').is_visible(), 'Esc closed Preferences, not the recording'
    assert not page.locator('#pref-controls-list .pm-key-chip.recording').count()
    # the next Esc is the dialog's, as ever
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    assert not page.locator('#preferences-modal').is_visible()
    assert served(page)['keys'] == {}


def test_a_second_key_can_be_added_and_one_taken_off(page):
    w = mod_word(page)
    open_controls(page)
    page.locator('#pref-controls-list .pm-key-add[data-control="undo"]').click()
    page.keyboard.press(f'{mod(page)}+KeyU')
    page.wait_for_timeout(150)
    assert chips(page, 'undo') == [f'{w}+Z', f'{w}+U']
    page.locator('#pref-controls-list .pm-key-remove[data-control="deleteScreen"][data-index="1"]').click()
    assert chips(page, 'deleteScreen') == ['Delete']
    save(page)
    keys = served(page)['keys']
    assert keys['undo'] == ['mod+KeyZ', 'mod+KeyU'] and keys['deleteScreen'] == ['Delete']


# ── the 3D mouse ─────────────────────────────────────────────────────────

def test_orbit_first_left_drag_on_empty_space_orbits_and_shift_drag_boxes(page):
    open_controls(page)
    page.locator('#pref-controls-preset').select_option('orbitFirst')
    save(page)
    assert served(page)['mouse3d'] == {'preset': 'orbitFirst', 'actions': {}}
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[1]}], {ids[1]})")
    page.wait_for_timeout(300)
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    corner = (rect['left'] + 30, rect['top'] + 30)
    assert probe(page, *corner) is None
    before = camera(page)
    steps = history_len(page)
    drag(page, corner, (corner[0] + 120, corner[1] + 40))
    after = camera(page)
    a0, a1 = angle_of(before), angle_of(after)
    assert abs(a1[0] - a0[0]) > 10 and abs(a1[1] - a0[1]) > 2, (before, after)
    assert after['target'] == pytest.approx(before['target'], abs=0.5), 'the orbit did not turn round the view centre'
    assert history_len(page) == steps and selected(page) == [ids[1]]
    assert page.evaluate("(() => { const b = document.getElementById('s3d-box'); return !b || b.hidden; })()")
    # a click on empty space still lets go
    page.mouse.click(*corner)
    page.wait_for_timeout(300)
    assert selected(page) == []
    assert camera(page) == after
    # Shift+drag across empty space draws the box
    view(page, 'front')
    cam = camera(page)
    lower = screen(page, ids[1])['at']
    bottom = (lower[0] - 10, rect['bottom'] - 10)
    drag(page, bottom, (lower[0] + 10, lower[1] + 5), keys=('Shift',))
    assert selected(page) == [ids[1]]
    assert camera(page) == cam, 'a box select moved the camera'
    # a drag on the selected screen still moves it, in one undo step
    steps = history_len(page)
    w = screen(page, ids[1])['world']
    grab = where(page, [w['min'][0] + (w['max'][0] - w['min'][0]) / 4, (w['min'][1] + w['max'][1]) / 2, w['max'][2]])
    drag(page, grab, (grab[0] + 60, grab[1]))
    assert stored(page, ids[1]) is not None and history_len(page) == steps + 1
    assert camera(page) == cam
    undo(page)
    # the corner hint says the preset's way
    assert 'Drag orbits' in page.locator('#s3d-hint').inner_text()
    assert page.errors == []


def test_a_3d_action_set_on_its_own_button_works(page):
    """Orbit on the right button (the swap question clears Pan), then Pan
    on the middle button: a right drag orbits, a middle drag pans."""
    open_controls(page)
    page.locator('#pref-controls-list select[data-mouse="orbit"][data-part="button"]').select_option('right')
    asked = answer_app_dialog(page, accept=True)
    assert asked == 'Right-drag is already Pan. Use it here and clear Pan?'
    assert page.locator('#pref-controls-list select[data-mouse="pan"][data-part="button"]').input_value() == 'none'
    page.locator('#pref-controls-list select[data-mouse="pan"][data-part="button"]').select_option('middle')
    page.wait_for_timeout(150)
    assert no_question(page)
    save(page)
    assert served(page)['mouse3d'] == {'preset': 'standard', 'actions': {
        'orbit': {'button': 'right', 'mod': 'none'}, 'pan': {'button': 'middle', 'mod': 'none'}}}
    fresh(page)
    view(page, 'front')
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    corner = (rect['left'] + 30, rect['top'] + 30)
    before = camera(page)
    drag(page, corner, (corner[0] + 120, corner[1]), button='right')
    after = camera(page)
    assert abs(angle_of(after)[0] - angle_of(before)[0]) > 10, 'a right drag did not orbit'
    assert page.evaluate("getComputedStyle(document.getElementById('context-menu')).display") == 'none'
    before = after
    drag(page, corner, (corner[0] + 120, corner[1] + 60), button='middle')
    after = camera(page)
    assert angle_of(after) == pytest.approx(angle_of(before), abs=0.5), 'a middle drag turned the camera'
    assert math.dist(after['target'], before['target']) > 1, 'a middle drag did not pan'
    assert 'Right-drag orbits, Middle-drag pans' in page.locator('#s3d-hint').inner_text()


def test_the_standard_3d_hint_keeps_its_words(page):
    fresh(page)
    assert 'Middle-drag orbits' in page.locator('#s3d-hint').inner_text()
    tip = page.locator('#s3d-hint').get_attribute('data-tooltip')
    assert 'Alt+drag' in tip and 'Keyboard Shortcuts' in tip


MAC_INIT = """Object.defineProperty(Navigator.prototype, 'platform', {get: () => 'MacIntel'});"""


def test_a_mac_reads_cmd_and_option(e2e_server, pw_browser):
    context = _context(pw_browser, init=MAC_INIT)
    pg = context.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app.project && window.Controls)")
        pg.wait_for_timeout(1000)
        assert pg.evaluate("window.app._isMacPlatform()") is True
        open_controls(pg)
        assert chips(pg, 'duplicate') == ['Cmd+J']
        assert chips(pg, 'exportPsd') == ['Cmd+Option+S']
        mods = pg.locator('#pref-controls-list select[data-mouse="orbit"][data-part="mod"] option').all_inner_texts()
        assert mods == ['No key', 'Shift', 'Option', 'Cmd'], mods
        # a Mac's Control key is a key of its own here
        record(pg, 'paste', 'Control+KeyK')
        assert chips(pg, 'paste') == ['Control+K']
        pg.locator('#preferences-cancel').click()
    finally:
        context.close()
