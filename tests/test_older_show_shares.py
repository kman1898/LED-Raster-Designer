"""An older show's automatic 2fers and 3fers are kept as saved (1.6.0).

Up to 1.5.3 a US circuit packed to 100% of its breaker; it packs to 80%
now (since the 1.5.4 betas that led to 1.6.0). Automatic shares are
worked out from that figure on every read, so a show saved by an older
build whose 2fers fit at 100% but not at 80% used
to open with them re-split: more circuits, more multis, a different pull
sheet. The owner's ruling: opening it keeps them exactly as saved and
flags the overloaded ones OVER, the same OVER every shared circuit past
its amps wears; the user shares them again. A locked screen stays
unchanged as well. The next change that repacks the screen is a normal
repack at 80%.

The walls are synthetic: 6 x 4 cabinets of 305 W on 208 V x 20 A, cabled
by row (tr-h), Organized, sharing through splitters (maxWays 3), on no
distro (208 V packs at 80%). A row draws 1,830 W: two rows (3,660 W,
17.6 A) fit one circuit at 100% (4,160 W) and not at 80% (3,328 W), so the
old build made two 2fers and this one makes four single-row circuits.

Run locally:
    python -m pytest tests/test_older_show_shares.py -v --browser chromium
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


FETCH_COUNT_JS = """(() => {
    const real = window.fetch;
    let out = 0;
    Object.defineProperty(window, '__lrdFetchesOut', { get: () => out });
    window.fetch = function (...args) {
        out++;
        const p = real.apply(this, args);
        p.then(() => { out--; }, () => { out--; });
        return p;
    };
})()"""


def _settle(pg):
    """Every fetch the page made has answered and every layer save landed."""
    pg.wait_for_function("() => window.__lrdFetchesOut === 0")
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")
    pg.wait_for_function("() => window.__lrdFetchesOut === 0 && !window.app._saveStateTimer")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    _settle(pg)
    yield pg, errors
    context.close()


# The show file an older build would have written: screens built on the
# server, shaped as above, without the keep this build adds on open, and
# stamped with `version` (None: no stamp, every file from before 1.3.0).
SHOW_JS = """async ({ specs, version }) => {
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
    await window.app._layerSavesSettled();
    await fetch('/api/project/new', { method: 'POST' });
    const ids = [];
    for (const s of specs) {
        const made = await j('POST', '/api/layer/add', {
            name: s.name, columns: 6, rows: 4, cabinet_width: 200, cabinet_height: 200,
            offset_x: s.x || 0, offset_y: 0 });
        ids.push(made.id);
    }
    const p = await j('GET', '/api/project');
    specs.forEach((s, i) => {
        const l = p.layers.find(x => x.id === ids[i]);
        Object.assign(l, {
            powerFlowPattern: 'tr-h', lastPowerFlowPattern: 'tr-h',
            powerCustomPath: false, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: s.watts || 305,
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } },
            locked: !!s.locked,
        });
    });
    p.name = 'Older Show';
    if (version === null) delete p.app_version; else p.app_version = version;
    return p;
}"""


def show(pg, specs, version='1.5.3'):
    project = pg.evaluate(SHOW_JS, {'specs': specs, 'version': version})
    _settle(pg)
    for l in project['layers']:
        assert 'kept' not in (l.get('powerSplitters') or {}), l['name']
    return project


def open_file(pg, project):
    """File > Open with the show, the way the user does, through the load's
    PUT and its layer sync."""
    pg.evaluate("""() => {
        window.__loaded = false;
        const el = document.getElementById('status-message');
        const mo = new MutationObserver(() => {
            if (el.textContent === 'Project loaded') { window.__loaded = true; mo.disconnect(); }
        });
        mo.observe(el, { childList: true, characterData: true, subtree: true });
    }""")
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("() => window.app.loadProjectFromFile()")
    chooser.value.set_files({'name': 'older-show.json', 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_function("() => window.__loaded === true")
    _settle(pg)


# Each screen as the app reads it: its circuits' runs, the Nfer pills the
# wall paints (ways, OVER, the pill's text), the keep on it, its lock, the
# % it packs at - and the copy of the keep the server holds.
READ_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    app._circuitTailCache = null;
    const server = await (await fetch('/api/project')).json();
    const out = {};
    app.project.layers.filter(l => (l.type || 'screen') === 'screen').forEach(l => {
        const srv = server.layers.find(x => x.id === l.id) || {};
        out[l.name] = {
            runIds: app.screenCircuits(l).map(c => c.runIds),
            gangs: r._nferGangs(l).map(g => [g.ways, g.over, r._nferTagText(l, g)]),
            amps: app.getSocaPlan(l).flatMap(s => s.legs.map(g => +g.amps.toFixed(1))),
            kept: (l.powerSplitters || {}).kept || null,
            serverKept: (srv.powerSplitters || {}).kept || null,
            locked: !!l.locked,
            pct: app.circuitCapacity(l).pct,
        };
    });
    return out;
}"""


def read(pg):
    return pg.evaluate(READ_JS)


KEPT = [[1, 2], [3, 4]]
REPACKED = [[1], [2], [3], [4]]
OVER = [[2, True, '2fer · OVER'], [2, True, '2fer · OVER']]


def edit(pg, name, patch, action='Edit Power'):
    """A screen edit through the layer commit, the way the sidebar's
    fields land: the fields set, then updateLayers with a history entry."""
    pg.evaluate("""([name, patch, action]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        Object.assign(l, patch);
        app._circuitTailCache = null;
        app.updateLayers([l], true, action);
    }""", [name, patch, action])
    _settle(pg)


def test_an_older_show_opens_with_its_2fers_as_saved_and_flagged_over(page):
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A'}, {'name': 'WALL B', 'x': 1400, 'locked': True}]))
    got = read(pg)
    for name in ('WALL A', 'WALL B'):
        s = got[name]
        # the old build's circuits: two 2fers, at 80% of the breaker
        assert s['pct'] == 0.8, (name, s)
        assert s['runIds'] == KEPT, (name, s)
        # each 2fer draws 17.6 A on a circuit held to 16 A: OVER, the pill
        # every shared circuit past its amps wears
        assert s['amps'] == [17.6, 17.6], (name, s)
        assert s['gangs'] == OVER, (name, s)
        # the keep is saved with the screen, on the server's copy too
        assert s['kept'] and s['kept']['groups'] == KEPT, (name, s)
        assert s['serverKept'] == s['kept'], (name, s)
    # the locked screen opens locked and unchanged, the same as the other
    assert got['WALL B']['locked'] is True and got['WALL A']['locked'] is False
    # the file the app saves from here keeps them, stamped with this build
    saved = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    by = {l['name']: l for l in saved['layers']}
    assert by['WALL A']['powerSplitters']['kept']['groups'] == KEPT
    assert not pg.evaluate("(p) => window.app.olderShowKeepsShares(p)", saved)
    assert errors == [], errors


def test_an_unstamped_show_is_an_older_one_too(page):
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A'}], version=None))
    assert read(pg)['WALL A']['runIds'] == KEPT
    assert errors == [], errors


def test_a_show_saved_by_this_build_packs_at_80(page):
    pg, errors = page
    version = pg.evaluate("() => window.app.appVersion()")
    for stamp in (version, '1.6.0', '1.5.4', '1.5.4-beta.1', '1.5.4-beta.3'):
        open_file(pg, show(pg, [{'name': 'WALL A'}], version=stamp))
        s = read(pg)['WALL A']
        assert s['runIds'] == REPACKED and s['kept'] is None and s['gangs'] == [], (stamp, s)
    assert errors == [], errors


def test_the_bar_is_the_1_5_4_betas(page):
    """1.5.4 only ever shipped as betas, on the way to 1.6.0, and those
    betas already packed at 80%. A show any of them saved, or 1.6.0 and
    later (its betas too), is a new show; 1.5.3 and earlier, a 1.5.3
    beta, and an unstamped show are older ones."""
    pg, errors = page
    ask = lambda v: pg.evaluate("(v) => window.app.olderShowKeepsShares({app_version: v})", v)
    for v in ('1.5.4-beta.1', '1.5.4-beta.2', '1.5.4-beta.3', '1.6.0-beta.1', '1.6.0',
              'v1.6.0', '1.6.1', '1.7.0'):
        assert ask(v) is False, v
    for v in ('1.5.3', '1.5.3-beta.11', '1.5.2', '1.4.1', '1.0', None, ''):
        assert ask(v) is True, v
    assert errors == [], errors


def test_2fers_that_still_fit_get_no_keep(page):
    """305 W makes the old 2fers too big for 80%; at 100 W a row is 600 W
    and three rows share a circuit through a 3fer at either figure, so the
    screen packs the same and nothing is written on it."""
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A', 'watts': 100}]))
    s = read(pg)['WALL A']
    assert s['runIds'] == [[1, 2, 3], [4]] and s['kept'] is None, s
    assert s['gangs'] == [[3, False, '3fer']], s
    assert errors == [], errors


def test_the_next_change_that_repacks_the_screen_is_a_normal_repack(page):
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A'}, {'name': 'WALL B', 'x': 1400, 'locked': True}]))
    # moving the screen repacks nothing: the 2fers stay
    edit(pg, 'WALL A', {'offset_x': 40}, 'Move')
    assert read(pg)['WALL A']['runIds'] == KEPT
    # a new Watts per Panel repacks it at 80%, and the keep goes, on the
    # server's copy too
    edit(pg, 'WALL A', {'panelWatts': 300})
    got = read(pg)
    a = got['WALL A']
    assert a['runIds'] == REPACKED and a['gangs'] == [], a
    assert a['kept'] is None and a['serverKept'] is None, a
    # typing the old figure back is one more normal repack, never the old 2fers
    edit(pg, 'WALL A', {'panelWatts': 305})
    a = read(pg)['WALL A']
    assert a['runIds'] == REPACKED and a['kept'] is None, a
    # the locked screen was never touched
    b = read(pg)['WALL B']
    assert b['runIds'] == KEPT and b['gangs'] == OVER and b['kept']['groups'] == KEPT, b
    # undo goes back through both edits to the 2fers as opened
    pg.evaluate("() => { window.app.undo(); }")
    _settle(pg)
    pg.evaluate("() => { window.app.undo(); }")
    _settle(pg)
    a = read(pg)['WALL A']
    assert a['runIds'] == KEPT and a['gangs'] == OVER, a
    assert errors == [], errors


def test_removing_one_kept_2fer_is_a_normal_repack(page):
    """Remove 2fer on a kept circuit is the user sharing again: the screen
    packs at 80% with that circuit's runs pinned apart."""
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A'}]))
    pg.evaluate("""() => {
        const app = window.app;
        app.splitSplitterCircuits(app.project.layers.find(x => x.name === 'WALL A'), [1]);
    }""")
    _settle(pg)
    a = read(pg)['WALL A']
    assert a['runIds'] == REPACKED and a['kept'] is None and a['gangs'] == [], a
    assert errors == [], errors


def test_turning_the_splitters_off_and_on_shares_them_again(page):
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL A'}]))
    for on in (False, True):
        pg.evaluate("""(on) => {
            const app = window.app;
            app.selectLayer(app.project.layers.find(x => x.name === 'WALL A'));
            const en = document.getElementById('power-splitters-enabled');
            en.checked = on;
            en.dispatchEvent(new Event('change'));
        }""", on)
        _settle(pg)
    a = read(pg)['WALL A']
    assert a['runIds'] == REPACKED and a['kept'] is None and a['gangs'] == [], a
    assert errors == [], errors


def test_a_locked_screen_refuses_the_edit_and_keeps_its_2fers(page):
    """Lock holds: the sidebar's edit funnel refuses a locked screen with
    the error naming it, and its kept 2fers stay."""
    pg, errors = page
    open_file(pg, show(pg, [{'name': 'WALL B', 'locked': True}]))
    out = pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'WALL B');
        app.selectLayer(l);
        const shown = [];
        const real = app._showLockedError;
        app._showLockedError = function (layers, why) {
            shown.push((layers || []).map(x => x.name));
            return real.apply(this, arguments);
        };
        try {
            app.splitSplitterCircuits(l, [1]);
        } finally {
            app._showLockedError = real;
        }
        return shown;
    }""")
    _settle(pg)
    assert out and out[0] == ['WALL B'], out
    b = read(pg)['WALL B']
    assert b['runIds'] == KEPT and b['gangs'] == OVER and b['kept']['groups'] == KEPT, b
    assert errors == [], errors
