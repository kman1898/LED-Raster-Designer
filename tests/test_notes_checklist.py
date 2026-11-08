"""The show to-do checklist under the Notes panel's free text.

project.notesChecklist = [{id, text, done}], in order. Pinned here:

* add / tick / edit / remove / drag-reorder, each through the panel the way
  a hand does it, each ONE undo step that undo and redo walk;
* a ticked item reads struck through;
* Enter in an item's text is the app's one rule - it commits and lets go -
  and adds no row;
* the list reaches the server (PUT /api/project/notes-checklist) and every
  other client (`notes_checklist_updated`), undo included;
* it rides File > Save / Open, and a project from before the checklist
  opens unchanged with an empty list.

Run locally:
    python -m pytest tests/test_notes_checklist.py -v --browser chromium
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _new_page(pw_browser, url):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');"
        "localStorage.setItem('ledRasterPanelCollapsed_notes','0');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    pg.wait_for_timeout(800)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    delete project.notesChecklist;
    project.notes = '';
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(project)});
    app.project = await (await fetch('/api/project')).json();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.updateUI();
    app.resetHistory('Test Reset');
    const panel = document.getElementById('notes-panel');
    if (panel.classList.contains('collapsed')) document.getElementById('notes-panel-header').click();
    // Give the list room to work in, whatever edge the panel sits on.
    panel.style.height = '420px';
    panel.style.maxHeight = 'none';
}"""


def reset(page):
    page.evaluate(RESET_JS)
    page.wait_for_timeout(300)


def model(page):
    return page.evaluate(
        "() => (window.app.project.notesChecklist || []).map(i => [i.text, i.done])")


def ui_rows(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '#notes-checklist-list .notes-checklist-row')).map(r => [
            r.querySelector('.notes-checklist-text').value,
            r.querySelector('.notes-checklist-done').checked])""")


def server_list(page):
    return page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        return (p.notesChecklist || []).map(i => [i.text, i.done]);
    }""")


def history_len(page):
    return page.evaluate("window.app.history.length")


def add_item(page, text):
    page.click('#notes-checklist-add')
    field = page.locator('#notes-checklist-list .notes-checklist-row').last.locator('.notes-checklist-text')
    assert page.evaluate("document.activeElement.classList.contains('notes-checklist-text')")
    field.type(text)
    field.press('Enter')
    page.wait_for_timeout(150)


def row(page, n):
    return page.locator('#notes-checklist-list .notes-checklist-row').nth(n)


def undo(page):
    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(500)


def redo(page):
    page.evaluate("window.app.handleMenuAction('redo')")
    page.wait_for_timeout(500)


# ── the edits ─────────────────────────────────────────────────────────────

def test_add_item_commits_on_enter_and_adds_no_row(page):
    reset(page)
    before = history_len(page)
    add_item(page, 'Check fiber')
    assert model(page) == [['Check fiber', False]]
    assert ui_rows(page) == [['Check fiber', False]]
    # Enter let go of the field and did not open another row.
    assert not page.evaluate("document.activeElement.classList.contains('notes-checklist-text')")
    assert page.locator('#notes-checklist-list .notes-checklist-row').count() == 1
    # Add + its text: two steps.
    assert history_len(page) == before + 2, page.evaluate("window.app.history.map(h => h.action)")
    assert settled(page, lambda: server_list(page), lambda v: v == [['Check fiber', False]]) \
        == [['Check fiber', False]]
    assert page.locator('#notes-checklist .notes-checklist-title').text_content() == 'Checklist 0/1'


def test_check_strikes_through_and_is_one_undo_step(page):
    reset(page)
    add_item(page, 'Patch power')
    before = history_len(page)
    row(page, 0).locator('.notes-checklist-done').click()
    assert model(page) == [['Patch power', True]]
    assert history_len(page) == before + 1
    deco = page.evaluate("""() => getComputedStyle(document.querySelector(
        '#notes-checklist-list .notes-checklist-row .notes-checklist-text')).textDecorationLine""")
    assert 'line-through' in deco
    assert page.locator('#notes-checklist .notes-checklist-title').text_content() == 'Checklist 1/1'
    assert settled(page, lambda: server_list(page), lambda v: v == [['Patch power', True]]) \
        == [['Patch power', True]]
    undo(page)
    assert model(page) == [['Patch power', False]]
    assert ui_rows(page) == [['Patch power', False]]
    assert settled(page, lambda: server_list(page), lambda v: v == [['Patch power', False]]) \
        == [['Patch power', False]]
    redo(page)
    assert model(page) == [['Patch power', True]]


def test_edit_text_commits_on_leaving_and_escape_reverts(page):
    reset(page)
    add_item(page, 'Rig')
    field = row(page, 0).locator('.notes-checklist-text')
    field.click()
    field.fill('Rig the wall')
    field.press('Tab')
    page.wait_for_timeout(150)
    assert model(page) == [['Rig the wall', False]]
    field.click()
    field.fill('something else')
    field.press('Escape')
    page.wait_for_timeout(150)
    assert model(page) == [['Rig the wall', False]]
    assert ui_rows(page) == [['Rig the wall', False]]
    undo(page)
    assert model(page) == [['Rig', False]]
    assert ui_rows(page) == [['Rig', False]]


def test_delete_item(page):
    reset(page)
    add_item(page, 'One')
    add_item(page, 'Two')
    before = history_len(page)
    row(page, 0).hover()
    row(page, 0).locator('.notes-checklist-remove').click()
    assert model(page) == [['Two', False]]
    assert ui_rows(page) == [['Two', False]]
    assert history_len(page) == before + 1
    undo(page)
    assert model(page) == [['One', False], ['Two', False]]


def test_drag_reorders_before_and_after(page):
    reset(page)
    for t in ('A', 'B', 'C'):
        add_item(page, t)
    before = history_len(page)
    # C onto A's upper half: before A.
    target = row(page, 0)
    box = target.bounding_box()
    row(page, 2).locator('.notes-checklist-handle').drag_to(
        target, target_position={'x': box['width'] / 2, 'y': 2})
    page.wait_for_timeout(200)
    assert [t for t, _ in model(page)] == ['C', 'A', 'B']
    assert [t for t, _ in ui_rows(page)] == ['C', 'A', 'B']
    assert history_len(page) == before + 1
    # C onto B's lower half: after B (last).
    target = row(page, 2)
    box = target.bounding_box()
    row(page, 0).locator('.notes-checklist-handle').drag_to(
        target, target_position={'x': box['width'] / 2, 'y': box['height'] - 2})
    page.wait_for_timeout(200)
    assert [t for t, _ in model(page)] == ['A', 'B', 'C']
    # Rows are not draggable outside a handle press: text stays selectable.
    assert page.evaluate("""() => Array.from(document.querySelectorAll(
        '#notes-checklist-list .notes-checklist-row')).every(r => !r.draggable)""")
    undo(page)
    assert [t for t, _ in model(page)] == ['C', 'A', 'B']
    assert settled(page, lambda: [t for t, _ in server_list(page)],
                   lambda v: v == ['C', 'A', 'B']) == ['C', 'A', 'B']


def test_text_is_never_markup(page):
    reset(page)
    add_item(page, '<img src=x onerror="window.__pwned=1"> & co')
    assert model(page) == [['<img src=x onerror="window.__pwned=1"> & co', False]]
    assert page.locator('#notes-checklist-list img').count() == 0
    assert not page.evaluate("window.__pwned === 1")


# ── other clients ─────────────────────────────────────────────────────────

def test_other_clients_follow_edits_and_undo(page, e2e_server, pw_browser):
    reset(page)
    context, other = _new_page(pw_browser, e2e_server)
    try:
        add_item(page, 'Shared item')
        got = settled(other, lambda: model(other), lambda v: v == [['Shared item', False]])
        assert got == [['Shared item', False]]
        assert ui_rows(other) == [['Shared item', False]]
        row(page, 0).locator('.notes-checklist-done').click()
        got = settled(other, lambda: ui_rows(other), lambda v: v == [['Shared item', True]])
        assert got == [['Shared item', True]]
        undo(page)
        got = settled(other, lambda: ui_rows(other), lambda v: v == [['Shared item', False]])
        assert got == [['Shared item', False]]
        # And back the other way.
        row(other, 0).locator('.notes-checklist-done').click()
        got = settled(page, lambda: ui_rows(page), lambda v: v == [['Shared item', True]])
        assert got == [['Shared item', True]]
    finally:
        context.close()


# ── save / open ───────────────────────────────────────────────────────────

def _load_file(pg, project, name='file.json'):
    """Drive File > Open with an in-memory project, the way the user does."""
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("() => window.app.loadProjectFromFile()")
    chooser.value.set_files({'name': name, 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_timeout(2000)


def test_checklist_rides_save_and_open(page):
    reset(page)
    add_item(page, 'First')
    add_item(page, 'Second')
    row(page, 1).locator('.notes-checklist-done').click()
    saved = json.loads(page.evaluate("window.app.serializeProjectForFile()"))
    assert [(i['text'], i['done']) for i in saved['notesChecklist']] == [('First', False), ('Second', True)]
    assert all(i['id'] for i in saved['notesChecklist'])

    reset(page)
    assert ui_rows(page) == []
    _load_file(page, saved)
    assert model(page) == [['First', False], ['Second', True]]
    assert ui_rows(page) == [['First', False], ['Second', True]]
    assert settled(page, lambda: server_list(page),
                   lambda v: v == [['First', False], ['Second', True]]) == [['First', False], ['Second', True]]


def test_a_project_from_before_the_checklist_opens_unchanged(page):
    reset(page)
    add_item(page, 'Left over')
    old = json.loads(page.evaluate("window.app.serializeProjectForFile()"))
    old.pop('notesChecklist', None)
    old['notes'] = 'Old notes'
    _load_file(page, old, name='old.json')
    assert page.evaluate("'notesChecklist' in window.app.project") is False or model(page) == []
    assert ui_rows(page) == []
    assert page.input_value('#project-notes') == 'Old notes'
    assert page.locator('#notes-checklist .notes-checklist-title').text_content() == 'Checklist'
    # The server copy keeps the file's shape: no list was invented for it.
    page.wait_for_timeout(500)
    served = page.evaluate("async () => (await (await fetch('/api/project')).json())")
    assert served.get('notesChecklist') in (None, [])


def test_route_cleans_what_it_stores(client):
    res = client.put('/api/project/notes-checklist', json={'items': 'nope'})
    assert res.status_code == 400
    res = client.put('/api/project/notes-checklist', json={'items': [
        {'id': 'a', 'text': 'x' * 900, 'done': 1},
        'junk',
        {'id': 'a', 'text': 5, 'done': True},
        {'text': 'no id'},
    ]})
    assert res.status_code == 200
    items = res.get_json()['items']
    assert len(items) == 3
    assert len(items[0]['text']) == 500 and items[0]['done'] is False
    assert items[1]['text'] == '' and items[1]['done'] is True
    assert len({i['id'] for i in items}) == 3
    assert client.get('/api/project').get_json()['notesChecklist'] == items
