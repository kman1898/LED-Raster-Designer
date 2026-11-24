"""Every processor's and every distro's cable list from one button.

The owner, 2026-11-24: "currently we have the ability on processing to do a
dropdown for all the data extensions and fiber for one processor. Having
another one of those buttons at the very top for all of hardware to expand
all of them would be nice. We can do the same thing on distros." And on the
distro side: "the distro thing is just a window that allows the lists of all
cable lengths and extensions".

  * Data: the tray header's ≡ (beside Add) opens every processor's cable list
    at once, and closes them all once every one is open. It writes each
    processor's own key, so each processor's ≡ agrees with it afterwards.
  * Power: each distro gets a ≡ of its own, built like the processor's: one
    list under the distro, outside every fold, with its power in, each
    multi's home run and circuit cables (the multi's own sheet) and each
    direct output's cable. A length typed there is the same stored entry
    the multi's header and sheet type. The chips stay chips; each multi's
    own ≡ is untouched. The header's ≡ opens or closes every distro's list.
  * Nothing on the header moves when the lists open and close.

Synthetic hardware only.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


DIALOGS = ('save-file', 'open-file', 'select-directory')

FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""

CLEAR_KEYS_JS = """() => {
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (/^lrd_data_cable_sheet_|^lrd_distro_cable_list_|^lrd_cable_sheet_|^ledRasterPanelCollapsed_hwdock-/.test(k)) {
                localStorage.removeItem(k);
            }
        }
    } catch (_) { /* no storage */ }
}"""

# Three processors, each with ports of its own and so a cable list.
SEED_DATA_JS = """async () => {
    const app = window.app;
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await send('/api/project', 'PUT', proj);
    await send('/api/layer/add', 'POST', { name: 'WALL', columns: 4, rows: 2,
        cabinet_width: 500, cabinet_height: 500 });
    for (const name of ['A', 'B', 'C']) {
        const st = await send('/api/processors', 'POST', { deviceId: 'novastar-vx1000' });
        const p = st.resolved[st.resolved.length - 1];
        await send(`/api/processors/${p.id}`, 'PUT', { name });
    }
    await app.refreshProcessors();
    app.project = await send('/api/project', 'GET');
    app.renderHardwareDock();
    return app._processorsResolved.map(p => p.id);
}"""

# The Data header's ≡ and every processor's: what a user can see.
DATA_STATE_JS = """(ids) => {
    const all = document.getElementById('hw-dock-proc-sheets');
    const r = all.getBoundingClientRect();
    const add = document.getElementById('processor-add-btn').getBoundingClientRect();
    const head = document.querySelector('#hardware-dock .hw-dock-head').getBoundingClientRect();
    return {
        all: { shown: r.width > 0, on: all.classList.contains('hw-dock-cablebtn-on'),
               disabled: all.disabled, pressed: all.getAttribute('aria-pressed'),
               text: all.textContent, tip: all.dataset.tooltip || '' },
        place: [Math.round(add.left), Math.round(add.top), Math.round(r.left),
                Math.round(head.height)],
        procs: ids.map(id => {
            const b = document.querySelector(`[data-lrd-field="data-cable-sheet-${id}"]`);
            let stored = null;
            try { stored = localStorage.getItem(`lrd_data_cable_sheet_proc_${id}`); } catch (_) {}
            return { id, btn: !!b, on: !!b && b.classList.contains('hw-dock-cablebtn-on'),
                     list: !!document.querySelector(`[data-lrd-proc-sheet="${id}"]`), stored };
        }),
    };
}"""

# WALL: 8 x 12 of 200 W cabinets at 208 V, one row per circuit, so two
# multis of six. Multi 1 on SR, multi 2 on SL, and a third distro US with
# nothing on it (its list still has its power in).
SEED_POWER_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL', columns: 8, rows: 12,
                              cabinet_width: 200, cabinet_height: 200})});
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 12.5,
                                  panelWatts: 200,
                                  processorType: 'novastar-coex-1g'})});
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('cable_lists_setup');
    await app.refreshProcessors();
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    const sr = app.addDistro({name: 'SR'});
    const sl = app.addDistro({name: 'SL'});
    const us = app.addDistro({name: 'US'});
    app.setSocaDistro(wall, 1, sr.id);
    app.setSocaNumber(wall, 1, 1);
    app.setSocaDistro(wall, 2, sl.id);
    app.setSocaNumber(wall, 2, 1);
    app.renderLayers();
    app._circuitTailCache = null;
    app.renderHardwareDock();
    app.resetHistory('Cable Lists Seed');
    const plan = app.getSocaPlan(wall);
    return {
        wall: wall.id, ids: [sr.id, sl.id, us.id],
        circuits: plan.find(s => s.soca === 1).legs.map(g => g.circuit),
    };
}"""

POWER_STATE_JS = """(ids) => {
    const all = document.getElementById('hw-dock-distro-lists');
    const r = all.getBoundingClientRect();
    const add = document.getElementById('power-distro-add').getBoundingClientRect();
    const head = document.querySelector('#hardware-dock .hw-dock-head').getBoundingClientRect();
    return {
        all: { shown: r.width > 0, on: all.classList.contains('hw-dock-cablebtn-on'),
               disabled: all.disabled, pressed: all.getAttribute('aria-pressed'),
               text: all.textContent, tip: all.dataset.tooltip || '' },
        place: [Math.round(add.left), Math.round(add.top), Math.round(r.left),
                Math.round(head.height)],
        distros: ids.map(id => {
            const b = document.querySelector(`[data-lrd-field="power-distro-list-${id}"]`);
            const list = document.querySelector(`[data-lrd-distro-list="${id}"]`);
            let stored = null;
            try { stored = localStorage.getItem(`lrd_distro_cable_list_${id}`); } catch (_) {}
            return {
                id, btn: !!b, shown: !!b && b.getClientRects().length > 0,
                on: !!b && b.classList.contains('hw-dock-cablebtn-on'),
                list: !!list,
                secs: list ? [...list.querySelectorAll('[data-lrd-distro-list-sec]')]
                    .map(s => s.dataset.lrdDistroListSec) : [],
                heads: list ? [...list.querySelectorAll('.hw-dock-proc-sheet-head')]
                    .map(h => h.textContent) : [],
                stored,
            };
        }),
    };
}"""


def landed(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    for name in DIALOGS:
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"ok": false, "cancelled": true, "unavailable": false}'))
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " === true && window.app._socketConnects >= 1")
    landed(pg)
    yield pg, errors
    context.close()


def view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_function(f"() => window.canvasRenderer.viewMode === '{mode}'")
    landed(page)


def click(page, selector):
    page.locator(selector).click()
    landed(page)


def test_the_data_header_opens_and_closes_every_processor_list(page):
    pg, errors = page
    view(pg, 'data-flow')
    pg.evaluate(CLEAR_KEYS_JS)
    ids = pg.evaluate(SEED_DATA_JS)
    landed(pg)
    assert len(ids) == 3
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert st['all']['shown'] and not st['all']['disabled']
    assert st['all']['text'] == '≡'
    assert not st['all']['on'] and st['all']['pressed'] == 'false'
    # the tooltip names the button, then says what it does
    assert st['all']['tip'].startswith('Cable lists, Open every processor')
    assert all(p['btn'] and not p['on'] and not p['list'] for p in st['procs'])
    place = st['place']

    # one processor open by its own ≡: the header still offers to open
    click(pg, f'[data-lrd-field="data-cable-sheet-{ids[1]}"]')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert [p['on'] for p in st['procs']] == [False, True, False]
    assert not st['all']['on']

    # Open all: every processor as its own ≡ would leave it
    click(pg, '#hw-dock-proc-sheets')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert all(p['on'] and p['list'] and p['stored'] == '1' for p in st['procs']), st
    assert st['all']['on'] and st['all']['pressed'] == 'true'
    assert st['all']['tip'].startswith('Cable lists, Every processor')
    assert st['place'] == place, 'the header moved'

    # one closed by its own ≡: the header offers to open again
    click(pg, f'[data-lrd-field="data-cable-sheet-{ids[0]}"]')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert [p['on'] for p in st['procs']] == [False, True, True]
    assert not st['all']['on']
    click(pg, '#hw-dock-proc-sheets')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert all(p['on'] and p['list'] for p in st['procs'])

    # Close all: each processor's ≡ agrees, its key gone
    click(pg, '#hw-dock-proc-sheets')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert all(not p['on'] and not p['list'] and p['stored'] is None
               for p in st['procs']), st
    assert not st['all']['on'] and st['place'] == place

    # each processor's own ≡ still works after the header used it
    click(pg, f'[data-lrd-field="data-cable-sheet-{ids[2]}"]')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert [p['on'] for p in st['procs']] == [False, False, True]
    assert [p['list'] for p in st['procs']] == [False, False, True]

    # a reload keeps what was open (localStorage, never the show)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true")
    view(pg, 'data-flow')
    st = pg.evaluate(DATA_STATE_JS, ids)
    assert [p['on'] for p in st['procs']] == [False, False, True]
    assert not errors, errors


def test_the_data_header_is_off_with_no_processor(page):
    pg, errors = page
    view(pg, 'data-flow')
    pg.evaluate("""async () => {
        const proj = await (await fetch('/api/project')).json();
        proj.processors = [];
        delete proj.port_assignments;
        await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(proj)});
        await window.app.refreshProcessors();
        window.app.renderHardwareDock();
    }""")
    landed(pg)
    st = pg.evaluate(DATA_STATE_JS, [])
    assert st['all']['shown'] and st['all']['disabled'] and not st['all']['on']
    assert not errors, errors


def test_each_distro_has_a_cable_list_like_a_processors(page):
    pg, errors = page
    view(pg, 'power')
    pg.evaluate(CLEAR_KEYS_JS)
    seed = pg.evaluate(SEED_POWER_JS)
    landed(pg)
    ids, wall = seed['ids'], seed['wall']
    sr = ids[0]
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert all(d['btn'] and d['shown'] and not d['on'] and not d['list']
               for d in st['distros']), st

    click(pg, f'[data-lrd-field="power-distro-list-{sr}"]')
    st = pg.evaluate(POWER_STATE_JS, ids)
    d = st['distros'][0]
    assert d['on'] and d['list'] and d['stored'] == '1'
    assert d['secs'] == ['power-in', 'multi:1'], d
    assert d['heads'][0] == 'Power in'
    # the chips stay chips, and the multi's own ≡ is untouched
    multi = pg.evaluate("""(id) => {
        const sec = document.querySelector(`[data-lrd-sec="hwdock-multi-${id}-1"]`).parentElement;
        const b = sec.querySelector(`[data-lrd-field="power-cable-sheet-${id}-1"]`);
        return { grid: !!sec.querySelector('.hw-dock-grid'),
                 own: !!b, on: b.classList.contains('hw-dock-cablebtn-on') };
    }""", sr)
    assert multi == {'grid': True, 'own': True, 'on': False}

    # a home run typed in the list is the multi's own home run, every member
    ns = f'distrolist-{sr}-'
    home = pg.locator(f'[data-lrd-field="{ns}power-soca-length-{wall}-1"]')
    home.fill('100')
    home.press('Enter')
    landed(pg)
    got = pg.evaluate("""([id, wall]) => {
        const l = window.app.project.layers.find(x => x.id === wall);
        const head = document.querySelector(
            `[data-lrd-field="power-soca-length-${wall}-1"]`);
        return { stored: (l.powerSocaLengths || {})[1], head: head ? head.value : null,
                 action: window.app.history[window.app.historyIndex].action };
    }""", [sr, wall])
    assert got == {'stored': '100', 'head': '100', 'action': 'Set Multi Home Run'}

    # a circuit cable typed in the list is the circuit's cable
    c1 = seed['circuits'][0]
    ft = pg.locator(f'[data-lrd-field="{ns}power-cable-ft-{wall}-{c1}"]')
    ft.fill('10')
    ft.press('Enter')
    landed(pg)
    cable = pg.evaluate("""([wall, c]) => {
        const l = window.app.project.layers.find(x => x.id === wall);
        return ((l.powerCircuitCables || {})[c] || {}).ft;
    }""", [wall, c1])
    assert cable in (10, '10')

    # the power in's length is the distro's power in
    pin = pg.locator(f'[data-lrd-field="{ns}distro-feeder-ft-{sr}"]')
    pin.fill('150')
    pin.press('Enter')
    landed(pg)
    feeder = pg.evaluate("(id) => window.app.getDistros().find(d => d.id === id).feeder",
                         sr)
    assert feeder and feeder.get('ft') == 150

    # with the multi's own sheet open too, every field still has ONE key
    click(pg, f'[data-lrd-field="power-cable-sheet-{sr}-1"]')
    dupes = pg.evaluate("""() => {
        const seen = new Map();
        document.querySelectorAll('#hardware-dock-body [data-lrd-field]').forEach(el => {
            const k = el.dataset.lrdField;
            seen.set(k, (seen.get(k) || 0) + 1);
        });
        return [...seen].filter(([, n]) => n > 1).map(([k]) => k);
    }""")
    assert dupes == []
    click(pg, f'[data-lrd-field="power-cable-sheet-{sr}-1"]')

    # folded, the distro still shows the list it was asked for
    click(pg, f'[data-lrd-sec-id="hwdock-distro-{sr}"] > .lrd-sec-head .lrd-sec-arrow')
    shown = pg.evaluate("""(id) => {
        const list = document.querySelector(`[data-lrd-distro-list="${id}"]`);
        return !!list && list.getClientRects().length > 0;
    }""", sr)
    assert shown
    click(pg, f'[data-lrd-sec-id="hwdock-distro-{sr}"] > .lrd-sec-head .lrd-sec-arrow')

    # and the distro's ≡ closes it again
    click(pg, f'[data-lrd-field="power-distro-list-{sr}"]')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert not st['distros'][0]['on'] and not st['distros'][0]['list']
    assert st['distros'][0]['stored'] is None
    assert not errors, errors


def test_the_power_header_opens_and_closes_every_distro_list(page):
    pg, errors = page
    view(pg, 'power')
    pg.evaluate(CLEAR_KEYS_JS)
    seed = pg.evaluate(SEED_POWER_JS)
    landed(pg)
    ids = seed['ids']
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert st['all']['shown'] and not st['all']['disabled'] and not st['all']['on']
    assert st['all']['text'] == '≡'
    assert st['all']['tip'].startswith('Cable lists, Open every distro')
    place = st['place']

    click(pg, '#hw-dock-distro-lists')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert all(d['on'] and d['list'] and d['stored'] == '1' for d in st['distros']), st
    assert [d['secs'] for d in st['distros']] == [
        ['power-in', 'multi:1'], ['power-in', 'multi:1'], ['power-in']]
    assert st['all']['on'] and st['all']['pressed'] == 'true'
    assert st['place'] == place, 'the header moved'

    # one closed by its own ≡: the header offers to open again
    click(pg, f'[data-lrd-field="power-distro-list-{ids[2]}"]')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert [d['on'] for d in st['distros']] == [True, True, False]
    assert not st['all']['on']
    click(pg, '#hw-dock-distro-lists')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert all(d['on'] for d in st['distros'])

    click(pg, '#hw-dock-distro-lists')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert all(not d['on'] and not d['list'] and d['stored'] is None
               for d in st['distros']), st
    assert not st['all']['on'] and st['place'] == place

    # each distro's own ≡ still works after the header used it
    click(pg, f'[data-lrd-field="power-distro-list-{ids[1]}"]')
    st = pg.evaluate(POWER_STATE_JS, ids)
    assert [d['list'] for d in st['distros']] == [False, True, False]

    # a removed distro's list memory goes with it
    pg.evaluate("(id) => window.app.removeDistro(id)", ids[1])
    landed(pg)
    stored = pg.evaluate("(id) => localStorage.getItem(`lrd_distro_cable_list_${id}`)", ids[1])
    assert stored is None
    assert not errors, errors
