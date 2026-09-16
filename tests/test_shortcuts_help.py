"""Help > Keyboard Shortcuts must list every gesture the app handles.

Three guards, from the outside in:

(a) The modal opens from the Help menu action and carries every group
    heading - one per place a gesture works.

(b) The gesture inventory is PINNED: every phrase in GESTURE_PHRASES must
    appear in the modal's text. Each phrase is one distinctive fragment of
    one row (the gesture or the verb), so a row deleted or reworded out of
    the modal fails here. The inventory the phrases were read from lives
    with the modal's HTML in src/templates/index.html.

(c) A gesture cannot SHIP without a row: HANDLER_MARKERS maps a handler
    name that exists in the JS today to the modal phrase that documents it.
    The test reads the source; while the marker is still in the code its
    phrase must be in the modal. A marker that vanishes from the code is
    reported too, so a rename of the handler updates this map rather than
    silently retiring the check.

How to add a gesture
--------------------
1. Add its row to #shortcuts-modal in src/templates/index.html, under the
   group it belongs to (gesture in the first cell, what it does in the
   second; write the modifier as <span data-sc-mod>Ctrl</span> - the modal
   stamps Cmd on a Mac).
2. Add one distinctive phrase from that row to GESTURE_PHRASES.
3. Add (handler name, source file, phrase) to HANDLER_MARKERS so the row
   and the code stay tied together.

Run: python3 -m pytest tests/test_shortcuts_help.py -q --browser chromium
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')

MENU_ACTION = 'keyboard-shortcuts'

GROUP_HEADINGS = [
    'Everywhere',
    'Pixel Map',
    'Show Look',
    'Data view & the tray',
    'Power view & the tray',
    'Screens & Beaches panels',
    'Cable sheets',
    'Guided tours',
]

# One distinctive phrase per row of the modal. Platform-neutral on purpose:
# the modifier span is checked separately (test_modifier_matches_platform).
GESTURE_PHRASES = [
    # Everywhere
    'Undo / redo',
    'Copy / paste the selected layer',
    'Duplicate the current layer',
    'Delete / Backspace',
    'Open Preferences',
    'Open a project file',
    'Save the project to a file',
    'Export PNG / Export PSD',
    'Fit to view',
    'Zoom to selection (1:1)',
    'Toggle snap',
    'Scroll wheel',
    'Space+drag',
    'middle-button drag',
    'Enter in the zoom % field',
    'Toggle it in or out of the selection',
    'Marquee-select screens',
    'Click & drag a screen-name label',
    'move the screen-name label, not the screen',
    'Right-click',
    'Enter / Esc in a rename field',
    'Close a menu, a popover or a prompt',
    # Pixel Map
    'Alt+click a cabinet',
    'Alt+drag across cabinets',
    'Alt+Shift+click a cabinet',
    'Select cabinets of the current screen',
    'Toggle it in or out of the cabinet selection',
    'Clear the cabinet selection',
    'Set Blank, Restore From Blank, Set Half-tile',
    'Shift+drag a screen',
    'Shift+drag a screen onto another canvas',
    "dashed outline",
    'Center on Canvas',
    'Group Screens',
    'Move to Canvas',
    'Export this screen',
    # Show Look
    "show position",
    # Data view & the tray
    'Hold Alt',
    'Alt+click a run',
    'Click cabinets / arrow keys',
    'Select cabinets for a pattern button',
    'End the redraw',
    'Tab / Shift+Tab, ] / [',
    'Next / previous port in custom mode',
    'Redraw port N',
    'back to auto',
    'Clear port N',
    'Drag a port, card, box or processor onto a screen',
    'Drag an assigned port back onto the tray',
    'Open its editor; Esc closes it',
    '⚙ on a header',
    'Reorder the processors',
    'Esc mid-drag',
    'Alt+press a port chip, sweep across chips',
    'Snake these N',
    'Set home run',
    'Unsnake',
    'Alt+Enter',
    'Drop the lit ports',
    "Right-click a snake's tag",
    '≡ on a card or box header',
    # Power view & the tray
    'Take that circuit over',
    'Sweep a run of circuits',
    '2fer / 3fer / 4fer them',
    'Un-share all',
    'Share with next run via 2fer or 3fer',
    'Un-share this screen',
    'Clear multi N',
    'Clear circuit N',
    'Merge back into a multi',
    'Add <type> from',
    'Redraw circuit N',
    'Next / previous circuit in custom mode',
    'Drag a multi slot, circuit chip or distro onto a screen',
    'Drag an assigned slot or circuit chip back onto the tray',
    "Click a box's type chip",
    'Click a circuit chip',
    'redundancy pill',
    'Reorder the distros',
    '≡ on a multi header',
    # Screens & Beaches panels
    'Shift+click a row',
    'Select the range from the last pick',
    'Toggle it and open the menu',
    'Double-click a name',
    'Reorder screens within their canvas',
    "Drag a row onto another canvas's header",
    'Reorder the canvases',
    'Click a group header',
    '+ Add beach',
    'Reorder the beaches',
    '× on a beach',
    'Put on beach',
    '+ New beach',
    # Cable sheets
    'Next / previous length field',
    'Show the chips again',
    'Enter in a pull sheet cell',
    'the board redraws',
    # Guided tours
    'Next (Done on the last step)',
    'Leave the tour',
    'Return to the previous step',
    'Play this step again',
    'Go to N',
    'End the tour',
]

# (handler marker, source file under src/static/js, phrase in the modal).
# The marker is a name the gesture's code path is known by today.
HANDLER_MARKERS = [
    ('handleWheel', 'canvas-input.js', 'Scroll wheel'),
    ('spacePressed', 'canvas-input.js', 'Space+drag'),
    ('fitToView', 'canvas-input.js', 'Fit to view'),
    ('zoomActual', 'canvas-input.js', 'Zoom to selection (1:1)'),
    ('magneticSnap', 'canvas-input.js', 'Toggle snap'),
    ('openPreferencesModal', 'canvas-input.js', 'Open Preferences'),
    # The File menu's accelerators: handleMenuShortcut's case labels.
    ('mod+KeyO', 'app-menubar.js', 'Open a project file'),
    ('mod+KeyS', 'app-menubar.js', 'Save the project to a file'),
    ('alt+KeyS', 'app-menubar.js', 'Export PNG / Export PSD'),
    ('mod+alt+KeyS', 'app-menubar.js', 'Export PNG / Export PSD'),
    ('deleteCurrentLayer', 'canvas-input.js', 'Delete / Backspace'),
    ('duplicateLayer', 'canvas-input.js', 'Duplicate the current layer'),
    ('_toggleLayerSelectionFromCanvas', 'canvas-input.js',
     'Toggle it in or out of the selection'),
    ('selectLayersInRect', 'canvas-input.js', 'Marquee-select screens'),
    ('isDraggingScreenName', 'canvas-input.js',
     'Click & drag a screen-name label'),
    ('isAltPainting', 'canvas-input.js', 'Alt+drag across cabinets'),
    ('setPanelsHalfTileBulk', 'canvas-input.js', 'Alt+Shift+click a cabinet'),
    ('setPanelsBlankBulk', 'canvas-input.js', 'Alt+click a cabinet'),
    ('togglePixelMapPanelSelection', 'canvas-input.js',
     'Toggle it in or out of the cabinet selection'),
    ('clearPixelMapSelection', 'app-core.js', 'Clear the cabinet selection'),
    ('isDraggingCanvas', 'canvas-input.js', 'dashed outline'),
    ('handleOverrideClick', 'canvas-input.js', 'Alt+click a run'),
    ('updateOverrideHover', 'canvas-input.js', 'Hold Alt'),
    ('endOverrideEdit', 'canvas-input.js', 'End the redraw'),
    ('handleCustomArrowKey', 'app-custom-runs.js',
     'Click cabinets / arrow keys'),
    ('stepCustomPort', 'canvas-input.js', 'Tab / Shift+Tab, ] / ['),
    ('_prepareOverrideMenu', 'app-run-overrides.js', 'back to auto'),
    ('_prepareClearMenu', 'app-dock-menus.js', 'Clear port N'),
    ('_prepareShareMenus', 'app-dock-menus.js',
     'Share with next run via 2fer or 3fer'),
    ('_prepareBatchMenu', 'app-dock-menus.js', '2fer / 3fer / 4fer them'),
    ('_prepareMergeMenu', 'app-dock-menus.js', 'Merge back into a multi'),
    ('_prepareOutputsMenu', 'app-context-menu.js', 'Add <type> from'),
    ('_sweepPending', 'canvas-input.js', 'Sweep a run of circuits'),
    ('_traySweepStart', 'app-dock-drag.js',
     'Alt+press a port chip, sweep across chips'),
    ('_traySweepSnake', 'app-dock-sweep.js', 'Alt+Enter'),
    ('_traySweepClear', 'app-dock-sweep.js', 'Drop the lit ports'),
    ('_prepareSnakeMenu', 'app-context-menu.js', 'Snake these N'),
    ('_dockArmDrag', 'app-dock-drag.js', 'Esc mid-drag'),
    ('_dockReorderIndex', 'app-dock-drag.js', 'Reorder the processors'),
    ('_dockBuildDataCableSheetButton', 'app-dock-cable-sheets.js',
     '≡ on a card or box header'),
    ('_dockBuildCableSheetButton', 'app-dock-cable-sheets.js',
     '≡ on a multi header'),
    ('setDistroBoxType', 'app-dock.js', "Click a box's type chip"),
    ('_dockRedundancyPill', 'app-dock.js', 'redundancy pill'),
    ('_setTileOpen', 'app-core.js', 'Open its editor; Esc closes it'),
    ('selectLayerRange', 'app-layers-panel.js', 'Shift+click a row'),
    ('toggleLayerSelection', 'app-layers-panel.js',
     'Toggle it and open the menu'),
    ('reorderLayersByDrag', 'app-layers-panel.js',
     'Reorder screens within their canvas'),
    ('moveLayerToCanvas', 'app-canvas-ui.js',
     "Drag a row onto another canvas's header"),
    ('reorderCanvasBeforeTarget', 'app-canvas-ui.js', 'Reorder the canvases'),
    ('setGroupExpanded', 'app-screen-groups.js', 'Click a group header'),
    ('canGroupSelection', 'app-context-menu.js', 'Group Screens'),
    ('openMoveToCanvasMenu', 'app-menubar.js', 'Move to Canvas'),
    ('_prepareBinderMenu', 'app-context-menu.js', 'Export this screen'),
    ('centerLayersOnCanvas', 'app-context-menu.js', 'Center on Canvas'),
    ('_prepareBeachMenu', 'app-beaches.js', 'Put on beach'),
    ('moveBeachBefore', 'app-beaches.js', 'Reorder the beaches'),
    ('removeBeach', 'app-beaches.js', '× on a beach'),
    ('createBeach', 'app-beaches.js', '+ Add beach'),
    ('renameBeach', 'app-beaches.js', 'Double-click a name'),
    ('ftInputs', 'app-dock-cable-sheets.js', 'Next / previous length field'),
    ('isPullSheetEditorOpen', 'app-pull-sheet-editor.js', 'the board redraws'),
    ('jumpTo', 'quickstart.js', 'Go to N'),
    ('goBack', 'quickstart.js', 'Return to the previous step'),
    ('replay', 'quickstart.js', 'Play this step again'),
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _modal_html():
    html = _read(INDEX_HTML)
    start = html.index('<div id="shortcuts-modal"')
    end = html.index('<!-- About Modal -->', start)
    return html[start:end]


def _modal_text():
    """The modal's text the way the browser would read it, minus tags."""
    text = re.sub(r'<[^>]+>', ' ', _modal_html())
    text = (text.replace('&amp;', '&').replace('&lt;', '<')
                .replace('&gt;', '>').replace('&rsquo;', '’'))
    return re.sub(r'\s+', ' ', text)


# ── (c) source side: no handler without a row ────────────────────────────

def test_every_handler_marker_still_exists():
    """A marker that leaves the code means a gesture was renamed or removed:
    update HANDLER_MARKERS (and the modal row) rather than losing the tie."""
    missing = []
    for marker, fname, _phrase in HANDLER_MARKERS:
        src = _read(os.path.join(JS_DIR, fname))
        if marker not in src:
            missing.append(f'{marker} in {fname}')
    assert not missing, (
        'handler markers no longer in the source - rename or drop them in '
        'HANDLER_MARKERS and fix the modal row:\n  ' + '\n  '.join(missing))


def test_every_live_handler_has_a_modal_row():
    text = _modal_text()
    unlisted = [f'{marker} ({fname}) -> "{phrase}"'
                for marker, fname, phrase in HANDLER_MARKERS
                if marker in _read(os.path.join(JS_DIR, fname))
                and phrase not in text]
    assert not unlisted, (
        'gestures handled in the code with no row in Help > Keyboard '
        'Shortcuts:\n  ' + '\n  '.join(unlisted))


def test_inventory_phrases_are_in_the_template():
    """Same pin as the browser check, without a browser - so a plain
    `pytest tests/test_shortcuts_help.py -k template` catches a lost row."""
    text = _modal_text()
    missing = [p for p in GESTURE_PHRASES if p not in text]
    assert not missing, 'rows missing from the modal: ' + repr(missing)


def test_group_headings_are_in_the_template():
    text = _modal_text()
    missing = [h for h in GROUP_HEADINGS if h not in text]
    assert not missing, 'group headings missing: ' + repr(missing)


def test_no_banned_display_words():
    """UI strings say circuits and shared circuits, never these."""
    text = _modal_text().lower()
    for banned in ('tails', 'gang'):
        assert re.search(r'\b' + banned + r'\b', text) is None, (
            f'"{banned}" is banned display language (found in the modal)')


def test_modifier_is_a_stamped_span_not_literal_text():
    """The modifier is written once as <span data-sc-mod> so the modal can
    say Cmd on a Mac and Ctrl elsewhere; a literal Cmd or Ctrl in a row
    would read wrong on one platform."""
    html = _modal_html()
    assert 'data-sc-mod' in html
    rows = re.sub(r'<span data-sc-mod>Ctrl</span>', '', html)
    assert re.search(r'\bCmd\b|\bCtrl\b', re.sub(r'<!--.*?-->', '', rows, flags=re.S)) is None, (
        'write the modifier as <span data-sc-mod>Ctrl</span>, not literally')


# ── (d) the File menu's printed accelerators are honoured ────────────────

MENUBAR_JS = os.path.join(JS_DIR, 'app-menubar.js')

# The four chords handleMenuShortcut answers to, and the File menu item
# each one dispatches.
FILE_MENU_SHORTCUTS = {
    'mod+KeyO': 'open',
    'mod+KeyS': 'save',
    'alt+KeyS': 'export-png',
    'mod+alt+KeyS': 'export-psd',
}


def _chord(label, mod_word, alt_word):
    """'Cmd+Option+S' / 'Ctrl+Alt+S' -> 'mod+alt+KeyS', the dispatcher's
    spelling. Any other token is an error: the dispatcher never sees it."""
    mod = alt = False
    key = None
    for tok in label.split('+'):
        if tok == mod_word:
            mod = True
        elif tok == alt_word:
            alt = True
        elif re.fullmatch(r'[A-Z]', tok):
            key = 'Key' + tok
        elif tok == ',':
            key = 'Comma'
        else:
            raise AssertionError(f'unknown accelerator token {tok!r} in {label!r}')
    assert key, label
    return ('mod+' if mod else '') + ('alt+' if alt else '') + key


def _file_menu_labels():
    """{action: (mac label or None, win label or None)} from #menu-file."""
    html = _read(INDEX_HTML)
    start = html.index('<div id="menu-file"')
    end = html.index('<div id="menu-edit"', start)
    out = {}
    for m in re.finditer(r'<div class="menu-option[^"]*"([^>]*)>', html[start:end]):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        if 'data-action' in attrs:
            out[attrs['data-action']] = (attrs.get('data-shortcut-mac'),
                                         attrs.get('data-shortcut-win'))
    return out


def _dispatcher_cases():
    """{chord: action} from handleMenuShortcut's switch."""
    src = _read(MENUBAR_JS)
    body = src[src.index('handleMenuShortcut(e) {'):]
    body = body[:body.index('\n    }\n')]
    return dict(re.findall(r"case '([\w+]+)': action = '([\w-]+)';", body))


# File-menu accelerators honoured by canvas-input's handleKeyDown instead
# (it owns the Cmd+Z/C/V/J/, family): chord -> (action, the source text
# that handles it there).
CANVAS_INPUT_FILE_CHORDS = {
    'mod+Comma': ('preferences', "e.code === 'Comma'"),
}


def test_file_menu_labels_and_dispatcher_agree():
    """Every accelerator the File menu prints has a case in
    handleMenuShortcut that dispatches that item's action, on both
    platforms' spellings - and every case is printed. A label with no
    case is a promise the app breaks; a case with no label is a hidden
    gesture."""
    labels = _file_menu_labels()
    cases = _dispatcher_cases()
    assert cases == FILE_MENU_SHORTCUTS, cases
    printed = {}
    for action, (mac, win) in labels.items():
        assert (mac is None) == (win is None), (action, mac, win)
        if mac is None:
            continue
        mac_chord = _chord(mac, 'Cmd', 'Option')
        win_chord = _chord(win, 'Ctrl', 'Alt')
        assert mac_chord == win_chord, (action, mac, win)
        printed[mac_chord] = action
    canvas_src = _read(os.path.join(JS_DIR, 'canvas-input.js'))
    for chord, (action, marker) in CANVAS_INPUT_FILE_CHORDS.items():
        assert printed.pop(chord) == action, (chord, action)
        assert marker in canvas_src, (chord, marker)
    assert printed == cases, (printed, cases)


def test_file_new_prints_no_accelerator():
    """The app runs in the user's browser, and Chrome, Edge and Firefox
    reserve Cmd/Ctrl+N (New Window) before the page can see it - so File
    > New must not print a key it can never honour."""
    labels = _file_menu_labels()
    assert 'new' in labels
    assert labels['new'] == (None, None), labels['new']
    assert 'KeyN' not in _read(MENUBAR_JS)


# ── (a) + (b) in the browser ─────────────────────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 850})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def _open(page):
    page.evaluate(f"window.app.handleMenuAction('{MENU_ACTION}')")
    page.wait_for_timeout(200)
    modal = page.locator('#shortcuts-modal')
    assert modal.is_visible(), 'Keyboard Shortcuts modal did not open'
    return modal


def test_modal_opens_with_every_group(page):
    modal = _open(page)
    # innerText carries the h3's text-transform: uppercase, so compare
    # case-blind; the template test pins the exact spelling.
    headings = [h.lower() for h in modal.locator('.sc-group h3').all_inner_texts()]
    assert headings == [h.lower() for h in GROUP_HEADINGS], headings
    page.locator('#shortcuts-close').click()
    page.wait_for_timeout(150)
    assert not modal.is_visible()


def test_modal_lists_every_gesture(page):
    modal = _open(page)
    text = re.sub(r'\s+', ' ', modal.inner_text())
    missing = [p for p in GESTURE_PHRASES if p not in text]
    assert not missing, 'gestures missing from the open modal: ' + repr(missing)
    page.locator('#shortcuts-close').click()


def test_modifier_matches_platform(page):
    modal = _open(page)
    is_mac = page.evaluate(
        "/Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac/.test(navigator.userAgent)")
    mods = set(modal.locator('[data-sc-mod]').all_inner_texts())
    assert mods == {'Cmd' if is_mac else 'Ctrl'}, mods
    # The modal and the menu bar agree.
    undo = page.locator('#menu-edit .menu-option[data-action="undo"]').inner_text()
    assert ('Cmd' in undo) == is_mac, undo
    page.locator('#shortcuts-close').click()


def test_modal_fits_and_scrolls_inside_itself(page):
    """The content box never overflows the window; when taller it scrolls
    inside itself rather than pushing the Close button off-screen."""
    modal = _open(page)
    box = page.evaluate("""() => {
        const c = document.querySelector('#shortcuts-modal .sc-modal');
        const r = c.getBoundingClientRect();
        return { top: r.top, bottom: r.bottom, right: r.right,
                 inner: window.innerHeight, innerW: window.innerWidth,
                 scrolls: c.scrollHeight > c.clientHeight,
                 overflowY: getComputedStyle(c).overflowY };
    }""")
    assert box['top'] >= 0 and box['bottom'] <= box['inner'] + 1, box
    assert box['right'] <= box['innerW'], box
    assert box['overflowY'] == 'auto', box
    page.locator('#shortcuts-close').click()


# ── (d) in the browser: the chords reach handleMenuAction ────────────────

STUB_LEAVES = """() => {
    window.__lrdCalls = [];
    const app = window.app;
    app.saveProjectToFile = () => { window.__lrdCalls.push('save'); return Promise.resolve(); };
    app.loadProjectFromFile = () => { window.__lrdCalls.push('open'); };
    app.openExportModal = (fmt) => { window.__lrdCalls.push('export-' + fmt); };
    if (document.activeElement) document.activeElement.blur();
}"""

# Own-property stubs shadowed the prototype; deleting them restores it.
UNSTUB_LEAVES = """() => {
    delete window.app.saveProjectToFile;
    delete window.app.loadProjectFromFile;
    delete window.app.openExportModal;
    delete window.__lrdCalls;
}"""


@pytest.fixture
def stubbed(page):
    page.evaluate(STUB_LEAVES)
    yield page
    page.evaluate(UNSTUB_LEAVES)


def _mod(page):
    """The modifier the dispatcher honours: it reads the client platform
    through app._isMacPlatform(), the same read the labels are printed
    with (window.LRD_PLATFORM is the server's platform - the same machine
    here, but the keyboard belongs to the client)."""
    return 'Meta' if page.evaluate('window.app._isMacPlatform()') else 'Control'


def _calls(page):
    return page.evaluate('window.__lrdCalls')


def test_mod_s_saves_the_project(stubbed):
    page = stubbed
    page.keyboard.press(f'{_mod(page)}+KeyS')
    page.wait_for_timeout(100)
    assert _calls(page) == ['save']


def test_mod_o_opens_and_is_refused_while_typing(stubbed):
    page = stubbed
    mod = _mod(page)
    page.keyboard.press(f'{mod}+KeyO')
    page.wait_for_timeout(100)
    assert _calls(page) == ['open']

    name = page.locator('#project-name')
    before = name.input_value()
    name.focus()
    page.keyboard.press(f'{mod}+KeyO')
    page.keyboard.press(f'{mod}+KeyS')
    page.keyboard.press('Alt+KeyS')
    page.wait_for_timeout(100)
    assert _calls(page) == ['open'], 'a chord fired out of a text field'
    assert name.input_value() == before
    page.evaluate('document.activeElement.blur()')


def test_alt_s_chords_export(stubbed):
    page = stubbed
    mod = _mod(page)
    page.keyboard.press('Alt+KeyS')
    page.keyboard.press(f'{mod}+Alt+KeyS')
    page.wait_for_timeout(100)
    assert _calls(page) == ['export-png', 'export-psd']


def test_unlabelled_chords_do_nothing(stubbed):
    """Shift added, the other platform's modifier, or a key the menu never
    prints: nothing dispatches."""
    page = stubbed
    mod = _mod(page)
    other = 'Control' if mod == 'Meta' else 'Meta'
    page.keyboard.press(f'{mod}+Shift+KeyS')
    page.keyboard.press(f'{other}+KeyS')
    page.keyboard.press(f'{mod}+KeyN')
    page.wait_for_timeout(100)
    assert _calls(page) == []
