"""Screen groups (v0.10.9) - the Screens sidebar UI (Playwright).

Step 1 built the model, step 2 the combined totals. This file covers step 3:
a group presented and acted on as A SINGLE LAYER - one collapsed row carrying
the wall's combined figures, whole-group visibility / lock / delete /
duplicate / z-order, Screen Info edits that reach every member, and the
settings-mismatch dialog.

Three things these tests pin deliberately:

* ONE UNDO STEP. Group / ungroup / rename / add / remove / apply-settings each
  record exactly one history entry, and undoing it restores the whole action -
  including each member's original processor settings when the dialog changed
  them. Asserted as a history LENGTH delta, so an action that quietly records
  two entries fails here rather than surfacing as "undo does half a thing".
* UI state is read from classList / textContent / getComputedStyle, never from
  el.style.*. A v0.10.9 rename cue shipped broken precisely because its test
  read the inline style it had just written, while theme.css painted over it.
* SHARED vs PER MEMBER. A wall-level setting written on one member reaches all
  of them; a grid-level one (columns, cabinet size, offsets) must not. Both
  directions are asserted, because only testing the first would let an
  over-eager propagation quietly flatten the two cabinet sizes the group
  exists to hold.

Run locally:
    python -m pytest tests/test_screen_groups_ui.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """One long-lived page; each test resets to a known project first."""
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# ── helpers ───────────────────────────────────────────────────────────────

RESET_JS = """async (count) => {
    const app = window.app;
    // The live server is shared with every other browser test file, and by the
    // time this module runs the project holds whatever they left behind -
    // including hand-built layers with no color1/color2, which the renderer
    // cannot draw. Clear the layer list outright and build exactly `count`
    // screens through the real add endpoint, so every assertion below is about
    // layers this module created.
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (let i = 0; i < count; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'GroupTest' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('screen_group_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, count);
    screens.forEach(l => {
        l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60;
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(app.project),
    });
    app.currentLayer = screens[0];
    app.selectedLayerIds = new Set([screens[0].id]);
    // Land any debounced snapshot still in flight from boot BEFORE rebasing,
    // otherwise it fires later and shows up as a second history entry against
    // whichever group action ran first.
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Test Reset');
    app.renderLayers();
    return screens.map(l => l.id);
}"""


def reset_project(page, count=3):
    """Deterministic starting point: exactly `count` ungrouped screens with
    matching settings, and a history containing one entry.

    Returns those `count` ids and no others - the shared server may hold
    layers left by another browser test file, and an assertion written against
    "every screen in the project" would then be testing their state too."""
    ids = page.evaluate(RESET_JS, count)
    page.wait_for_timeout(700)
    assert len(ids) == count, ids
    return ids


def select(page, ids):
    page.evaluate(
        "(ids) => window.app.setSelectedLayersByIds(ids, ids[0])", ids)
    page.wait_for_timeout(200)


def history_len(page):
    return page.evaluate("window.app.history.length")


def history_actions(page):
    """Every recorded action, so a "one undo step" failure names the entry
    that snuck in rather than just reporting a count."""
    return page.evaluate("window.app.history.map(h => h.action)")


def group_model(page):
    """Both sides of the relationship, as the client currently holds them."""
    return page.evaluate("""() => ({
        groups: (window.app.project.groups || []).map(g => ({
            id: g.id, name: g.name, layer_ids: g.layer_ids })),
        membership: Object.fromEntries(window.app.project.layers.map(
            l => [l.id, l.group_id ?? null])),
        lastAction: window.app.history[window.app.history.length - 1].action,
    })""")


def server_groups(page):
    return page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        return {
            groups: p.groups || [],
            membership: Object.fromEntries(
                p.layers.map(l => [l.id, l.group_id ?? null])),
        };
    }""")


def settings_of(page, ids):
    return page.evaluate("""(ids) => ids.map(id => {
        const l = window.app.project.layers.find(x => x.id === id);
        return {processorType: l.processorType, bitDepth: l.bitDepth,
                frameRate: l.frameRate};
    })""", ids)


def undo(page):
    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(900)


def dialog_visible(page):
    return page.evaluate("""() => {
        const m = document.getElementById('group-settings-modal');
        return !!m && getComputedStyle(m).display !== 'none';
    }""")


# ── grouping matching screens ─────────────────────────────────────────────


def test_group_two_matching_layers_is_one_undo_step(page):
    """Two screens that already agree group with no dialog, write BOTH sides,
    and cost exactly one history entry that undo fully reverses."""
    ids = reset_project(page)[:2]
    select(page, ids)
    before = history_len(page)

    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    assert not dialog_visible(page), 'matching screens should not need a dialog'
    model = group_model(page)
    assert len(model['groups']) == 1, model
    group = model['groups'][0]
    assert group['layer_ids'] == ids, model
    assert [model['membership'][str(i)] for i in ids] == [group['id']] * 2, model
    assert history_len(page) == before + 1, (
        f"expected ONE undo step, history went {before} -> "
        f"{history_len(page)}: {history_actions(page)}")
    assert model['lastAction'] == 'Group Screens', model

    stored = server_groups(page)
    assert [g['id'] for g in stored['groups']] == [group['id']], stored

    undo(page)
    after = group_model(page)
    assert after['groups'] == [], after
    assert [after['membership'][str(i)] for i in ids] == [None, None], after


def test_group_is_one_collapsed_row_carrying_the_walls_totals(page):
    """A group is a single layer. It gets ONE row - the group's name and its
    COMBINED figures - and the members it is built from start hidden behind a
    disclosure arrow."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    dom = page.evaluate("""() => {
        const el = document.querySelector('#layers-list .screen-group');
        if (!el) return null;
        const body = el.querySelector('.screen-group-body');
        const toggle = el.querySelector('.screen-group-toggle');
        const gid = el.dataset.groupId;
        const totals = window.app.getGroupTotals(gid);
        const members = window.app.getGroupMembers(gid);
        return {
            groupId: gid,
            name: el.querySelector('.screen-group-name-input').value,
            info: el.querySelector('.screen-group-info').textContent.trim(),
            collapsed: el.classList.contains('collapsed'),
            bodyDisplay: getComputedStyle(body).display,
            toggleExpanded: toggle.getAttribute('aria-expanded'),
            toggleGlyph: toggle.textContent.trim(),
            memberIds: [...body.querySelectorAll('.layer-item')]
                .map(n => parseInt(n.dataset.layerId, 10)),
            memberMarked: [...body.querySelectorAll('.layer-item')]
                .every(n => n.classList.contains('grouped')),
            insideCanvas: !!el.closest('.canvas-group-body'),
            cabinets: totals.cabinets,
            memberCabinets: members.reduce((sum, m) => sum
                + (m.panels || []).filter(p => !p.blank && !p.hidden).length, 0),
            // Members must no longer be top-level rows in the canvas. Checked
            // by id rather than by counting rows, because the shared server
            // may hold unrelated screens from another test file.
            membersStillTopLevel: [...document.querySelectorAll(
                '#layers-list .canvas-group-body > .layer-item')]
                .map(n => parseInt(n.dataset.layerId, 10)),
        };
    }""")
    assert dom, 'no .screen-group rendered in the layer list'
    assert dom['name'].startswith('Group '), dom
    # Collapsed by default: the members are how the wall was built, not what
    # the user is managing.
    assert dom['collapsed'], dom
    assert dom['bodyDisplay'] == 'none', dom
    assert dom['toggleExpanded'] == 'false', dom
    assert dom['toggleGlyph'] == '\u25b8', dom
    # The row carries the COMBINED figure, not one member's.
    assert dom['cabinets'] == dom['memberCabinets'], dom
    assert f"{dom['cabinets']} cab" in dom['info'], dom
    assert ' kg' in dom['info'] or ' lb' in dom['info'], dom
    # Members are reachable but no longer top-level rows in the canvas.
    assert dom['memberIds'] == list(reversed(ids)), dom
    assert dom['memberMarked'], dom
    assert dom['insideCanvas'], 'group did not nest inside its canvas group'
    assert not set(ids) & set(dom['membersStillTopLevel']), (
        'grouped members are still top-level rows: %r' % (dom,))


def test_disclosure_arrow_reveals_the_members(page):
    """Expanding is a view cursor: it shows the members and records no undo."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    before = history_len(page)

    page.locator('.screen-group-toggle').click()
    page.wait_for_timeout(300)
    opened = page.evaluate("""() => {
        const el = document.querySelector('.screen-group');
        return {
            collapsed: el.classList.contains('collapsed'),
            bodyDisplay: getComputedStyle(
                el.querySelector('.screen-group-body')).display,
            expanded: el.querySelector('.screen-group-toggle')
                .getAttribute('aria-expanded'),
            glyph: el.querySelector('.screen-group-toggle').textContent.trim(),
        };
    }""")
    assert opened['collapsed'] is False, opened
    assert opened['bodyDisplay'] != 'none', opened
    assert opened['expanded'] == 'true', opened
    assert opened['glyph'] == '\u25be', opened
    assert history_len(page) == before, history_actions(page)

    # The state survives a re-render, so an edit does not slam the group shut.
    page.evaluate("window.app.renderLayers()")
    page.wait_for_timeout(300)
    assert page.evaluate(
        "!document.querySelector('.screen-group').classList.contains('collapsed')")

    page.locator('.screen-group-toggle').click()
    page.wait_for_timeout(300)
    assert page.evaluate(
        "document.querySelector('.screen-group').classList.contains('collapsed')")


def test_group_row_reads_like_a_screen_row(page):
    """A group IS a single layer, so its row wears the layer tile treatment
    rather than the canvas group's colored identity band."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    res = page.evaluate("""() => {
        const g = document.querySelector('.screen-group-row');
        const c = document.querySelector('.canvas-group-header');
        const l = document.querySelector('.screen-group-body .layer-item');
        if (!g || !c || !l) return null;
        const bg = el => getComputedStyle(el).backgroundImage + '|'
            + getComputedStyle(el).backgroundColor;
        return {
            group: bg(g), canvas: bg(c), layer: bg(l),
            hasHeader: !!g.querySelector('.layer-header'),
            hasInfo: !!g.querySelector('.layer-info'),
            controls: [...g.querySelectorAll('.layer-controls button')]
                .map(b => b.className.split(' ').find(c => c.startsWith('screen-group-'))
                          || b.className),
        };
    }""")
    assert res, 'rows not found'
    assert res['group'] != res['canvas'], res
    assert res['group'] == res['layer'], (
        'the group row does not read like a screen row: %r' % (res,))
    assert res['hasHeader'] and res['hasInfo'], res
    assert 'screen-group-move-up' in res['controls'], res
    assert 'screen-group-vis-btn' in res['controls'], res
    assert 'screen-group-menu-btn' in res['controls'], res


# ── the mismatch dialog ───────────────────────────────────────────────────


def start_group(page):
    """Kick the group action off WITHOUT awaiting it. page.evaluate awaits a
    returned Promise, and the one groupSelectedLayers() hands back does not
    settle until the mismatch dialog is answered."""
    page.evaluate("() => { window.app.groupSelectedLayers(); }")


def _make_mismatch(page):
    """Two screens differing on processor + bit depth, agreeing on frame
    rate. Returns their ids.

    The mismatch is persisted and history re-based afterwards, so the entry an
    undo steps back ONTO is the mismatched state - which is what makes "undo
    restores the members' original settings" a real assertion."""
    ids = reset_project(page)[:2]
    page.evaluate("""async (ids) => {
        const l = window.app.project.layers.find(x => x.id === ids[1]);
        l.processorType = 'novastar-5g';
        l.bitDepth = 12;
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.app.project),
        });
        window.app.resetHistory('Test Mismatch');
    }""", ids)
    select(page, ids)
    return ids


def test_mismatch_dialog_lists_only_the_differing_fields(page):
    ids = _make_mismatch(page)
    start_group(page)
    page.wait_for_timeout(500)

    assert dialog_visible(page), 'mismatch dialog did not open'
    dom = page.evaluate("""() => {
        const rows = [...document.querySelectorAll(
            '#group-settings-conflicts .group-settings-row')];
        return {
            fields: rows.map(r => r.dataset.field),
            labels: rows.map(r => r.querySelector('label').textContent),
            options: Object.fromEntries(rows.map(r => [
                r.dataset.field,
                [...r.querySelectorAll('option')].map(o => o.textContent),
            ])),
            matching: [...document.querySelectorAll('.group-settings-match')]
                .map(m => m.textContent),
            note: document.getElementById('group-settings-note').textContent,
            sublabel: document.getElementById('group-settings-sublabel').textContent,
            apply: document.getElementById('group-settings-apply').textContent,
        };
    }""")
    assert dom['fields'] == ['processorType', 'bitDepth'], dom
    assert dom['labels'] == ['Processor', 'Bit Depth'], dom
    assert dom['options']['processorType'] == [
        'Brompton Tessera', 'NovaStar COEX CX40 (5G)'], dom
    assert dom['options']['bitDepth'] == ['10-bit', '12-bit'], dom
    # frameRate matched, so it is confirmation text, not a chooser.
    assert dom['matching'] == ['Frame Rate: 60 Hz'], dom
    assert '2 screens' in dom['sublabel'], dom
    assert dom['note'] == 'Cancel leaves the screens ungrouped and unchanged.'
    assert dom['apply'] == 'Apply to Group'

    page.evaluate("document.getElementById('group-settings-cancel').click()")
    page.wait_for_timeout(600)


def test_mismatch_apply_writes_both_members_in_one_undo_step(page):
    """Applying writes the chosen values to EVERY member and creates the group
    as one undoable action - and undo restores the grouping AND the original
    per-member settings."""
    ids = _make_mismatch(page)
    original = settings_of(page, ids)
    before = history_len(page)

    start_group(page)
    page.wait_for_timeout(500)
    assert dialog_visible(page)

    page.evaluate("""() => {
        const pick = (field, label) => {
            const sel = document.querySelector(
                `#group-settings-conflicts .group-settings-select[data-field="${field}"]`);
            const opt = [...sel.options].find(o => o.textContent === label);
            sel.value = opt.value;
        };
        pick('processorType', 'NovaStar COEX CX40 (5G)');
        pick('bitDepth', '12-bit');
        document.getElementById('group-settings-apply').click();
    }""")
    page.wait_for_timeout(1000)

    assert not dialog_visible(page)
    after = settings_of(page, ids)
    assert all(s['processorType'] == 'novastar-5g' for s in after), after
    assert all(s['bitDepth'] == 12 for s in after), after
    assert all(s['frameRate'] == 60 for s in after), after

    model = group_model(page)
    assert len(model['groups']) == 1, model
    assert model['groups'][0]['layer_ids'] == ids, model
    assert history_len(page) == before + 1, (
        f"apply + group must be ONE undo step, history went "
        f"{before} -> {history_len(page)}: {history_actions(page)}")
    assert model['lastAction'] == 'Group Screens', model

    undo(page)
    assert group_model(page)['groups'] == [], 'undo left the group behind'
    assert settings_of(page, ids) == original, (
        'undo did not restore the members original processor settings')


def test_mismatch_cancel_groups_nothing_and_changes_nothing(page):
    ids = _make_mismatch(page)
    original = settings_of(page, ids)
    before = history_len(page)

    start_group(page)
    page.wait_for_timeout(500)
    assert dialog_visible(page)
    page.evaluate("document.getElementById('group-settings-cancel').click()")
    page.wait_for_timeout(700)

    assert not dialog_visible(page)
    assert group_model(page)['groups'] == []
    assert settings_of(page, ids) == original
    assert history_len(page) == before, 'cancel recorded a history entry'
    assert server_groups(page)['groups'] == []


def test_adding_a_mismatched_layer_runs_the_same_check(page):
    """The settings check is not a create-time-only gate: a screen joining an
    existing group still has to agree with the screens already in it."""
    ids = reset_project(page)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    group_id = group_model(page)['groups'][0]['id']

    page.evaluate("""(id) => {
        window.app.project.layers.find(l => l.id === id).bitDepth = 8;
    }""", ids[2])
    select(page, [ids[2]])
    page.evaluate("(gid) => { window.app.addSelectedToGroup(gid); }", group_id)
    page.wait_for_timeout(500)

    assert dialog_visible(page), 'add-to-group skipped the settings check'
    dom = page.evaluate("""() => ({
        fields: [...document.querySelectorAll(
            '#group-settings-conflicts .group-settings-row')]
            .map(r => r.dataset.field),
        note: document.getElementById('group-settings-note').textContent,
    })""")
    assert dom['fields'] == ['bitDepth'], dom
    assert dom['note'] == 'Cancel leaves the group and the screens unchanged.'

    page.evaluate("document.getElementById('group-settings-cancel').click()")
    page.wait_for_timeout(600)
    assert group_model(page)['groups'][0]['layer_ids'] == ids[:2]


# ── add / remove / ungroup / rename ───────────────────────────────────────


def test_add_and_remove_a_member_are_one_undo_step_each(page):
    ids = reset_project(page)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    group_id = group_model(page)['groups'][0]['id']

    select(page, [ids[2]])
    before = history_len(page)
    page.evaluate("(gid) => window.app.addSelectedToGroup(gid)", group_id)
    page.wait_for_timeout(900)
    model = group_model(page)
    assert model['groups'][0]['layer_ids'] == ids, model
    assert model['membership'][str(ids[2])] == group_id, model
    assert history_len(page) == before + 1, history_actions(page)
    assert model['lastAction'] == 'Add to Group', model

    before = history_len(page)
    page.evaluate("window.app.removeSelectedFromGroup()")
    page.wait_for_timeout(900)
    model = group_model(page)
    assert model['groups'][0]['layer_ids'] == ids[:2], model
    assert model['membership'][str(ids[2])] is None, model
    assert history_len(page) == before + 1, history_actions(page)
    assert model['lastAction'] == 'Remove from Group', model

    undo(page)
    assert group_model(page)['groups'][0]['layer_ids'] == ids


def test_ungroup_clears_both_sides(page):
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    before = history_len(page)
    page.evaluate("window.app.ungroupSelectedLayers()")
    page.wait_for_timeout(900)

    model = group_model(page)
    assert model['groups'] == [], model
    assert [model['membership'][str(i)] for i in ids] == [None, None], model
    assert history_len(page) == before + 1, history_actions(page)
    assert model['lastAction'] == 'Ungroup Screens', model
    stored = server_groups(page)
    assert stored['groups'] == [], stored
    assert [stored['membership'][str(i)] for i in ids] == [None, None], stored
    assert page.evaluate(
        "document.querySelectorAll('#layers-list .screen-group').length") == 0


def test_removing_down_to_one_member_dissolves_the_group(page):
    """The server owns that rule (_enforce_group_integrity), and the client
    has to end up agreeing with it rather than showing a group of one."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    select(page, [ids[0]])
    page.evaluate("window.app.removeSelectedFromGroup()")
    page.wait_for_timeout(900)

    model = group_model(page)
    assert model['groups'] == [], model
    assert [model['membership'][str(i)] for i in ids] == [None, None], model


def test_rename_persists_and_is_one_undo_step(page):
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    group_id = group_model(page)['groups'][0]['id']

    before = history_len(page)
    page.evaluate("(gid) => window.app.renameGroup(gid, 'Main Wall')", group_id)
    page.wait_for_timeout(900)

    model = group_model(page)
    assert model['groups'][0]['name'] == 'Main Wall', model
    assert history_len(page) == before + 1, history_actions(page)
    assert model['lastAction'] == 'Rename Group', model
    assert page.evaluate(
        "document.querySelector('.screen-group-name-input').value") == 'Main Wall'
    stored = server_groups(page)
    assert stored['groups'][0]['name'] == 'Main Wall', stored

    undo(page)
    assert group_model(page)['groups'][0]['name'] != 'Main Wall'


def test_rename_edit_cue_is_a_class_not_an_inline_style(page):
    """Same trap the layer and canvas rename cues fell into: theme.css styles
    the field with !important, so the cue has to ride on `.editing`."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    res = page.evaluate("""() => {
        const i = document.querySelector('.screen-group-name-input');
        if (!i) return null;
        const snap = () => {
            const s = getComputedStyle(i);
            return {bc: s.borderColor, bg: s.backgroundColor};
        };
        i.classList.remove('editing'); const plain = snap();
        i.classList.add('editing');    const edit = snap();
        i.classList.remove('editing');
        return {plain, edit};
    }""")
    assert res, 'group name input not found'
    assert res['edit']['bc'] != res['plain']['bc'], res
    assert res['edit']['bg'] != res['plain']['bg'], res


# ── refusals ──────────────────────────────────────────────────────────────


def test_grouping_fewer_than_two_layers_is_not_offered(page):
    ids = reset_project(page)
    select(page, [ids[0]])

    assert page.evaluate("window.app.canGroupSelection()") is False
    page.evaluate("window.app.showContextMenu(40, 40)")
    page.wait_for_timeout(200)
    visible = page.evaluate("""() => {
        const el = document.querySelector('#context-menu .group-create-only');
        return el ? getComputedStyle(el).display !== 'none' : null;
    }""")
    assert visible is False, 'Group Screens offered for a single screen'
    page.evaluate("window.app.hideContextMenu()")

    before = history_len(page)
    result = page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(500)
    assert result is None, 'a group of one was created'
    assert group_model(page)['groups'] == []
    assert history_len(page) == before


def test_group_actions_appear_only_for_a_grouped_selection(page):
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    page.evaluate("window.app.showContextMenu(40, 40)")
    page.wait_for_timeout(200)
    shown = page.evaluate("""() => Object.fromEntries(
        [...document.querySelectorAll('#context-menu .menu-option[data-action]')]
            .filter(el => ['group-screens', 'ungroup-screens',
                           'remove-from-group'].includes(el.dataset.action))
            .map(el => [el.dataset.action,
                        getComputedStyle(el).display !== 'none']))""")
    page.evaluate("window.app.hideContextMenu()")
    # The whole selection IS the group, so there is nothing new to make.
    assert shown['group-screens'] is False, shown
    assert shown['ungroup-screens'] is True, shown
    assert shown['remove-from-group'] is True, shown


# ── round trip ────────────────────────────────────────────────────────────


def test_group_survives_a_save_and_reload(page, e2e_server):
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    page.evaluate("(gid) => window.app.renameGroup(gid, 'Round Trip')",
                  group_model(page)['groups'][0]['id'])
    page.wait_for_timeout(900)

    # Save through the same endpoint the client saves through, then boot a
    # fresh page against the server so nothing in-memory can carry the group.
    page.evaluate("""async () => {
        await fetch('/api/project', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.app.project),
        });
    }""")
    page.wait_for_timeout(400)

    fresh = page.context.new_page()
    fresh.goto(e2e_server, wait_until='domcontentloaded')
    fresh.wait_for_timeout(2500)
    reloaded = fresh.evaluate("""(ids) => ({
        groups: (window.app.project.groups || []).map(
            g => ({id: g.id, name: g.name, layer_ids: g.layer_ids})),
        membership: ids.map(id => {
            const l = window.app.project.layers.find(x => x.id === id);
            return l ? (l.group_id ?? null) : 'missing';
        }),
        rendered: document.querySelectorAll('#layers-list .screen-group').length,
        renderedName: (document.querySelector('.screen-group-name-input') || {}).value,
    })""", ids)
    fresh.close()

    assert len(reloaded['groups']) == 1, reloaded
    assert reloaded['groups'][0]['name'] == 'Round Trip', reloaded
    assert reloaded['groups'][0]['layer_ids'] == ids, reloaded
    assert reloaded['membership'] == [reloaded['groups'][0]['id']] * 2, reloaded
    assert reloaded['rendered'] == 1, reloaded
    assert reloaded['renderedName'] == 'Round Trip', reloaded


def test_group_ids_are_never_reused(page):
    """Mirrors sync_next_group_seq server-side: delete a group, make a new
    one, and the new one must not answer to the dead one's id."""
    ids = reset_project(page)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    first = group_model(page)['groups'][0]['id']

    page.evaluate("window.app.ungroupSelectedLayers()")
    page.wait_for_timeout(900)
    select(page, ids[1:3])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)

    second = group_model(page)['groups'][0]['id']
    assert second != first, f'group id {first} was handed out twice'


# ── the group acts as ONE layer ───────────────────────────────────────────
#
# Visibility, lock, delete, duplicate and z-order all operate on the whole
# wall. Each is asserted to be exactly one undo step, because "delete removed
# both halves but undo only brought one back" is the failure that would make
# groups untrustworthy.


def _grouped_pair(page):
    """Reset, group the two oldest screens, return (ids, group_id)."""
    ids = reset_project(page)[:2]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    return ids, group_model(page)['groups'][0]['id']


def visibility_of(page, ids):
    return page.evaluate("""(ids) => ids.map(id => {
        const l = window.app.project.layers.find(x => x.id === id);
        return l ? (l.visible !== false) : 'missing';
    })""", ids)


def test_one_eye_hides_the_whole_group(page):
    ids, gid = _grouped_pair(page)
    assert visibility_of(page, ids) == [True, True]
    before = history_len(page)

    page.locator('.screen-group-vis-btn').click()
    page.wait_for_timeout(900)

    assert visibility_of(page, ids) == [False, False], 'group left half-drawn'
    assert history_len(page) == before + 1, history_actions(page)
    assert group_model(page)['lastAction'] == 'Hide Group'
    dom = page.evaluate("""() => {
        const el = document.querySelector('.screen-group');
        return {
            hidden: el.classList.contains('hidden'),
            badge: el.querySelector('.layer-hidden-badge') !== null,
            btn: el.querySelector('.screen-group-vis-btn').classList.contains('is-hidden'),
        };
    }""")
    assert dom['hidden'] and dom['badge'] and dom['btn'], dom

    undo(page)
    assert visibility_of(page, ids) == [True, True], 'undo restored half a wall'

    # And the toggle brings the whole wall back too.
    page.evaluate("(g) => window.app.toggleGroupVisibility(g)", gid)
    page.wait_for_timeout(900)
    page.evaluate("(g) => window.app.toggleGroupVisibility(g)", gid)
    page.wait_for_timeout(900)
    assert visibility_of(page, ids) == [True, True]


def test_one_lock_locks_the_whole_group(page):
    ids, gid = _grouped_pair(page)
    before = history_len(page)

    page.evaluate("(g) => window.app.toggleGroupLock(g)", gid)
    page.wait_for_timeout(900)
    locked = page.evaluate("""(ids) => ids.map(id => !!window.app.project.layers
        .find(x => x.id === id).locked)""", ids)
    assert locked == [True, True], locked
    assert history_len(page) == before + 1, history_actions(page)
    assert group_model(page)['lastAction'] == 'Lock Group'
    assert page.evaluate(
        "document.querySelector('.screen-group-lock-badge') !== null")

    page.evaluate("(g) => window.app.toggleGroupLock(g)", gid)
    page.wait_for_timeout(900)
    assert page.evaluate("""(ids) => ids.map(id => !!window.app.project.layers
        .find(x => x.id === id).locked)""", ids) == [False, False]


def test_delete_removes_every_member_in_one_undo_step(page):
    ids, gid = _grouped_pair(page)
    before_count = page.evaluate("window.app.project.layers.length")
    before = history_len(page)

    page.evaluate("(g) => window.app.deleteGroup(g)", gid)
    page.wait_for_timeout(900)

    state = page.evaluate("""(ids) => ({
        count: window.app.project.layers.length,
        survivors: ids.filter(id => window.app.project.layers.some(l => l.id === id)),
        groups: (window.app.project.groups || []).length,
        rendered: document.querySelectorAll('#layers-list .screen-group').length,
    })""", ids)
    assert state['survivors'] == [], state
    assert state['count'] == before_count - 2, state
    assert state['groups'] == 0, state
    assert state['rendered'] == 0, state
    assert history_len(page) == before + 1, history_actions(page)
    assert group_model(page)['lastAction'] == 'Delete Group'

    undo(page)
    restored = page.evaluate("""(ids) => ({
        survivors: ids.filter(id => window.app.project.layers.some(l => l.id === id)),
        groups: (window.app.project.groups || []).map(g => g.layer_ids),
    })""", ids)
    assert restored['survivors'] == ids, restored
    assert restored['groups'] == [ids], restored


def test_duplicate_copies_the_wall_and_regroups_the_copies(page):
    ids, gid = _grouped_pair(page)
    before_count = page.evaluate("window.app.project.layers.length")
    before = history_len(page)

    page.evaluate("(g) => window.app.duplicateGroup(g)", gid)
    page.wait_for_timeout(1100)

    state = page.evaluate("""(args) => {
        const [ids, gid] = args;
        const groups = window.app.project.groups || [];
        const copy = groups.find(g => g.id !== gid) || null;
        return {
            count: window.app.project.layers.length,
            groupCount: groups.length,
            copyMembers: copy ? copy.layer_ids.length : 0,
            copyName: copy ? copy.name : null,
            copyIsNew: copy ? copy.layer_ids.every(id => !ids.includes(id)) : false,
            membershipOk: copy ? copy.layer_ids.every(id => window.app.project.layers
                .find(l => l.id === id).group_id === copy.id) : false,
            renderedGroups: document.querySelectorAll('#layers-list .screen-group').length,
        };
    }""", [ids, gid])
    assert state['count'] == before_count + 2, state
    assert state['groupCount'] == 2, state
    assert state['copyMembers'] == 2, 'the copies were not regrouped'
    assert state['copyIsNew'], state
    assert state['membershipOk'], state
    assert state['renderedGroups'] == 2, state
    assert history_len(page) == before + 1, history_actions(page)
    assert group_model(page)['lastAction'] == 'Duplicate Group'

    undo(page)
    after = page.evaluate("""() => ({
        count: window.app.project.layers.length,
        groups: (window.app.project.groups || []).length,
    })""")
    assert after['count'] == before_count, after
    assert after['groups'] == 1, after


# ── z-order: the group moves as one block ─────────────────────────────────


def display_ids(page):
    """Layer ids in sidebar order (newest on top), from the project itself."""
    return page.evaluate(
        "[...window.app.project.layers].reverse().map(l => l.id)")


def test_the_group_moves_up_and_down_as_one_block(page):
    ids = reset_project(page)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    gid = group_model(page)['groups'][0]['id']
    loose = ids[2]

    order = display_ids(page)
    assert order.index(ids[1]) + 1 == order.index(ids[0]), order

    before = history_len(page)
    page.evaluate("(g) => window.app.moveGroupWithinCanvas(g, -1)", gid)
    page.wait_for_timeout(700)
    moved = display_ids(page)
    # The whole block hopped over the loose screen, and stayed a block.
    assert moved.index(ids[1]) < moved.index(loose), moved
    assert moved.index(ids[0]) < moved.index(loose), moved
    assert abs(moved.index(ids[0]) - moved.index(ids[1])) == 1, moved
    assert history_len(page) == before + 1, history_actions(page)

    page.evaluate("(g) => window.app.moveGroupWithinCanvas(g, 1)", gid)
    page.wait_for_timeout(700)
    assert display_ids(page) == order, display_ids(page)


def test_a_reorder_can_never_split_a_group(page):
    """Every reorder path funnels through applyDisplayOrder, so dropping an
    unrelated screen between two members has to be undone there."""
    ids = reset_project(page)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    loose = ids[2]

    # Ask for an order that puts the loose screen BETWEEN the members.
    page.evaluate("(order) => window.app.applyDisplayOrder(order, 'Test Split')",
                  [ids[1], loose, ids[0]])
    page.wait_for_timeout(700)

    order = display_ids(page)
    assert abs(order.index(ids[0]) - order.index(ids[1])) == 1, (
        'an unrelated screen was left inside the group: %r' % (order,))
    assert loose in order, order
    # And the sidebar still shows exactly one group row with both members.
    dom = page.evaluate("""() => {
        const el = document.querySelector('#layers-list .screen-group');
        return el ? el.querySelectorAll('.screen-group-body .layer-item').length : 0;
    }""")
    assert dom == 2, dom


# ── Screen Info: shared vs per member ─────────────────────────────────────


def field_of(page, ids, field):
    return page.evaluate("""(args) => {
        const [ids, field] = args;
        return ids.map(id => (window.app.project.layers
            .find(l => l.id === id) || {})[field]);
    }""", [ids, field])


def test_a_wall_level_setting_reaches_every_member(page):
    """Bit depth is a processor rule for the whole wall. Editing it with only
    ONE member selected has to move the other one too, in the same undo step."""
    ids, gid = _grouped_pair(page)
    select(page, [ids[0]])
    assert field_of(page, ids, 'bitDepth') == [10, 10]
    before = history_len(page)

    page.evaluate("""() => {
        const sel = document.getElementById('bit-depth');
        sel.value = '12';
        sel.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_timeout(900)

    assert field_of(page, ids, 'bitDepth') == [12, 12], (
        'the peer did not follow the wall-level edit')
    assert history_len(page) == before + 1, history_actions(page)

    stored = page.evaluate("""async (ids) => {
        const p = await (await fetch('/api/project')).json();
        return ids.map(id => (p.layers.find(l => l.id === id) || {}).bitDepth);
    }""", ids)
    assert stored == [12, 12], f'the peer never reached the server: {stored}'

    undo(page)
    assert field_of(page, ids, 'bitDepth') == [10, 10], 'undo restored half a wall'


def test_a_grid_level_setting_stays_on_its_own_member(page):
    """Columns is the whole reason the wall needed two layers. Propagating it
    would flatten the two cabinet sizes the group exists to hold."""
    ids, gid = _grouped_pair(page)
    select(page, [ids[0]])
    before_cols = field_of(page, ids, 'columns')
    before_cabinet = field_of(page, ids, 'cabinet_width')

    page.evaluate("""(n) => {
        const el = document.getElementById('screen-columns');
        el.value = String(n);
        window.app._lastChangedInputId = 'screen-columns';
        el.dispatchEvent(new Event('change'));
    }""", before_cols[0] + 3)
    page.wait_for_timeout(900)

    after_cols = field_of(page, ids, 'columns')
    assert after_cols[0] == before_cols[0] + 3, after_cols
    assert after_cols[1] == before_cols[1], (
        f'columns leaked to the peer: {before_cols} -> {after_cols}')
    assert field_of(page, ids, 'cabinet_width') == before_cabinet, (
        'cabinet size leaked to the peer')


def test_an_unrelated_edit_does_not_repaint_the_peers(page):
    """Propagation diffs rather than blanket-copies: nudging one member must
    not force its peer to adopt every shared value it happened to differ on."""
    ids, gid = _grouped_pair(page)
    # Make the two disagree on a shared field WITHOUT going through an edit
    # funnel, exactly as two independently-built screens would.
    page.evaluate("""(ids) => {
        window.app.project.layers.find(l => l.id === ids[1]).labelsFontSize = 44;
        window.app.project.layers.find(l => l.id === ids[0]).labelsFontSize = 12;
    }""", ids)
    select(page, [ids[0]])

    page.evaluate("""() => {
        const el = document.getElementById('offset-x');
        el.value = '77';
        window.app._lastChangedInputId = 'offset-x';
        el.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_timeout(900)

    sizes = field_of(page, ids, 'labelsFontSize')
    assert sizes[1] == 44, (
        f'an unrelated edit repainted the peer: {sizes}')


def test_the_shared_field_list_excludes_the_per_cabinet_figures(page):
    """A 1m JP5 and a 0.5m standard cabinet do not weigh or draw the same, and
    getGroupTotals sums each member's own figure - so these can never be
    treated as wall-level."""
    shared = page.evaluate("window.app.GROUP_SHARED_LAYER_FIELDS")
    for field in ('columns', 'rows', 'cabinet_width', 'cabinet_height',
                  'panel_width_mm', 'panel_height_mm', 'panel_weight',
                  'panelWatts', 'offset_x', 'offset_y', 'showOffsetX',
                  'showOffsetY', 'rotation', 'panels', 'customPortPaths',
                  'name', 'visible', 'locked', 'group_id', 'canvas_id'):
        assert field not in shared, f'{field} must stay per member'
    for field in ('processorType', 'bitDepth', 'frameRate', 'color1', 'color2',
                  'powerVoltage', 'flowPattern', 'showLabelName',
                  'labelsFontSize', 'panel_border_width'):
        assert field in shared, f'{field} should be shared across the wall'


# ── N members, and more than one group ────────────────────────────────────
#
# The model has never been pair-shaped, but a UI easily becomes so: a
# "2 screens" string, one shared expand flag, a menu popup reused by id, or a
# validate that compares the first two members and stops.


def test_a_group_holds_any_number_of_members(page):
    """Four screens selected at once become ONE group of four - not two pairs,
    and not just the first two."""
    ids = reset_project(page, 5)[:4]
    select(page, ids)
    before = history_len(page)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(1100)

    model = group_model(page)
    assert len(model['groups']) == 1, model
    assert sorted(model['groups'][0]['layer_ids']) == sorted(ids), model
    assert [model['membership'][str(i)] for i in ids] == [model['groups'][0]['id']] * 4
    assert history_len(page) == before + 1, history_actions(page)

    dom = page.evaluate("""() => {
        const el = document.querySelector('#layers-list .screen-group');
        const totals = window.app.getGroupTotals(el.dataset.groupId);
        const members = window.app.getGroupMembers(el.dataset.groupId);
        return {
            info: el.querySelector('.screen-group-info').textContent.trim(),
            memberRows: el.querySelectorAll('.screen-group-body .layer-item').length,
            cabinets: totals.cabinets,
            memberCabinets: members.reduce((sum, m) => sum
                + (m.panels || []).filter(p => !p.blank && !p.hidden).length, 0),
            groupRows: document.querySelectorAll('#layers-list .screen-group').length,
        };
    }""")
    assert dom['groupRows'] == 1, dom
    assert dom['memberRows'] == 4, dom
    assert '4 screens' in dom['info'], dom
    # The combined figure is the sum across ALL FOUR, not a pair.
    assert dom['cabinets'] == dom['memberCabinets'], dom
    assert f"{dom['cabinets']} cab" in dom['info'], dom


def test_adding_to_a_group_of_three_keeps_one_group(page):
    ids = reset_project(page, 5)
    select(page, ids[:3])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(1100)
    gid = group_model(page)['groups'][0]['id']
    assert len(group_model(page)['groups'][0]['layer_ids']) == 3

    select(page, [ids[3]])
    before = history_len(page)
    page.evaluate("(g) => window.app.addSelectedToGroup(g)", gid)
    page.wait_for_timeout(1100)

    model = group_model(page)
    assert len(model['groups']) == 1, model
    assert sorted(model['groups'][0]['layer_ids']) == sorted(ids[:4]), model
    assert history_len(page) == before + 1, history_actions(page)
    assert '4 screens' in page.evaluate(
        "document.querySelector('.screen-group-info').textContent"), 'count is stale'


def test_removing_from_a_group_of_four_leaves_a_group_of_three(page):
    """Only fewer than two dissolves a group. The client must not dissolve
    early - that rule belongs to _enforce_group_integrity."""
    ids = reset_project(page, 5)[:4]
    select(page, ids)
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(1100)
    gid = group_model(page)['groups'][0]['id']

    select(page, [ids[0]])
    page.evaluate("window.app.removeSelectedFromGroup()")
    page.wait_for_timeout(1000)

    model = group_model(page)
    assert len(model['groups']) == 1, 'the group was dissolved early'
    assert sorted(model['groups'][0]['layer_ids']) == sorted(ids[1:]), model
    assert model['membership'][str(ids[0])] is None, model
    assert model['groups'][0]['id'] == gid, model
    assert '3 screens' in page.evaluate(
        "document.querySelector('.screen-group-info').textContent")

    stored = server_groups(page)
    assert len(stored['groups']) == 1, stored
    assert sorted(stored['groups'][0]['layer_ids']) == sorted(ids[1:]), stored


def test_two_groups_coexist_without_sharing_state(page):
    """Each group gets its own row, name, expand state and menu. A single
    shared collapsed flag or an id-reused popup shows up here."""
    ids = reset_project(page, 5)
    select(page, ids[:2])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(1000)
    select(page, ids[2:4])
    page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(1000)

    model = group_model(page)
    assert len(model['groups']) == 2, model
    gids = [g['id'] for g in model['groups']]
    assert gids[0] != gids[1], model
    assert model['groups'][0]['name'] != model['groups'][1]['name'], model
    # group_id stays single-valued: no layer is claimed by both.
    owned = [lid for g in model['groups'] for lid in g['layer_ids']]
    assert len(owned) == len(set(owned)) == 4, model

    # Rows are read in DOM order, which is newest-on-top - i.e. the SECOND
    # group made is the first row. Everything below keys off what each row
    # actually holds rather than assuming creation order.
    rows = page.evaluate("""() => [...document.querySelectorAll(
        '#layers-list .screen-group')].map(el => ({
            id: el.dataset.groupId,
            name: el.querySelector('.screen-group-name-input').value,
            collapsed: el.classList.contains('collapsed'),
            members: el.querySelectorAll('.screen-group-body .layer-item').length,
            memberIds: [...el.querySelectorAll('.screen-group-body .layer-item')]
                .map(n => parseInt(n.dataset.layerId, 10)).sort((a, b) => a - b),
        }))""")
    assert len(rows) == 2, rows
    assert rows[0]['id'] != rows[1]['id'], rows
    assert all(r['collapsed'] for r in rows), rows
    assert all(r['members'] == 2 for r in rows), rows

    # Expanding one must not expand the other.
    page.evaluate("(g) => window.app.setGroupExpanded(g, true)", rows[0]['id'])
    page.wait_for_timeout(200)
    state = page.evaluate("""() => [...document.querySelectorAll(
        '#layers-list .screen-group')].map(el => ({
            id: el.dataset.groupId,
            collapsed: el.classList.contains('collapsed'),
            bodyDisplay: getComputedStyle(
                el.querySelector('.screen-group-body')).display,
        }))""")
    opened = [s for s in state if s['id'] == rows[0]['id']][0]
    other = [s for s in state if s['id'] == rows[1]['id']][0]
    assert opened['collapsed'] is False and opened['bodyDisplay'] != 'none', state
    assert other['collapsed'] is True and other['bodyDisplay'] == 'none', state

    # Renaming one must not rename the other.
    page.evaluate("(g) => window.app.renameGroup(g, 'North Wall')", rows[0]['id'])
    page.wait_for_timeout(1000)
    names = page.evaluate("""() => Object.fromEntries(
        [...document.querySelectorAll('#layers-list .screen-group')].map(el => [
            el.dataset.groupId,
            el.querySelector('.screen-group-name-input').value]))""")
    assert names[rows[0]['id']] == 'North Wall', names
    assert names[rows[1]['id']] != 'North Wall', names

    # Each row's ⋮ opens ONE popup, and opening the second closes the first.
    page.evaluate("""() => document.querySelectorAll(
        '.screen-group .screen-group-menu-btn')[0].click()""")
    page.wait_for_timeout(200)
    assert page.evaluate(
        "document.querySelectorAll('.screen-group-menu-popup').length") == 1
    page.evaluate("""() => document.querySelectorAll(
        '.screen-group .screen-group-menu-btn')[1].click()""")
    page.wait_for_timeout(200)
    assert page.evaluate(
        "document.querySelectorAll('.screen-group-menu-popup').length") == 1
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)

    # And deleting one leaves the other completely intact.
    page.evaluate("(g) => window.app.deleteGroup(g)", rows[0]['id'])
    page.wait_for_timeout(1100)
    after = group_model(page)
    assert len(after['groups']) == 1, after
    assert after['groups'][0]['id'] == rows[1]['id'], after
    assert sorted(after['groups'][0]['layer_ids']) == rows[1]['memberIds'], after
    # ...and only the deleted group's screens are gone.
    survivors = page.evaluate(
        "(ids) => ids.filter(id => window.app.project.layers.some(l => l.id === id))",
        ids[:4])
    assert sorted(survivors) == rows[1]['memberIds'], survivors


def test_the_mismatch_dialog_reads_every_member_not_just_the_first_two(page):
    """Three members, three different processors: the chooser has to offer all
    three values, and applying has to write the choice to all three."""
    ids = reset_project(page, 5)[:3]
    page.evaluate("""async (ids) => {
        const byId = (id) => window.app.project.layers.find(l => l.id === id);
        byId(ids[0]).processorType = 'brompton';
        byId(ids[1]).processorType = 'novastar-5g';
        byId(ids[2]).processorType = 'megapixel-1g';
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.app.project),
        });
        window.app.resetHistory('Test Mismatch N');
    }""", ids)
    select(page, ids)
    before = history_len(page)
    start_group(page)
    page.wait_for_timeout(600)

    assert dialog_visible(page)
    dom = page.evaluate("""() => {
        const rows = [...document.querySelectorAll(
            '#group-settings-conflicts .group-settings-row')];
        return {
            fields: rows.map(r => r.dataset.field),
            options: [...rows[0].querySelectorAll('option')].map(o => o.textContent),
            sublabel: document.getElementById('group-settings-sublabel').textContent,
        };
    }""")
    assert dom['fields'] == ['processorType'], dom
    assert dom['options'] == [
        'Brompton Tessera', 'NovaStar COEX CX40 (5G)', 'Megapixel HELIOS (1G)'], dom
    assert '3 screens' in dom['sublabel'], dom

    page.evaluate("""() => {
        const sel = document.querySelector(
            '#group-settings-conflicts .group-settings-select[data-field="processorType"]');
        sel.value = [...sel.options].find(
            o => o.textContent === 'Megapixel HELIOS (1G)').value;
        document.getElementById('group-settings-apply').click();
    }""")
    page.wait_for_timeout(1100)

    assert field_of(page, ids, 'processorType') == ['megapixel-1g'] * 3
    assert len(group_model(page)['groups'][0]['layer_ids']) == 3
    assert history_len(page) == before + 1, history_actions(page)
