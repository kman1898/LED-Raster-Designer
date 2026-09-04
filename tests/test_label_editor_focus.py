"""Editing a name in the hardware dock and pressing Tab must not kill focus.

The port and circuit label edits live on the DOCK's chips now: a port renames
in its port chip's editor (keys processor-port-name-<cardId>-<port> /
processor-port-return-<cardId>-<port>), a circuit's label override edits on
its occupied circuit chip (key power-label-<layerId>-<circuit>). The failure
mode those keys guard against is unchanged:

1. You type in a keyed field and press Tab.
2. The field's `change` listener commits the edit - a PUT to
   /api/processors/... for a port, updateLayers() for a circuit label.
3. The browser moves focus to the NEXT field immediately - it does not wait
   for anything.
4. The rebuild lands later - the processor response (renderHardwareDock) or
   the deferred dock rebuild a circuit edit schedules - and wipes
   #hardware-dock-body with innerHTML. That destroys the field you are now
   standing in, and focus falls to <body>.
5. Your next keystroke goes nowhere.

_preserveEditorFocus() snapshots the focused field's `data-lrd-field` key
plus its caret before the wipe and restores it in a microtask, after the
synchronous rebuild has finished; a focused chip FACE rides the same wipe by
its data-hwdock key. These tests pin that contract against the dock fields.

Run locally:
    python -m pytest tests/test_label_editor_focus.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


# A screen plus one processor, so the dock has chips whose editors hold the
# keyed fields under test.
#
# 4x4 of the default 200W cabinet on the default 15A/110V circuit is two
# circuits - so once a distro takes the multi, the dock's grid holds TWO
# occupied circuit chips and Tab out of the first chip's Label field has a
# real stop (the second chip's face) to land on. Bigger is NOT safer here:
# 12 wide overruns a single circuit, the layer takes a CANNOT FIT COMPLETE
# ROW error, and the plan is empty - no occupied chips at all.
#
# The MX20 is an all-in-one with six ports on one fixed card: six port chips,
# each with a Name and a Return field, and no breakout boxes to complicate
# which chip is which.
RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.processors = [];
    project.distros = [];
    delete project.port_assignments;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'LabelFocus',
            columns: 4, rows: 4, cabinet_width: 128, cabinet_height: 128,
        }),
    });
    await fetch('/api/processors', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-mx20', name: 'MX'}),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('label_focus_test_reset');
    const screen = app.project.layers.find(l => (l.type || 'screen') === 'screen');
    // The MX20 is COEX gear, and since the platform wall (2026-08-28) a
    // screen only lands on gear its Processing setting matches - left
    // unset, selecting it below would stamp the prefs default (Legacy)
    // onto it and its ports would have nowhere to land.
    screen.processorType = 'novastar-coex-1g';
    await fetch(`/api/layer/${screen.id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({processorType: 'novastar-coex-1g'}),
    });
    app.currentLayer = screen;
    app.selectedLayerIds = new Set([screen.id]);
    app.lastSelectedLayerId = screen.id;
    app.renderLayers();
    app.loadLayerToInputs(screen);
    // The capacity passes compute _portsRequired / _powerCircuitsRequired
    // client-side - a layer fetched straight from the server carries
    // neither, and the power plan (which sizes the circuit chips) needs
    // them.
    app.updatePortCapacityDisplay();
    app.updatePowerCapacityDisplay();
    await app.refreshProcessors();
    if (window.canvasRenderer) window.canvasRenderer.render();
    const proc = app._processorsResolved[0];
    const card = proc.slots.map(s => s.card).find(Boolean);
    // Nothing lands by itself (auto retired, 2026-09-03): the screen is
    // put on the card by an explicit fill, so the chips under test hold
    // the same occupant the old seed gave them.
    await app._assignmentRequest('/api/port-assignments/place-overflow',
        'POST', {layerId: String(screen.id), cardId: card.id});
    return {screenId: screen.id, procId: proc.id, cardId: card.id};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(RESET_JS)
    assert ids and ids.get('cardId'), f"test project was not created: {ids}"
    pg.wait_for_timeout(600)
    yield pg, ids
    context.close()


def has_field(page, key):
    return page.evaluate(
        "(k) => !!document.querySelector('[data-lrd-field=\"' + k + '\"]')", key)


# Stamp every field the dock body currently holds. Element identity is not
# stable across a rebuild, so a field that still carries the stamp afterwards
# proves the rebuild never happened - and a focus assertion over it would be
# passing for the wrong reason.
STAMP_JS = """() => {
    document.querySelectorAll('#hardware-dock-body input')
        .forEach(el => { el.__stamp = 1; });
    return document.querySelectorAll('#hardware-dock-body input').length;
}"""

FOCUS_JS = """() => {
    const a = document.activeElement;
    let caret = null;
    try { caret = a.selectionStart; } catch (e) { caret = null; }
    return {
        tag: a ? a.tagName : null,
        type: a ? a.type : null,
        key: (a && a.dataset) ? (a.dataset.lrdField || null) : null,
        isBody: a === document.body,
        id: a ? a.id : null,
        caret: caret,
        stamped: !!(a && a.__stamp),
    };
}"""


def _open(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(400)


def _wait_for_rebuild(page, key):
    """Block until the field with this key is a freshly built element."""
    page.wait_for_function(
        """(key) => {
            const el = document.querySelector('[data-lrd-field="' + key + '"]');
            return !!el && !el.__stamp;
        }""",
        arg=key,
        timeout=5000,
    )


def _chip_is_open(page, tile_key):
    return page.evaluate(
        """(k) => {
            const t = document.querySelector(`[data-lrd-tile="${k}"]`);
            return !!t && t.classList.contains('lrd-tile-open');
        }""", tile_key)


def _open_port_chip(page, card_id, port):
    """Open a port chip's editor the way a user does: a click on its face.
    Idempotent - the face click is a toggle, so an already-open chip is
    left alone rather than closed."""
    tile_key = f'port-{card_id}-{port}'
    if _chip_is_open(page, tile_key):
        return
    # An open neighbour grows past the dock body's visible area, so scroll
    # the face into view first - what locator.click() would do anyway, made
    # explicit so a miss fails here with the chip's name.
    page.evaluate(
        """(k) => {
            const el = document.querySelector(`[data-hwdock="${k}"]`);
            if (el) el.scrollIntoView({block: 'nearest'});
        }""", tile_key)
    page.locator(f'[data-hwdock="{tile_key}"]').click()
    page.wait_for_timeout(250)
    assert _chip_is_open(page, tile_key), f'chip {tile_key} did not open'


def test_the_dock_chips_have_a_field_to_tab_INTO(page):
    """Guard the premise the focus tests rest on: Tab out of a chip's Name
    field has to land on its Return field, or focus leaves the editor and
    there is nothing for a rebuild to destroy - the tests would pass while
    proving nothing. The fields exist (hidden, never detached) even while
    the chip is closed, so no click is needed to check."""
    pg, ids = page
    _open(pg, 'data-flow')
    assert has_field(pg, f'processor-port-name-{ids["cardId"]}-1'), (
        "no port 1 Name field - the MX20's card built no port chips")
    assert has_field(pg, f'processor-port-return-{ids["cardId"]}-1'), (
        "no port 1 Return field - Tab out of the Name field would leave the "
        "chip's editor")


# ── The reported bug: Tab, then the editor goes dead ──────────────────────

def test_focus_survives_the_rebuild_that_follows_a_port_name_edit(page):
    """Type in port 1's Name field, Tab, and wait for the processor
    round-trip to rebuild the dock. Focus must still be in a real field."""
    pg, ids = page
    _open(pg, 'data-flow')
    _open_port_chip(pg, ids['cardId'], 1)
    name_key = f'processor-port-name-{ids["cardId"]}-1'
    return_key = f'processor-port-return-{ids["cardId"]}-1'
    pg.evaluate(
        "(k) => document.querySelector('[data-lrd-field=\"' + k + '\"]')"
        ".focus()", name_key)
    assert pg.evaluate(STAMP_JS) >= 2, \
        "the dock built no fields - nothing to test"

    pg.keyboard.type("SL-A")
    pg.keyboard.press("Tab")
    # Tab moved focus to the chip's Return field before any of this resolves.
    assert pg.evaluate(FOCUS_JS)['key'] == return_key

    _wait_for_rebuild(pg, return_key)
    after = pg.evaluate(FOCUS_JS)

    assert not after['isBody'], (
        "focus fell to <body>: the rebuild destroyed the field Tab had just "
        f"moved into. activeElement={after}")
    assert after['tag'] == 'INPUT', f"focus left the editor entirely: {after}"
    assert after['key'] == return_key, (
        f"focus landed somewhere else after the rebuild: {after}")
    assert not after['stamped'], (
        "the dock never rebuilt, so this test proved nothing - the fixture "
        "or the round-trip changed")


def test_the_edited_port_name_reached_the_card_and_the_server(page):
    """The focus fix must not cost the edit itself. Port 2, so the previous
    test's text is not sitting in the field being typed into."""
    pg, ids = page
    _open(pg, 'data-flow')
    _open_port_chip(pg, ids['cardId'], 2)
    name_key = f'processor-port-name-{ids["cardId"]}-2'
    return_key = f'processor-port-return-{ids["cardId"]}-2'
    pg.evaluate(
        "(k) => document.querySelector('[data-lrd-field=\"' + k + '\"]')"
        ".focus()", name_key)
    pg.evaluate(STAMP_JS)
    pg.keyboard.type("SL-B")
    pg.keyboard.press("Tab")
    _wait_for_rebuild(pg, return_key)

    field = pg.evaluate(
        """(k) => {
            const el = document.querySelector('[data-lrd-field="' + k + '"]');
            return el ? el.value : null;
        }""", name_key)
    assert field == 'SL-B', f"rebuilt field lost the text: {field!r}"

    served = pg.evaluate("""async () => {
        const d = await (await fetch('/api/processors')).json();
        const card = ((d.processors || [])[0] || {slots: []}).slots
            .map(s => s.card).find(Boolean);
        return card ? (card.portNames || {}) : null;
    }""")
    assert served and served.get('2') == 'SL-B', (
        f"the edit never reached the server's card: {served}")


def test_the_caret_position_survives_the_rebuild(page):
    """Restoring focus is not enough - land the caret back where it was, or
    the next keystroke goes to the wrong end of the text. Driven through a
    direct renderHardwareDock(): the same wipe, no round-trip to wait on."""
    pg, ids = page
    _open(pg, 'data-flow')
    # Name port 3 through the API so the rebuilt field carries the text the
    # caret is being placed in - a value typed only into the DOM would come
    # back empty from the render and clamp the caret to 0.
    pg.evaluate(
        """async ([procId, cardId]) => {
            await fetch(`/api/processors/${procId}/cards/${cardId}/ports/3`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'ABCDEFG'}),
            });
            await window.app.refreshProcessors();
        }""", [ids['procId'], ids['cardId']])
    pg.wait_for_timeout(400)
    _open_port_chip(pg, ids['cardId'], 3)
    name_key = f'processor-port-name-{ids["cardId"]}-3'
    pg.evaluate(
        """(k) => {
            const el = document.querySelector('[data-lrd-field="' + k + '"]');
            el.focus();
            el.setSelectionRange(3, 3);
        }""", name_key)
    pg.evaluate(STAMP_JS)
    pg.evaluate("() => window.app.renderHardwareDock()")
    _wait_for_rebuild(pg, name_key)
    after = pg.evaluate(FOCUS_JS)

    assert after['key'] == name_key, f"focus was not restored: {after}"
    assert after['caret'] == 3, (
        f"caret moved to {after['caret']} - the user's next keystroke would "
        "land in the wrong place")


def test_the_circuit_label_editor_behaves_the_same(page):
    """The power side of the same contract: an occupied circuit chip's Label
    field commits to the HOLDER layer and schedules a deferred dock rebuild
    (_rebuildAfterGesture), and focus must ride that wipe too."""
    pg, ids = page
    seeded = pg.evaluate(
        """(screenId) => {
            const app = window.app;
            const layer = app.project.layers.find(l => l.id === screenId);
            app.currentLayer = layer;
            const d = app.getDistros()[0] || app.addDistro({name: 'PD'});
            const plan = app.getSocaPlan(layer);
            if (!plan.length) return null;
            app.setSocaDistro(layer, plan[0].soca, d.id);
            app._restateNaming();
            return {distroId: d.id, legs: plan[0].legs.length};
        }""", ids['screenId'])
    assert seeded, "the screen has no soca plan - no circuits to label"
    assert seeded['legs'] >= 2, (
        f"a single-circuit plan leaves Tab nowhere to go inside the dock's "
        f"grid: {seeded}")
    _open(pg, 'power')
    pg.wait_for_timeout(400)

    # The first occupied circuit chip; a free tail has no editor at all.
    face = pg.locator('[data-lrd-tile^="ptail-"] > .lrd-tile-face').first
    face.scroll_into_view_if_needed()
    face.click()
    pg.wait_for_timeout(250)
    key = pg.evaluate("""() => {
        const tile = document.querySelector('.lrd-tile-open[data-lrd-tile^="ptail-"]');
        const el = tile
            && tile.querySelector('[data-lrd-field^="power-label-"]');
        return el ? el.dataset.lrdField : null;
    }""")
    assert key, "the circuit chip opened no Label field"
    circuit = key.rsplit('-', 1)[1]

    pg.evaluate(
        "(k) => document.querySelector('[data-lrd-field=\"' + k + '\"]')"
        ".focus()", key)
    pg.evaluate(STAMP_JS)
    pg.keyboard.type("C-1")
    pg.keyboard.press("Tab")

    _wait_for_rebuild(pg, key)
    after = pg.evaluate(FOCUS_JS)
    assert not after['isBody'] and after['tag'] is not None, (
        f"focus fell to <body> after the deferred dock rebuild: {after}")

    stored = pg.evaluate(
        """(screenId) => {
            const l = window.app.project.layers.find(x => x.id === screenId);
            return l.powerLabelOverrides || {};
        }""", ids['screenId'])
    assert stored.get(circuit) == 'C-1', (
        f"circuit override not on the holder layer: {stored}")


# ── The helper must be inert when it has nothing to preserve ──────────────

def test_a_rebuild_with_nothing_focused_neither_throws_nor_grabs_focus(page):
    pg, ids = page
    _open(pg, 'data-flow')
    result = pg.evaluate("""() => {
        document.activeElement && document.activeElement.blur();
        try {
            window.app.renderHardwareDock();
            // The retired list editors survive as no-op stubs; every
            // "labels may have moved" path still calls them, so they must
            // stay safe to call.
            window.app.updatePortLabelEditor();
            window.app.updatePowerLabelEditor();
            window.app.updatePowerCircuitColorEditor();
        } catch (e) {
            return {error: String(e)};
        }
        return {error: null};
    }""")
    assert result['error'] is None, f"rebuild threw: {result['error']}"
    pg.wait_for_timeout(200)
    after = pg.evaluate(FOCUS_JS)
    assert after['isBody'] or after['key'] is None, (
        f"an unfocused rebuild pulled focus into the dock: {after}")


def test_a_rebuild_does_not_steal_focus_from_a_field_outside_the_dock(page):
    """Only fields the dock's editors own carry a key; everything else must
    be left exactly where it is. The Fallback Labels template box in the
    left sidebar's Data Settings panel is the nearest neighbour."""
    pg, ids = page
    _open(pg, 'data-flow')
    pg.evaluate("""() => {
        document.getElementById('port-label-template-primary').focus();
    }""")
    pg.evaluate("() => window.app.renderHardwareDock()")
    pg.wait_for_timeout(200)
    after = pg.evaluate(FOCUS_JS)
    assert after['id'] == 'port-label-template-primary', (
        f"the rebuild moved focus off an unrelated input: {after}")


def test_a_field_that_no_longer_exists_is_not_restored(page):
    """The chip a key names can vanish between the wipe and the restore -
    the processor removed, the view left. Missing field means leave focus
    alone, not throw."""
    pg, ids = page
    _open(pg, 'data-flow')
    _open_port_chip(pg, ids['cardId'], 1)
    name_key = f'processor-port-name-{ids["cardId"]}-1'
    result = pg.evaluate(
        """(k) => {
            const el = document.querySelector('[data-lrd-field="' + k + '"]');
            el.focus();
            try {
                window.app._preserveEditorFocus();
                // Empty the dock so the key it captured resolves to nothing.
                document.getElementById('hardware-dock-body').innerHTML = '';
            } catch (e) {
                return {error: String(e)};
            }
            return {error: null};
        }""", name_key)
    assert result['error'] is None, f"threw during capture: {result['error']}"
    pg.wait_for_timeout(200)
    after = pg.evaluate(FOCUS_JS)
    assert after['key'] is None, (
        f"restored a field that no longer exists: {after}")
    pg.evaluate("() => window.app.renderHardwareDock()")
