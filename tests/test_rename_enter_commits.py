"""Enter in a name field commits the rename at once, everywhere it shows.

Owner, Mac, 1.7.0 beta: "when i type in a layer name and hit enter nothing
happens it is not until i click out of the layer name does it actually
change", and the same assumed for groups.

The screen name in the Screens list did commit on Enter (its own keydown
blurs the field and the blur saves the name, sends the PUT and records the
undo step), but nothing in that commit drew the canvas again. The redraw
that usually followed came from the socket echo of the PUT, which runs
updateUI; the page lets that echo go without a render when it holds what
the page already has, or is older, or arrives during a gesture, and it
waits on the socket (app-core.js _onSocketLayerUpdated). Measured in
Chromium with the socket down: the canvas never drew the new name. The
name plate kept the old name until some later gesture redrew it, which is
what clicking away did. The canvas, group and beach names go through the
server's answer and redraw from it.

The fix: the screen rename redraws the canvas as it commits, and every
name field (screen, canvas, group, beach) commits from the Enter itself
rather than from the blur that follows it (helpers.js nameFieldEnter), so
the commit does not hang on how a browser orders blur against keydown. The
blur after it finds the edit already closed and does nothing more.

WebKit cannot run on the test PC. An Enter that takes a text composition
(an input method, or the system's inline text) only takes the composed
text, and the next Enter commits. Chromium marks that Enter isComposing;
WebKit ends the composition first and then sends the Enter with keyCode
229. Both orders are replayed below in Chromium, and so is a 229 Enter
with no composition, which commits.

Run locally:
    python -m pytest tests/test_rename_enter_commits.py -v -n 4 --dist loadfile
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401
from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Two loose screens, one group of two, two canvases and one beach. The
# group's names show as Group on the Pixel Map, so its name is drawn.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = (proj.canvases || []).slice(0, 1);
    const c1 = proj.canvases.length ? proj.canvases[0].id : null;
    if (c1) { proj.canvases[0].name = 'Canvas One'; proj.active_canvas_id = c1; }
    await j('PUT', '/api/project', proj);
    const add = (name, x, y) => j('POST', '/api/layer/add', {name, columns: 2, rows: 2,
        cabinet_width: 200, cabinet_height: 200, offset_x: x, offset_y: y});
    for (const [n, x, y] of [['ALPHA', 0, 0], ['BRAVO', 600, 0],
                             ['G1A', 0, 600], ['G1B', 400, 600]]) {
        await add(n, x, y);
    }
    const c2 = (await j('POST', '/api/canvas', {name: 'Canvas Two'})).active_canvas_id;
    if (c1) await j('PUT', `/api/canvas/${c1}/active`);
    await j('POST', '/api/beaches', {name: 'SR'});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('rename_enter_setup');
    const by = (n) => app.project.layers.find(l => l.name === n);
    const ids = ['G1A', 'G1B'].map(n => by(n).id);
    app.setSelectedLayersByIds(ids, ids[0]);
    await app.groupSelectedLayers();
    app.project = await j('GET', '/api/project');
    app.selectLayer(by('BRAVO'));
    app.renderLayers();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Rename Enter Seed');
    return {
        a: by('ALPHA').id, b: by('BRAVO').id,
        group: (app.project.groups || []).map(g => g.id)[0],
        canvases: [c1, c2],
        beach: (app.project.beaches || []).map(b => b.id)[0],
    };
}"""

# Every string the page draws on a canvas from here on, so a test can say
# the new name reached the drawing.
WATCH_DRAWING_JS = """() => {
    window.__drawn = [];
    if (window.__drawWatch) return;
    window.__drawWatch = true;
    const wrap = (proto) => {
        if (!proto || !proto.fillText) return;
        const fill = proto.fillText;
        proto.fillText = function (text, ...rest) {
            if (window.__drawn) window.__drawn.push(String(text));
            return fill.call(this, text, ...rest);
        };
    };
    wrap(window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype);
    wrap(window.OffscreenCanvasRenderingContext2D && OffscreenCanvasRenderingContext2D.prototype);
}"""

MARK_JS = """() => {
    window.__drawn = [];
    return window.app.historyIndex;
}"""

STATE_JS = """([sel, name]) => {
    const app = window.app;
    const el = document.querySelector(sel);
    const h = app.history[app.historyIndex];
    return {
        drawn: (window.__drawn || []).some(t => t.includes(name)),
        readOnly: el ? el.readOnly : null,
        focused: !!el && document.activeElement === el,
        editing: !!el && el.classList.contains('editing'),
        value: el ? el.value : null,
        historyIndex: app.historyIndex,
        action: h ? h.action : null,
    };
}"""

SERVER_JS = """async () => {
    const p = await (await fetch('/api/project')).json();
    const pick = (xs) => Object.fromEntries((xs || []).map(x => [String(x.id), x.name]));
    return {layers: pick(p.layers), canvases: pick(p.canvases), groups: pick(p.groups),
            beaches: pick(p.beaches)};
}"""

# An Enter keydown with keyCode 229, in one of three orders:
#   'chromium': the composition still open, the keydown isComposing;
#   'webkit':   compositionend first, then the keydown, isComposing false;
#   'bare':     no composition at all (a plain Enter that reports 229).
# Chromium's KeyboardEvent takes neither keyCode nor isComposing from its
# init, so both are set on the event itself.
ENTER_229_JS = """([sel, order]) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const comp = (type) => el.dispatchEvent(new CompositionEvent(type,
        {bubbles: true, cancelable: true, composed: true, data: ''}));
    if (order !== 'bare') comp('compositionstart');
    if (order === 'webkit') comp('compositionend');
    const e = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter',
        bubbles: true, cancelable: true, composed: true});
    Object.defineProperty(e, 'keyCode', {get: () => 229});
    Object.defineProperty(e, 'which', {get: () => 229});
    Object.defineProperty(e, 'isComposing', {get: () => order === 'chromium'});
    el.dispatchEvent(e);
    if (order === 'chromium') comp('compositionend');
    return true;
}"""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body='{"ok": false, "cancelled": true}')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    writes = []
    pg.on('request', lambda r: writes.append((r.method, r.url, r.post_data or ''))
          if r.method in ('PUT', 'POST', 'PATCH') else None)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert ids['group'] and ids['beach'] and all(ids['canvases']), ids
    pg.evaluate(WATCH_DRAWING_JS)
    ids['errors'] = errors
    ids['writes'] = writes
    yield pg, ids
    context.close()


def _screen(layer_id):
    return f'#layers-list .layer-item[data-layer-id="{layer_id}"] .layer-name-input'


def _canvas(canvas_id):
    return f'#layers-list .canvas-group[data-canvas-id="{canvas_id}"] .canvas-name-input'


def _group(group_id):
    return f'#layers-list .screen-group[data-group-id="{group_id}"] .screen-group-name-input'


def _beach(beach_id):
    return f'#beaches-panel .beach-row[data-beach-id="{beach_id}"] .beach-name-input'


def _open_and_type(pg, sel, text):
    pg.locator(sel).dblclick()
    got = settled(pg, lambda: pg.evaluate(STATE_JS, [sel, text]),
                  lambda v: v['readOnly'] is False and v['focused'])
    assert got['readOnly'] is False and got['focused'], f'the rename did not open at {sel}: {got}'
    pg.keyboard.press('Control+A')
    pg.keyboard.type(text)


def _writes_naming(ids, text):
    """The writes to the show that carry `text` (the page's own log posts,
    which quote what was typed, are not writes to the show)."""
    return [w for w in ids['writes'] if text in w[2] and '/api/log' not in w[1]]


def _enter_commits(pg, ids, sel, text, kind, key, action, drawn=True):
    """Press Enter and nothing else: the name is drawn, the field lets go,
    one write goes to the server, one undo step is taken; the blur that
    follows adds nothing."""
    _open_and_type(pg, sel, text)
    before = pg.evaluate(MARK_JS)
    del ids['writes'][:]
    pg.keyboard.press('Enter')

    def ok(v):
        return (v['readOnly'] and not v['focused'] and v['historyIndex'] == before + 1
                and (v['drawn'] or not drawn))
    got = settled(pg, lambda: pg.evaluate(STATE_JS, [sel, text]), ok)
    assert got['readOnly'] and not got['focused'], f'Enter did not end the edit: {got}'
    assert not got['editing'], got
    assert got['value'] == text, got
    assert got['historyIndex'] == before + 1 and got['action'] == action, \
        f'Enter did not record one {action} step: {got} (before {before})'
    if drawn:
        assert got['drawn'], f'the canvas was not drawn with {text!r} after Enter: {got}'
    server = settled(pg, lambda: pg.evaluate(SERVER_JS), lambda v: v[kind].get(str(key)) == text)
    assert server[kind].get(str(key)) == text, f'the {kind} rename never reached the server: {server}'
    # Then the person clicks away: nothing more is written or recorded.
    pg.wait_for_timeout(300)
    pg.locator('#layers-list').click(position={'x': 5, 'y': 5}, force=True)
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")
    pg.wait_for_timeout(400)
    after = pg.evaluate(STATE_JS, [sel, text])
    assert after['historyIndex'] == before + 1, f'the blur after Enter took another step: {after}'
    named = _writes_naming(ids, text)
    assert len(named) == 1, f'expected one write carrying {text!r}, got {named}'


# ── each name field ───────────────────────────────────────────────────────

def test_screen_name_enter_commits_and_redraws(page):
    pg, ids = page
    _enter_commits(pg, ids, _screen(ids['a']), 'ALPHA RENAMED', 'layers', ids['a'], 'Rename Layer')


@pytest.mark.parametrize('kind', ['screen', 'group'])
def test_enter_redraws_without_the_socket_echo(page, kind):
    """The redraw is the rename's own: with the socket down no echo comes
    back, and the new name is drawn all the same (before the fix the
    screen's never was)."""
    pg, ids = page
    sel = _screen(ids['b']) if kind == 'screen' else _group(ids['group'])
    text = f'{kind.upper()} NO ECHO'
    pg.evaluate("() => window.app.socket.disconnect()")
    try:
        _open_and_type(pg, sel, text)
        before = pg.evaluate(MARK_JS)
        pg.keyboard.press('Enter')
        got = settled(pg, lambda: pg.evaluate(STATE_JS, [sel, text]),
                      lambda v: v['drawn'] and v['historyIndex'] == before + 1)
        assert got['drawn'], f'the canvas never drew {text!r}: {got}'
        assert got['readOnly'] and not got['focused'] and got['historyIndex'] == before + 1, got
    finally:
        pg.evaluate("() => window.app.socket.connect()")
        pg.wait_for_timeout(500)


def test_canvas_name_enter_commits(page):
    pg, ids = page
    c2 = ids['canvases'][1]
    _enter_commits(pg, ids, _canvas(c2), 'CANVAS RENAMED', 'canvases', c2, 'Rename Canvas',
                   drawn=False)


def test_group_name_enter_commits_and_redraws(page):
    pg, ids = page
    pg.evaluate("""(gid) => {
        const app = window.app;
        const g = (app.project.groups || []).find(x => x.id === gid);
        const ids = app.getGroupMembers(g).map(l => l.id);
        app.setSelectedLayersByIds(ids, ids[0]);
    }""", ids['group'])
    _enter_commits(pg, ids, _group(ids['group']), 'WALL RENAMED', 'groups', ids['group'], 'Rename Group')


def test_beach_name_enter_commits(page):
    pg, ids = page
    _enter_commits(pg, ids, _beach(ids['beach']), 'BEACH RENAMED', 'beaches', ids['beach'], 'Rename Beach',
                   drawn=False)


# ── Escape and the WebKit composing Enter ─────────────────────────────────

def test_escape_still_drops_the_typing(page):
    pg, ids = page
    for sel, kind, key in ((_screen(ids['b']), 'layers', ids['b']),
                           (_group(ids['group']), 'groups', ids['group']),
                           (_canvas(ids['canvases'][0]), 'canvases', ids['canvases'][0]),
                           (_beach(ids['beach']), 'beaches', ids['beach'])):
        server0 = pg.evaluate(SERVER_JS)[kind][str(key)]
        _open_and_type(pg, sel, 'NOT KEPT')
        before = pg.evaluate(MARK_JS)
        del ids['writes'][:]
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(400)
        got = pg.evaluate(STATE_JS, [sel, 'NOT KEPT'])
        assert got['readOnly'] and not got['focused'], (sel, got)
        assert got['value'] == server0, (sel, got)
        assert got['historyIndex'] == before, (sel, got)
        assert not _writes_naming(ids, 'NOT KEPT'), (sel, ids['writes'])
        assert pg.evaluate(SERVER_JS)[kind][str(key)] == server0, sel


def _field_of(ids, kind):
    return {
        'screen': (_screen(ids['b']), ids['b'], 'layers'),
        'group': (_group(ids['group']), ids['group'], 'groups'),
        'canvas': (_canvas(ids['canvases'][0]), ids['canvases'][0], 'canvases'),
        'beach': (_beach(ids['beach']), ids['beach'], 'beaches'),
    }[kind]


@pytest.mark.parametrize('kind', ['screen', 'group', 'canvas', 'beach'])
def test_composing_enter_keeps_the_edit_then_enter_commits(page, kind):
    """The Enter that takes a composition, in Chromium's order and then in
    WebKit's (compositionend first, then keyCode 229), leaves the edit open;
    the plain Enter after it commits once."""
    pg, ids = page
    sel, key, table = _field_of(ids, kind)
    text = f'{kind.upper()} COMPOSED'
    _open_and_type(pg, sel, text)
    before = pg.evaluate(MARK_JS)
    del ids['writes'][:]
    for order in ('chromium', 'webkit'):
        assert pg.evaluate(ENTER_229_JS, [sel, order])
        pg.wait_for_timeout(300)
        got = pg.evaluate(STATE_JS, [sel, text])
        assert got['readOnly'] is False and got['focused'], \
            f'a composing Enter ({order} order) ended the edit: {got}'
        assert got['historyIndex'] == before, (order, got)
        assert not _writes_naming(ids, text), (order, ids['writes'])
    pg.keyboard.press('Enter')
    got = settled(pg, lambda: pg.evaluate(STATE_JS, [sel, text]),
                  lambda v: v['readOnly'] and not v['focused'] and v['historyIndex'] == before + 1)
    assert got['readOnly'] and not got['focused'] and got['historyIndex'] == before + 1, got
    server = settled(pg, lambda: pg.evaluate(SERVER_JS), lambda v: v[table].get(str(key)) == text)
    assert server[table].get(str(key)) == text, server
    pg.wait_for_timeout(300)
    assert len(_writes_naming(ids, text)) == 1, ids['writes']


@pytest.mark.parametrize('kind', ['screen', 'group', 'canvas', 'beach'])
def test_an_enter_reporting_229_with_no_composition_commits(page, kind):
    """keyCode 229 alone is not a composition: with none open or just ended
    on the field, the Enter commits, drawn on the canvas for a screen."""
    pg, ids = page
    sel, key, table = _field_of(ids, kind)
    text = f'{kind.upper()} BARE'
    _open_and_type(pg, sel, text)
    pg.wait_for_timeout(1100)   # past any composition an earlier test ended
    before = pg.evaluate(MARK_JS)
    del ids['writes'][:]
    assert pg.evaluate(ENTER_229_JS, [sel, 'bare'])
    got = settled(pg, lambda: pg.evaluate(STATE_JS, [sel, text]),
                  lambda v: v['readOnly'] and not v['focused'] and v['historyIndex'] == before + 1
                  and (v['drawn'] or kind != 'screen'))
    assert got['readOnly'] and not got['focused'] and got['historyIndex'] == before + 1, got
    if kind == 'screen':
        assert got['drawn'], got
    server = settled(pg, lambda: pg.evaluate(SERVER_JS), lambda v: v[table].get(str(key)) == text)
    assert server[table].get(str(key)) == text, server
    pg.wait_for_timeout(300)
    assert len(_writes_naming(ids, text)) == 1, ids['writes']


def test_a_locked_screen_keeps_its_name_on_enter(page):
    pg, ids = page
    sel = _screen(ids['a'])
    name0 = pg.evaluate(SERVER_JS)['layers'][str(ids['a'])]
    pg.evaluate("""(id) => {
        const app = window.app;
        app.project.layers.find(x => x.id === id).locked = true;
        window.__toasts = [];
        if (!app.__toastWatch) {
            app.__toastWatch = app._toast;
            app._toast = function (msg, ...rest) {
                window.__toasts.push(String(msg));
                return app.__toastWatch.call(this, msg, ...rest);
            };
        }
    }""", ids['a'])
    try:
        _open_and_type(pg, sel, 'LOCKED TRY')
        before = pg.evaluate(MARK_JS)
        del ids['writes'][:]
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(400)
        got = pg.evaluate(STATE_JS, [sel, 'LOCKED TRY'])
        assert got['readOnly'] and got['value'] == name0, got
        assert got['historyIndex'] == before, got
        assert not _writes_naming(ids, 'LOCKED TRY'), ids['writes']
        toasts = pg.evaluate("() => window.__toasts")
        assert len(toasts) == 1 and 'is locked' in toasts[0], toasts
    finally:
        pg.evaluate("""(id) => {
            window.app.project.layers.find(x => x.id === id).locked = false;
        }""", ids['a'])


def test_no_page_errors(page):
    pg, ids = page
    assert ids['errors'] == [], ids['errors']
