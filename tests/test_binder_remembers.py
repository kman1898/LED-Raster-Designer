"""The binder remembers each show's export (owner, 1.7.0): "when exporting
to binder the options I select like hardware and fiber need to be
remembered. So if I want to export again it has the same settings for that
project. New projects reset these check boxes." Then: "Same thing when
using logos added to binders".

- A WHOLE-SHOW export from the Export dialog keeps its palette, maps and
  six sheet ticks on the show (project.binder.sheets), in the one undo
  entry the export's revision takes. The dialog opens on them again, after
  a reload, and in the file. Ticking boxes and cancelling writes nothing.
- A show with none (a new show, an older show) opens on the Binder
  preferences, as before.
- A single-screen export writes nothing: its show sheets start unticked
  whatever the show keeps, and the show's choices stand.
- The logo is the show's (project.binder.logo): set on one show, a new
  show has none, the first show still has it. A show saved before 1.7.0
  with no logo of its own takes the one the old preference holds, once,
  as it opens. The Preferences dialog has no logo row any more.

Run locally:
    python -m pytest tests/test_binder_remembers.py -v --browser chromium
"""

import base64
import io
import json

import pytest

from conftest import open_app  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder import SEED_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and its preferences) the way this
    module found them."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    # no real save dialog may pop on the machine running this
    body = json.dumps({'ok': False, 'cancelled': True})
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}',
                      lambda route: route.fulfill(status=200, content_type='application/json', body=body))
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    open_app(pg, e2e_server)
    yield pg, errors
    context.close()


# The Binder preferences this module runs under, stated rather than
# inherited from whatever ran before: every sheet on, Color, both maps.
PREFS = {'binderPalette': 'colour', 'binderMaps': 'both', 'binderCover': True, 'binderPull': True,
         'binderHardware': True, 'binderWiring': True, 'binderFiber': True, 'binderRigging': True,
         'binderLogo': ''}
PREF_CHOICES = {'palette': 'colour', 'maps': 'both', 'cover': True, 'pull': True, 'hardware': True,
                'wiring': True, 'fiber': True, 'rigging': True}

SET_PREFS_JS = """async (patch) => {
    const app = window.app;
    const prefs = { ...app.getPreferences(), ...patch };
    app._serverPreferences = prefs;
    try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (_) {}
    await fetch('/api/preferences', { method: 'PUT', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify(prefs) });
}"""

# The PDF route and the picker stubbed: the export runs whole, nothing is
# written to disk. Installed again after every reload.
STUB_JS = """() => {
    const app = window.app;
    if (window.__binderStubbed) return;
    window.__binderStubbed = true;
    const realFetch = window.fetch;
    window.__binderPosts = 0;
    window.fetch = async (url, init) => {
        if (String(url).includes('/api/export/pdf-from-')) {
            window.__binderPosts += 1;
            return { ok: true, blob: async () => new Blob(['%PDF-fake'], {type: 'application/pdf'}) };
        }
        return realFetch(url, init);
    };
    app.saveBlobWithPicker = async () => {};
}"""

# What the dialog shows: the palette, the maps, the six ticks, the scope.
DIALOG_JS = """() => {
    const on = (id) => document.getElementById(id).checked;
    const maps = ['power', 'data', 'both'].filter(m => on(`export-binder-side-${m}`));
    return { palette: on('export-binder-printer') ? 'printer' : 'colour', maps: maps.join(','),
             cover: on('export-binder-cover'), pull: on('export-binder-pull'),
             hardware: on('export-binder-hardware'), wiring: on('export-binder-wiring'),
             fiber: on('export-binder-fiber'), rigging: on('export-binder-rigging'),
             scope: document.getElementById('export-binder-scope').value };
}"""

STATE_JS = """async () => {
    const app = window.app;
    const served = await (await fetch('/api/project')).json();
    const b = app.project.binder || {};
    return { sheets: b.sheets === undefined ? null : JSON.parse(JSON.stringify(b.sheets)),
             served: served.binder && served.binder.sheets !== undefined ? served.binder.sheets : null,
             revisions: (b.revisions || []).map(r => r.rev),
             history: app.history.length, index: app.historyIndex,
             action: app.history[app.historyIndex] && app.history[app.historyIndex].action };
}"""


def _seed(pg):
    pg.evaluate(STUB_JS)
    pg.evaluate(SET_PREFS_JS, PREFS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    return ids


def _open_dialog(pg):
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(150)
    return pg.evaluate(DIALOG_JS)


def _set_tick(pg, key, on):
    # the Fiber tick is offered only to a show that uses fiber, so it is
    # set as the dialog's own control, shown or not
    pg.evaluate("([k, v]) => { document.getElementById(`export-binder-${k}`).checked = v; }", [key, on])


def _confirm(pg):
    pg.evaluate("() => { document.getElementById('status-message').textContent = 'Ready'; }")
    pg.locator('#export-confirm').click()
    # the outcome read as it lands: an earlier export's 3 s "Ready" timer
    # can put the line back a moment later
    outcome = pg.wait_for_function(
        """() => { const t = document.getElementById('status-message').textContent;
                   return ['Export complete!', 'Export failed!'].includes(t) ? t : null; }""",
        timeout=60000).json_value()
    assert outcome == 'Export complete!'
    pg.wait_for_timeout(300)


def _state(pg):
    return pg.evaluate(STATE_JS)


def _choices(dialog):
    return {k: v for k, v in dialog.items() if k != 'scope'}


def _reopen_file(pg, text):
    pg.evaluate("async (text) => { await window.app._openProjectData(JSON.parse(text), { source: 'file' }); }", text)
    pg.wait_for_timeout(600)


def _new_project(pg):
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_function("() => window.app.project && !window.app.project.binder"
                         " && (window.app.project.layers || []).length <= 1", timeout=10000)
    pg.wait_for_timeout(600)


def test_a_whole_show_export_is_remembered_per_show(page):
    """Hardware and Fiber unticked, Printer and the Power maps picked, the
    whole show exported: the show keeps them, in the revision's one undo
    entry; the dialog opens on them again, after a reload and from the
    saved file. Ticking then cancelling writes nothing. File > New opens on
    the preferences again, and the saved show still on its own."""
    pg, errors = page
    _seed(pg)
    before = _state(pg)
    assert before['sheets'] is None and before['revisions'] == [], before
    first = _open_dialog(pg)
    assert _choices(first) == {**PREF_CHOICES, 'maps': 'both'} and first['scope'] == 'show', first
    assert pg.evaluate("() => window.app.binderChoices().saved") is False

    _set_tick(pg, 'hardware', False)
    _set_tick(pg, 'fiber', False)
    pg.locator('#export-binder-printer').check()
    pg.locator('#export-binder-side-power').check()
    _confirm(pg)
    want = {**PREF_CHOICES, 'palette': 'printer', 'maps': 'power', 'hardware': False, 'fiber': False}
    after = _state(pg)
    assert after['sheets'] == want and after['served'] == want, after
    # one entry: the revision this export logged carries the choices too
    assert after['revisions'] == ['1.0'], after
    assert after['history'] == before['history'] + 1 and after['action'] == 'Log Revision', (before, after)

    # undo takes both back, redo puts both back
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(400)
    undone = _state(pg)
    assert undone['sheets'] is None and undone['revisions'] == [] and undone['served'] is None, undone
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(400)
    redone = _state(pg)
    assert redone['sheets'] == want and redone['served'] == want and redone['revisions'] == ['1.0'], redone

    # the dialog opens on them
    again = _open_dialog(pg)
    assert _choices(again) == want, again
    assert pg.evaluate("() => window.app.binderChoices().saved") is True

    # the same export again adds nothing to the history
    _confirm(pg)
    same = _state(pg)
    assert same['history'] == redone['history'] and same['index'] == redone['index'], (redone, same)

    # ticking boxes and cancelling writes nothing, and the next open
    # starts from the show's choices, not from the cancelled ticks
    _open_dialog(pg)
    _set_tick(pg, 'hardware', True)
    pg.locator('#export-binder-colour').check()
    pg.locator('#export-cancel').click()
    pg.wait_for_timeout(200)
    assert _state(pg)['sheets'] == want
    assert _choices(_open_dialog(pg)) == want
    pg.locator('#export-cancel').click()

    # the Whole show scope picked again restores the show's set, not every tick
    pg.evaluate("""() => { const s = document.getElementById('export-binder-scope');
                           s.value = s.options[1].value; s.dispatchEvent(new Event('change'));
                           s.value = 'show'; s.dispatchEvent(new Event('change')); }""")
    assert _choices(pg.evaluate(DIALOG_JS)) == want

    # a reload: the server's copy keeps them
    text = pg.evaluate("() => window.app.serializeProjectForFile()")
    open_app(pg)
    pg.evaluate(STUB_JS)
    assert _state(pg)['sheets'] == want
    assert _choices(_open_dialog(pg)) == want
    pg.locator('#export-cancel').click()

    # File > New: the preferences again, nothing kept
    _new_project(pg)
    fresh = _state(pg)
    assert fresh['sheets'] is None and fresh['served'] is None, fresh
    assert _choices(_open_dialog(pg)) == PREF_CHOICES
    pg.locator('#export-cancel').click()

    # the saved file opens on its own choices
    _reopen_file(pg, text)
    assert _state(pg)['sheets'] == want
    assert _choices(_open_dialog(pg)) == want
    pg.locator('#export-cancel').click()

    # and a preference changed since does not reach a show that has its own
    pg.evaluate(SET_PREFS_JS, {'binderPull': False})
    assert _choices(_open_dialog(pg)) == want
    pg.locator('#export-cancel').click()
    pg.evaluate(SET_PREFS_JS, PREFS)
    assert errors == [], errors


def test_a_single_screen_export_leaves_the_shows_choices_alone(page):
    """The show keeps Hardware and Fiber off. A screen's own export starts
    with the show sheets unticked as it always has; ticked on and exported,
    it still writes nothing to the show: the Whole show scope opens on the
    show's set again."""
    pg, errors = page
    ids = _seed(pg)
    _open_dialog(pg)
    _set_tick(pg, 'hardware', False)
    _set_tick(pg, 'fiber', False)
    _confirm(pg)
    want = {**PREF_CHOICES, 'hardware': False, 'fiber': False}
    assert _state(pg)['sheets'] == want

    pg.evaluate("(id) => window.app.openScreenBinderExport(window.app.project.layers.find(l => l.id === id))",
                ids['b'])
    pg.wait_for_timeout(200)
    one = pg.evaluate(DIALOG_JS)
    assert one['scope'] == f"screen:{ids['b']}", one
    assert (one['cover'], one['pull'], one['hardware'], one['fiber']) == (False, False, False, False), one
    assert (one['wiring'], one['rigging']) == (True, True), one
    before = _state(pg)
    _set_tick(pg, 'hardware', True)
    _set_tick(pg, 'pull', True)
    pg.locator('#export-binder-printer').check()
    _confirm(pg)
    after = _state(pg)
    assert after['sheets'] == want and after['served'] == want, after
    assert after['history'] == before['history'], (before, after)

    # opened again (the screen still the scope) and back to the whole show:
    # the show's set, not the screen export's ticks or palette
    reopened = _open_dialog(pg)
    assert reopened['scope'] == f"screen:{ids['b']}" and reopened['palette'] == 'colour', reopened
    pg.evaluate("() => { const s = document.getElementById('export-binder-scope'); s.value = 'show';"
                " s.dispatchEvent(new Event('change')); }")
    assert _choices(pg.evaluate(DIALOG_JS)) == want
    pg.locator('#export-cancel').click()
    # and opened fresh it is the show's set whole
    pg.evaluate("() => { const s = document.getElementById('export-binder-scope'); s.value = 'show'; }")
    assert _choices(_open_dialog(pg)) == want
    pg.locator('#export-cancel').click()
    assert errors == [], errors


def _logo_png(size=(400, 100), color=(20, 60, 140, 255)):
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((size[0] // 10, size[1] // 10, size[0] * 9 // 10, size[1] * 9 // 10), fill=color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


FEED_LOGO_JS = """async (b64) => {
    const app = window.app;
    const bin = atob(b64); const u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    const input = document.getElementById('export-binder-logo');
    const dt = new DataTransfer(); dt.items.add(new File([u], 'logo.png', { type: 'image/png' }));
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    const t0 = Date.now();
    while (!app.getBinderLogo()) { if (Date.now() - t0 > 8000) throw new Error('no logo'); await new Promise(r => setTimeout(r, 50)); }
    await app._ensureBinderLogo();
    return app.getBinderLogo();
}"""

LOGO_STATE_JS = """async () => {
    const app = window.app;
    const served = await (await fetch('/api/project')).json();
    const prefs = await (await fetch('/api/preferences')).json();
    app.syncBinderControls();
    const shown = (id) => document.getElementById(id).style.display !== 'none';
    return { logo: app.getBinderLogo(), served: (served.binder || {}).logo === undefined ? null : served.binder.logo,
             pref: prefs.binderLogo || '', none: shown('export-binder-logo-none'),
             preview: shown('export-binder-logo-preview'),
             history: app.history.length, action: app.history[app.historyIndex].action,
             version: app.project.app_version, appVersion: app.appVersion() };
}"""


def test_the_logo_is_the_shows(page):
    """A logo added in the dialog is the show's: written to the project in
    one undo entry (undo and redo take it off and put it back), never to
    the preference. A new show has none; the first show, opened again, has
    it; a reload keeps it. Remove takes it off that show alone."""
    pg, errors = page
    _seed(pg)
    _open_dialog(pg)
    before = pg.evaluate(LOGO_STATE_JS)
    assert before['logo'] == '' and before['none'] and not before['preview'], before
    src = pg.evaluate(FEED_LOGO_JS, _logo_png())
    a = pg.evaluate(LOGO_STATE_JS)
    assert src.startswith('data:image/png;base64,')
    assert a['logo'] == src and a['served'] == src and a['pref'] == '', {k: str(v)[:40] for k, v in a.items()}
    assert a['history'] == before['history'] + 1 and a['action'] == 'Set Binder Logo', a
    assert a['preview'] and not a['none']
    # the sheets print it
    drawn = pg.evaluate("""() => { const app = window.app;
        const o = app.readBinderOptions(); return !!app.renderBinderPage(o, 0).logo; }""")
    assert drawn

    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(400)
    u = pg.evaluate(LOGO_STATE_JS)
    assert u['logo'] == '' and u['served'] in (None, ''), {k: str(v)[:40] for k, v in u.items()}
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(400)
    r = pg.evaluate(LOGO_STATE_JS)
    assert r['logo'] == src and r['served'] == src

    # later steps share the one logo string rather than copy it per entry;
    # every entry after the logo still holds it
    pg.evaluate("() => { const app = window.app; for (let i = 0; i < 3; i++) app.setBinderField('venue', `Hall ${i}`, 'Set Binder Venue'); }")
    held = pg.evaluate("""() => window.app.history.slice(-4).map(e => (e.project.binder || {}).logo === window.app.getBinderLogo())""")
    assert held == [True, True, True, True], held

    text = pg.evaluate("() => window.app.serializeProjectForFile()")
    open_app(pg)
    pg.evaluate(STUB_JS)
    assert pg.evaluate(LOGO_STATE_JS)['logo'] == src, 'a reload keeps the show its logo'

    _new_project(pg)
    _open_dialog(pg)
    b = pg.evaluate(LOGO_STATE_JS)
    assert b['logo'] == '' and b['served'] is None and b['none'] and not b['preview'], b
    drawn = pg.evaluate("""() => { const app = window.app;
        const o = { ...app.readBinderOptions(), scope: { kind: 'show' } }; const plan = app.planBinder(o);
        return plan.length ? !!app.renderBinderPage(o, 0).logo : null; }""")
    assert drawn in (False, None)
    pg.locator('#export-cancel').click()

    _reopen_file(pg, text)
    back = pg.evaluate(LOGO_STATE_JS)
    assert back['logo'] == src and back['served'] == src
    # Remove: that show's logo goes, kept as "none" so it stays gone
    _open_dialog(pg)
    pg.locator('#export-binder-logo-remove').click()
    pg.wait_for_timeout(300)
    gone = pg.evaluate(LOGO_STATE_JS)
    assert gone['logo'] == '' and gone['served'] == '' and gone['action'] == 'Remove Binder Logo', gone
    assert gone['none'] and not gone['preview']
    pg.locator('#export-cancel').click()
    assert errors == [], errors


def test_an_older_show_keeps_the_logo_the_preference_held(page):
    """Before 1.7.0 the logo was one preference. A show saved by an older
    build (or none at all) with no logo of its own opens with that logo,
    taken into its own binder before the open's PUT, so the server and the
    first undo entry hold it and an undo cannot take it away. A show this
    build saved does not take it, nor does one that removed its logo, nor
    a new show. The Preferences dialog has no logo row, and its Save keeps
    the stored logo for the shows not opened yet."""
    pg, errors = page
    _seed(pg)
    old = 'data:image/png;base64,' + _logo_png((300, 100), (200, 30, 30, 255))
    pg.evaluate(SET_PREFS_JS, {'binderLogo': old})
    base = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    base.pop('binder', None)
    try:
        for version in ('1.6.0', '1.5.4', None):
            show = dict(base, name=f'Older {version}')
            if version is None:
                show.pop('app_version', None)
            else:
                show['app_version'] = version
            _reopen_file(pg, json.dumps(show))
            s = pg.evaluate(LOGO_STATE_JS)
            assert s['logo'] == old and s['served'] == old, (version, {k: str(v)[:40] for k, v in s.items()})
            assert s['version'] == s['appVersion'], s
            # in the first entry: nothing to undo
            assert s['history'] == 1 and s['action'] == 'Initial State', s
            pg.evaluate("() => window.app.undo()")
            pg.wait_for_timeout(200)
            assert pg.evaluate("() => window.app.getBinderLogo()") == old
            # opened again it is the same, and saved it stays
            text = pg.evaluate("() => window.app.serializeProjectForFile()")
            assert json.loads(text)['binder']['logo'] == old
            _reopen_file(pg, text)
            assert pg.evaluate("() => window.app.getBinderLogo()") == old

        # an older show that had removed it is not given it back
        removed = dict(base, name='Older removed', app_version='1.6.0', binder={'logo': ''})
        _reopen_file(pg, json.dumps(removed))
        assert pg.evaluate("() => window.app.getBinderLogo()") == ''
        # a show this build saved, with no logo, has none
        _reopen_file(pg, json.dumps(dict(base, name='This build')))
        assert pg.evaluate("() => window.app.getBinderLogo()") == ''
        # an older show with a logo of its own keeps its own
        own = 'data:image/png;base64,' + _logo_png((100, 100), (10, 200, 10, 255))
        _reopen_file(pg, json.dumps(dict(base, name='Own logo', app_version='1.6.0', binder={'logo': own})))
        assert pg.evaluate("() => window.app.getBinderLogo()") == own
        # a new show: none, whatever the preference holds
        _new_project(pg)
        assert pg.evaluate("() => window.app.getBinderLogo()") == ''

        # the Preferences dialog: no logo row, and Save keeps the stored one
        pg.evaluate("() => window.app.openPreferencesModal()")
        pg.wait_for_timeout(300)
        pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="binder"]').click()
        assert pg.evaluate("() => !document.getElementById('pref-binder-logo')"
                           " && !document.getElementById('pref-binder-logo-preview')")
        assert 'Logo' not in pg.evaluate(
            "() => [...document.querySelectorAll('#pm-sec-binder .pm-row > label')].map(l => l.textContent.trim())")
        pg.locator('#preferences-save').click()
        pg.wait_for_timeout(600)
        assert pg.evaluate("async () => (await (await fetch('/api/preferences')).json()).binderLogo") == old
    finally:
        pg.evaluate(SET_PREFS_JS, {'binderLogo': ''})
    assert errors == [], errors
