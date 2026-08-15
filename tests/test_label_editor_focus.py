"""Editing a port/circuit label and pressing Tab dropped you out of the panel.

The sequence, in order:

1. You type in a port (or circuit) label field and press Tab.
2. The field's `change` listener writes the override and calls updateLayers(),
   which PUTs the layer to the server.
3. The browser moves focus to the NEXT field immediately - it does not wait
   for anything.
4. A round-trip later the response lands, updateUI() runs, and the editor
   rebuilds itself from scratch: `list.innerHTML = ''` in
   updatePortLabelEditor / updatePowerLabelEditor. That destroys the field you
   are now standing in, and focus falls to <body>.
5. Your next keystroke goes nowhere. Pressing Tab a second time appears to
   work only because an untouched field fires no `change`, so nothing rebuilds.

The socket `layer_updated` echo drives the same rebuild, so the fix cannot key
off which trigger fired: _preserveEditorFocus() snapshots the focused field's
`data-lrd-field` key plus its caret before the wipe and restores it in a
microtask, after the synchronous rebuild has finished.

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


# A screen sized so BOTH editors build the field Tab is supposed to land on.
#
# Both bugs here are about Tab moving to the next field INSIDE the editor, so
# the editor has to have a next field. Left to whatever project the previous
# test file happened to leave on the shared server, a small screen builds a
# single circuit row, Tab lands on #power-line-width outside the list, and the
# power test fails with "Tab left the editor before any rebuild" - passing
# alone and failing in a full run, which is the worst way to find out.
#
# 4x4 of the default 200W cabinet on the default 15A/110V circuit is two
# circuits. Bigger is NOT safer here: 12 wide overruns a single circuit, the
# layer takes a CANNOT FIT COMPLETE ROW error, and the editor renders "No
# circuits to edit." - zero rows, not more of them.
RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
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
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('label_focus_test_reset');
    const screen = app.project.layers.find(l => (l.type || 'screen') === 'screen');
    app.currentLayer = screen;
    app.selectedLayerIds = new Set([screen.id]);
    app.lastSelectedLayerId = screen.id;
    app.renderLayers();
    app.loadLayerToInputs(screen);
    // Both editors size themselves from _portsRequired / _powerCircuitsRequired,
    // which are computed client-side by the capacity passes - a layer fetched
    // straight from the server carries neither, and the power editor renders
    // "No circuits to edit."
    app.updatePortCapacityDisplay();
    app.updatePowerCapacityDisplay();
    app.updatePortLabelEditor();
    app.updatePowerLabelEditor();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return screen.id;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    assert pg.evaluate(RESET_JS), "test project was not created"
    pg.wait_for_timeout(600)
    yield pg
    context.close()


def has_field(page, key):
    return page.evaluate(
        "(k) => !!document.querySelector('[data-lrd-field=\"' + k + '\"]')", key)


def test_the_editors_have_a_field_to_tab_INTO(page):
    """Guard the premise both focus tests rest on: the field Tab moves to has
    to exist, or focus leaves the editor and there is nothing for a rebuild to
    destroy - the tests would pass while proving nothing."""
    _open(page, 'data-flow')
    assert has_field(page, 'port-return-1'), (
        "no Port 1 Return field - Tab out of Port 1 Primary would leave the "
        "editor")
    _open(page, 'power')
    assert has_field(page, 'power-check-2'), (
        "the power editor built a single circuit row - Tab out of Circuit 1's "
        "label lands outside the editor")


# Stamp every field the editor currently holds. Element identity is not
# stable across a rebuild, so a field that still carries the stamp afterwards
# proves the rebuild never happened - and a focus assertion over it would be
# passing for the wrong reason.
STAMP_JS = """(listId) => {
    document.querySelectorAll('#' + listId + ' input')
        .forEach(el => { el.__stamp = 1; });
    return document.querySelectorAll('#' + listId + ' input').length;
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


def _clear_overrides(page):
    """Reset the overrides AND the rendered fields. Clearing only the layer
    would leave the previous test's text sitting in the inputs, so the next
    keyboard.type() would append to it."""
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.portLabelOverridesPrimary = {};
        l.portLabelOverridesReturn = {};
        l.powerLabelOverrides = {};
        window.app.updatePortLabelEditor();
        window.app.updatePowerLabelEditor();
    }""")


# ── The reported bug: Tab, then the panel goes dead ───────────────────────

def test_focus_survives_the_rebuild_that_follows_a_port_label_edit(page):
    """Type in Port 1 Primary, Tab, and wait for the server round-trip to
    rebuild the editor. Focus must still be in a real field."""
    _open(page, 'data-flow')
    _clear_overrides(page)
    page.evaluate("""() => {
        document.querySelector('[data-lrd-field="port-primary-1"]').focus();
    }""")
    assert page.evaluate(STAMP_JS, 'port-label-list') >= 2, \
        "port label editor built no fields - nothing to test"

    page.keyboard.type("SL-A")
    page.keyboard.press("Tab")
    # Tab moved focus to Port 1 Return before any of this resolves.
    assert page.evaluate(FOCUS_JS)['key'] == 'port-return-1'

    _wait_for_rebuild(page, 'port-return-1')
    after = page.evaluate(FOCUS_JS)

    assert not after['isBody'], (
        "focus fell to <body>: the rebuild destroyed the field Tab had just "
        f"moved into. activeElement={after}")
    assert after['tag'] == 'INPUT', f"focus left the editor entirely: {after}"
    assert after['key'] == 'port-return-1', (
        f"focus landed somewhere else after the rebuild: {after}")
    assert not after['stamped'], (
        "the editor never rebuilt, so this test proved nothing - the fixture "
        "or the round-trip changed")


def test_the_edited_port_label_reached_the_layer_and_the_server(page):
    """The focus fix must not cost the edit itself."""
    _open(page, 'data-flow')
    _clear_overrides(page)
    page.evaluate("""() => {
        document.querySelector('[data-lrd-field="port-primary-1"]').focus();
    }""")
    page.evaluate(STAMP_JS, 'port-label-list')
    page.keyboard.type("SL-A")
    page.keyboard.press("Tab")
    _wait_for_rebuild(page, 'port-return-1')

    stored = page.evaluate(
        "() => window.app.currentLayer.portLabelOverridesPrimary")
    assert stored.get('1') == 'SL-A', f"override not on the layer: {stored}"

    field = page.evaluate("""() => {
        const el = document.querySelector('[data-lrd-field="port-primary-1"]');
        return el ? el.value : null;
    }""")
    assert field == 'SL-A', f"rebuilt field lost the text: {field!r}"

    served = page.evaluate("""async () => {
        const id = window.app.currentLayer.id;
        const p = await (await fetch('/api/project')).json();
        const l = (p.layers || []).find(x => x.id === id);
        return l ? l.portLabelOverridesPrimary : null;
    }""")
    assert served and served.get('1') == 'SL-A', (
        f"the edit never reached the server: {served}")


def test_the_caret_position_survives_the_rebuild(page):
    """Restoring focus is not enough - land the caret back where it was, or
    the next keystroke goes to the wrong end of the text."""
    _open(page, 'data-flow')
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.portLabelOverridesPrimary = Object.assign(
            {}, l.portLabelOverridesPrimary, {1: 'ABCDEFG'});
        window.app.updatePortLabelEditor();
    }""")
    page.evaluate("""() => {
        const el = document.querySelector('[data-lrd-field="port-primary-1"]');
        el.focus();
        el.setSelectionRange(3, 3);
    }""")
    page.evaluate(STAMP_JS, 'port-label-list')
    # Rebuild directly: same wipe, no round-trip to wait on.
    page.evaluate("() => window.app.updatePortLabelEditor()")
    _wait_for_rebuild(page, 'port-primary-1')
    after = page.evaluate(FOCUS_JS)

    assert after['key'] == 'port-primary-1', f"focus was not restored: {after}"
    assert after['caret'] == 3, (
        f"caret moved to {after['caret']} - the user's next keystroke would "
        "land in the wrong place")
    _clear_overrides(page)


def test_the_power_circuit_label_editor_behaves_the_same(page):
    """Same builder, same wipe, same bug - the Power tab's circuit labels."""
    _open(page, 'power')
    _clear_overrides(page)
    page.evaluate("""() => {
        document.querySelector('[data-lrd-field="power-label-1"]').focus();
    }""")
    assert has_field(page, 'power-check-2'), (
        "power label editor built a single circuit row - Tab has nowhere to go "
        "inside the editor")
    page.evaluate(STAMP_JS, 'power-label-list')

    page.keyboard.type("C-1")
    page.keyboard.press("Tab")
    moved = page.evaluate(FOCUS_JS)
    assert moved['key'], f"Tab left the editor before any rebuild: {moved}"

    _wait_for_rebuild(page, moved['key'])
    after = page.evaluate(FOCUS_JS)

    assert not after['isBody'], (
        f"focus fell to <body> after the Power editor rebuilt: {after}")
    assert after['tag'] == 'INPUT'
    assert after['key'] == moved['key'], (
        f"focus moved during the rebuild: {moved['key']} -> {after['key']}")
    assert not after['stamped'], "the power editor never rebuilt"

    stored = page.evaluate(
        "() => window.app.currentLayer.powerLabelOverrides")
    assert stored.get('1') == 'C-1', f"circuit override not stored: {stored}"
    _clear_overrides(page)


# ── The helper must be inert when it has nothing to preserve ──────────────

def test_a_rebuild_with_nothing_focused_neither_throws_nor_grabs_focus(page):
    _open(page, 'data-flow')
    result = page.evaluate("""() => {
        document.activeElement && document.activeElement.blur();
        try {
            window.app.updatePortLabelEditor();
            window.app.updatePowerLabelEditor();
            window.app.updatePowerCircuitColorEditor();
        } catch (e) {
            return {error: String(e)};
        }
        return {error: null};
    }""")
    assert result['error'] is None, f"rebuild threw: {result['error']}"
    page.wait_for_timeout(200)
    after = page.evaluate(FOCUS_JS)
    assert after['isBody'] or after['key'] is None, (
        f"an unfocused rebuild pulled focus into the editor: {after}")


def test_a_rebuild_does_not_steal_focus_from_a_field_outside_the_editor(page):
    """Only fields the editor itself owns carry a key; everything else must
    be left exactly where it is."""
    _open(page, 'data-flow')
    page.evaluate("""() => {
        document.getElementById('port-label-template-primary').focus();
    }""")
    page.evaluate("() => window.app.updatePortLabelEditor()")
    page.wait_for_timeout(200)
    after = page.evaluate(FOCUS_JS)
    assert after['id'] == 'port-label-template-primary', (
        f"the rebuild moved focus off an unrelated input: {after}")


def test_a_field_that_no_longer_exists_is_not_restored(page):
    """The port count can shrink between the wipe and the restore. Missing
    field means leave focus alone, not throw."""
    _open(page, 'data-flow')
    result = page.evaluate("""() => {
        const el = document.querySelector('[data-lrd-field="port-primary-1"]');
        el.focus();
        try {
            window.app._preserveEditorFocus();
            // Empty the editor so the key it captured resolves to nothing.
            document.getElementById('port-label-list').innerHTML = '';
        } catch (e) {
            return {error: String(e)};
        }
        return {error: null};
    }""")
    assert result['error'] is None, f"threw during capture: {result['error']}"
    page.wait_for_timeout(200)
    after = page.evaluate(FOCUS_JS)
    assert after['key'] is None, (
        f"restored a field that no longer exists: {after}")
    page.evaluate("() => window.app.updatePortLabelEditor()")
