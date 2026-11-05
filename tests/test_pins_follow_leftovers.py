"""Card pins follow their cabinets when Organized leftovers renumber a show.

The owner's ruling, 2026-11-04: "follow like labels do". Organized stacking
the leftovers at the end of its cut rows (_stackLineLeftovers) took the
84 x 5 wall from 49 ports to 47, and moved the numbers under the cabinets of
every show saved before it. The cards are pinned by number, and the numbers
are the only thing that changed, so opening such a show used to leave every
socket on its old number (driving other cabinets) and the open's own commit
let go of the pins past the new last port (_releasePinsOffPorts).

Now the open reads the show both ways, the walk it was saved with and the
walk of this build, and the pins and the typed names ride their cabinets
(_followPortsByCabinet, _portMovesByCabinet). Two leftovers that became one
port are a collision: the rule the labels follow keeps one and the other pin
is released, through the server, so its socket forgets its port cable the
way any release does. A locked screen stays as it is until it is unlocked.

Run locally:
    python -m pytest tests/test_pins_follow_leftovers.py -v -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # A real Windows dialog must never open on the desktop running the tests.
    # The open answers "unavailable", so the page takes its own file input.
    def answer(body):
        return lambda r: r.fulfill(status=200, content_type='application/json', body=body)

    for kind, body in (('save-file', '{"cancelled": true, "path": null}'),
                       ('select-directory', '{"cancelled": true, "path": null}'),
                       ('open-file', '{"ok": false, "cancelled": false}')):
        pg.route(f'**/api/native-dialog/{kind}', answer(body))
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function(
        '() => window.app && Array.isArray(window.app.history) && window.app.history.length > 0',
        timeout=60000)
    pg.evaluate(HELPERS_JS)
    yield pg
    assert errors == [], errors
    context.close()


# The owner's wall on the Armor: 192 x 384 cabinets, eight a port, a bottom
# row of half-height cabinets seventeen a port. Three 20-port H cards hold it.
HELPERS_JS = r"""
window.__pf = {
    screen(o) {
        o = Object.assign({
            id: 1, name: 'Wall', type: 'screen', visible: true, locked: false,
            columns: 84, rows: 5, cabinet_width: 192, cabinet_height: 384,
            panel_width_mm: 500, panel_height_mm: 1000,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 25,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60,
            lowLatency: false, rotation: 0, halfRow: 4,
            flowPattern: 'tl-h', portMappingMode: 'organized', portNumberOrder: 'down',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
            portLabelOverridesPrimary: {}, portLabelOverridesReturn: {},
        }, o || {});
        const halfRow = o.halfRow;
        delete o.halfRow;
        const panels = [];
        let y = o.offset_y;
        for (let r = 0; r < o.rows; r++) {
            const h = r === halfRow ? o.cabinet_height / 2 : o.cabinet_height;
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c, x: o.offset_x + c * o.cabinet_width, y,
                    width: o.cabinet_width, height: h, hidden: false, blank: false,
                    halfTile: r === halfRow ? 'height' : 'none',
                    is_color1: (r + c) % 2 === 0,
                });
            }
            y += h;
        }
        o.panels = panels;
        return o;
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    // A scratch project holding only the H9 and its three cards; the screens
    // come in with the show file.
    async base() {
        const app = window.app;
        if (app._overrideEditing) app.endOverrideEdit();
        const proj = await this.j('GET', '/api/project');
        proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
        delete proj.port_assignments;
        await this.j('PUT', '/api/project', proj);
        let st = await this.j('POST', '/api/processors', { deviceId: 'novastar-h9' });
        const pid = st.processors[0].id;
        for (let s = 0; s < 3; s++) {
            st = await this.j('PUT', `/api/processors/${pid}/slots/${s * 2}`,
                { deviceId: 'novastar-card-h-20xrj45' });
        }
        const cards = st.processors[0].slots.map(s => s.card).filter(Boolean).map(c => c.id);
        const file = await this.j('GET', '/api/project');
        return { file, pid, cards };
    },
    // Port number -> [[row, col], ...] of `layer` as the walk feeds them.
    // `old`: as a build from before the stacked leftovers walked it, read
    // with the stacking stepped over, so the test does not lean on the
    // code it tests.
    walk(layer, old, byPlace) {
        const app = window.app;
        const real = app._stackLineLeftovers;
        if (old) app._stackLineLeftovers = () => 0;
        app._numberRunsByPlace = !!byPlace;
        const out = {};
        try {
            (app.calculatePortAssignments(layer) || []).forEach(it => {
                (out[it.port] = out[it.port] || []).push([it.panel.row, it.panel.col]);
            });
        } finally {
            app._stackLineLeftovers = real;
            app._numberRunsByPlace = false;
            app.calculatePortAssignments(layer);
        }
        return out;
    },
    // Everything that says which socket drives which number.
    async state(id) {
        const app = window.app;
        const layer = app.project.layers.find(l => String(l.id) === String(id));
        const mine = list => (list || []).filter(p => String(p.layerId) === String(id))
            .map(p => [p.index, p.cardId, p.port]).sort((a, b) => a[0] - b[0]);
        const project = await this.j('GET', '/api/project');
        const file = JSON.parse(app.serializeProjectForFile());
        await app.refreshPortAssignment();
        const res = app._assignment || {};
        const row = (res.screens || []).find(s => String(s.layerId) === String(id));
        return {
            required: app.getLayerPortsRequired(layer),
            labels: layer.portLabelOverridesPrimary || {},
            locked: !!layer.locked,
            client: mine((app.project.port_assignments || {}).pins),
            server: mine((project.port_assignments || {}).pins),
            saved: mine((file.port_assignments || {}).pins),
            first: mine((((app.history[0] || {}).project || {}).port_assignments || {}).pins),
            // the tray and the port list read the server's resolution
            tray: ((row && row.ports) || []).filter(p => p.cardId)
                .map(p => [p.index, p.cardId, p.port]),
            listed: ((row && row.ports) || []).length,
            action: (app.history[app.historyIndex] || {}).action,
            cables: (project.processors || []).flatMap(pr => (pr.slots || [])
                .map(sl => sl.card).filter(Boolean)
                .flatMap(c => Object.keys(c.portCables || {}).map(n => [c.id, Number(n)]))),
        };
    },
};
"""


def _base(page):
    return page.evaluate("() => window.__pf.base()")


def _show(page, base, name, version, pin='old', labels=False, cables=False, extra=None,
          by_place=False, **layer):
    """The file as `version` saved it. `pin`: 'old' pins every port of the
    walk it was saved with in order across the three cards, 'new' every port
    of this build's walk, None none. `labels`: every port of that walk named
    L<number>. Returns (file, old walk)."""
    got = page.evaluate("""([file, cards, name, version, opts]) => {
        const h = window.__pf, app = window.app;
        const p = JSON.parse(JSON.stringify(file));
        const l = h.screen(opts.layer);
        p.name = name;
        p.layers = [l].concat((opts.extra || []).map(o => h.screen(o)));
        if (version === null) delete p.app_version; else p.app_version = version;
        const held = app.project;
        app.project = p;
        let old, now;
        try {
            old = h.walk(l, true, opts.byPlace);
            now = h.walk(l, false);
        } finally {
            app.project = held;
        }
        const on = opts.pin === 'old' ? old : (opts.pin === 'new' ? now : {});
        const pins = Object.keys(on).map(Number).sort((a, b) => a - b)
            .map(n => ({ layerId: String(l.id), index: n - 1,
                         cardId: cards[Math.floor((n - 1) / 20)], port: (n - 1) % 20 + 1 }));
        p.port_assignments = { auto: false, autoRetired: true, pins };
        if (opts.labels) {
            l.portLabelOverridesPrimary = Object.fromEntries(
                Object.keys(on).map(n => [n, `L${n}`]));
        }
        if (opts.cables) {
            p.processors[0].slots.map(s => s.card).filter(Boolean).forEach(c => {
                c.portCables = {};
                for (let n = 1; n <= 20; n++) c.portCables[n] = { ft: 50 };
            });
        }
        return { file: p, old };
    }""", [base['file'], base['cards'], name, version,
           {'layer': layer, 'pin': pin, 'labels': labels, 'cables': cables, 'extra': extra,
            'byPlace': by_place}])
    return got['file'], {int(k): v for k, v in got['old'].items()}


def _open_file(page, tmp_path, project, name):
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(project), encoding='utf-8')
    page.evaluate("""() => { window.__notes = [];
        const app = window.app;
        if (!app.__pfToast) {
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => { window.__notes.push(m); return real(m, err, ms); };
            app.__pfToast = true;
        } }""")
    with page.expect_file_chooser() as chooser:
        page.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    page.wait_for_function(
        f"() => window.app.project && window.app.project.name === {json.dumps(name)}",
        timeout=10000)
    page.wait_for_timeout(1000)


def _state(page, lid=1):
    return page.evaluate("(id) => window.__pf.state(id)", lid)


def _new_walk(page, lid=1):
    got = page.evaluate("""(id) => window.__pf.walk(
        window.app.project.layers.find(l => String(l.id) === String(id)), false)""", lid)
    return {int(k): v for k, v in got.items()}


def _socket_of(n, cards):
    """The socket _show pinned old port `n` on."""
    return [cards[(n - 1) // 20], (n - 1) % 20 + 1]


def _rides(old, new):
    """Old port -> new port by _portMovesByCabinet's rule, worked out here on
    its own: a port goes where most of its cabinets went; two on one number
    leave it to the one that had it, else to more cabinets, else the lower."""
    at = {tuple(c): n for n, cells in new.items() for c in cells}
    pick = {}
    for n, cells in old.items():
        tally = {}
        for c in cells:
            to = at.get(tuple(c))
            if to is not None:
                tally[to] = tally.get(to, 0) + 1
        pick[n] = max(tally.items(), key=lambda t: (t[1], -t[0])) if tally else None
    out = {}
    for to in {p[0] for p in pick.values() if p}:
        rivals = [(n, p[1]) for n, p in pick.items() if p and p[0] == to]
        rivals.sort(key=lambda r: (r[0] != to, -r[1], r[0]))
        out[rivals[0][0]] = to
    return out


def _expected(old, new, cards):
    rides = _rides(old, new)
    return sorted([rides[n] - 1, *_socket_of(n, cards)] for n in rides)


def _notes(page):
    return page.evaluate("() => window.__notes || []")


def _follow(page, want, lid=1):
    """The state once the pins have landed on the page, on the server and in
    the first undo step."""
    return settled(page, lambda: _state(page, lid),
                   lambda v: v['client'] == want and v['server'] == want
                   and v['first'] == want)


def _landed(page, want, lid=1):
    """The state once the pins have landed on the page and on the server."""
    return settled(page, lambda: _state(page, lid),
                   lambda v: v['client'] == want and v['server'] == want)


def _unlock(page, lid=1):
    page.evaluate("""(id) => { const app = window.app;
        const l = app.project.layers.find(x => String(x.id) === String(id));
        app.selectLayer(l);
        app.selectedLayerIds = new Set([l.id]);
        app.setLockOnSelected(false); }""", lid)


def _as_saved(page):
    return page.evaluate("() => JSON.parse(window.app.serializeProjectForFile())")


@pytest.mark.parametrize('order', ['down', 'across'])
def test_an_older_show_keeps_every_socket_on_its_cabinets(page, tmp_path, order):
    base = _base(page)
    project, old = _show(page, base, f'Old{order}', '1.6.0-beta.5', labels=True,
                         portNumberOrder=order)
    assert sorted(old) == list(range(1, 50))
    _open_file(page, tmp_path, project, f'Old{order}')
    new = _new_walk(page)
    assert sorted(new) == list(range(1, 48))
    want = _expected(old, new, base['cards'])
    assert len(want) == 47
    s = _follow(page, want)
    assert s['required'] == 47
    assert s['client'] == want and s['server'] == want and s['first'] == want
    # the labels' own rule: every name on its cabinets, one of each two
    # leftovers that became one port goes
    rides = _rides(old, new)
    assert s['labels'] == {str(rides[n]): f'L{n}' for n in rides}
    notes = ' '.join(_notes(page))
    assert 'stacked' in notes and 'moved with their cabinets' in notes, notes
    assert 'so their processor ports were released' in notes, notes


def test_the_tray_the_port_list_and_the_saved_project_agree(page, tmp_path):
    """Past the repro: every reader of the pins says the same thing, the two
    sockets the stacks left over are free, and only they forget their port
    cable."""
    base = _base(page)
    project, old = _show(page, base, 'OldAgree', '1.6.0-beta.5', cables=True,
                         extra=[{'id': 2, 'name': 'Side', 'columns': 2, 'rows': 2,
                                 'halfRow': None, 'offset_x': 20000}])
    side = {'layerId': '2', 'index': 0, 'cardId': base['cards'][2], 'port': 20}
    project['port_assignments']['pins'].append(side)
    _open_file(page, tmp_path, project, 'OldAgree')
    new = _new_walk(page)
    want = _expected(old, new, base['cards'])
    s = _follow(page, want)
    assert s['client'] == want and s['tray'] == want and s['saved'] == want
    assert s['listed'] == 47
    # the other screen's pin is not touched
    other = _state(page, 2)
    assert other['client'] == [[0, base['cards'][2], 20]]
    assert other['server'] == other['client']
    # the sockets let go of forget their cables, as any release does
    held = {(c, p) for _i, c, p in want} | {(base['cards'][2], 20)}
    every = {(c, n) for c in base['cards'] for n in range(1, 21)}
    pinned_before = {tuple(_socket_of(n, base['cards'])) for n in old} | {(base['cards'][2], 20)}
    released = pinned_before - held
    assert len(released) == 2
    assert {tuple(c) for c in s['cables']} == every - released


def test_reopening_keeps_the_pins(page, tmp_path):
    base = _base(page)
    project, old = _show(page, base, 'OldReopen', '1.6.0-beta.5', labels=True)
    _open_file(page, tmp_path, project, 'OldReopen')
    want = _expected(old, _new_walk(page), base['cards'])
    first = _follow(page, want)
    assert first['client'] == want
    saved = _as_saved(page)
    assert saved['app_version'] != '1.6.0-beta.5'
    saved['name'] = 'OldReopen2'
    _open_file(page, tmp_path, saved, 'OldReopen2')
    again = _follow(page, want)
    assert again['client'] == want and again['labels'] == first['labels']
    assert not any('stacked' in n for n in _notes(page))
    # and the file as it was, opened again, lands in the same place
    project['name'] = 'OldReopen3'
    _open_file(page, tmp_path, project, 'OldReopen3')
    assert _follow(page, want)['client'] == want


def test_undo_and_redo_keep_the_followed_pins(page, tmp_path):
    base = _base(page)
    project, old = _show(page, base, 'OldUndo', '1.6.0-beta.5', labels=True)
    _open_file(page, tmp_path, project, 'OldUndo')
    want = _expected(old, _new_walk(page), base['cards'])
    s = _follow(page, want)
    page.evaluate("""() => { const app = window.app;
        const l = app.project.layers[0];
        l.name = 'Renamed';
        app.updateLayers([l], true, 'Rename For Test'); }""")
    page.wait_for_timeout(300)
    page.evaluate("() => window.app.undo()")
    back = _follow(page, want)
    assert back['client'] == want and back['server'] == want
    assert back['labels'] == s['labels']
    page.evaluate("() => window.app.redo()")
    assert _follow(page, want)['client'] == want


def test_a_locked_screen_stays_as_it_is_until_it_is_unlocked(page, tmp_path):
    base = _base(page)
    project, old = _show(page, base, 'OldLocked', '1.6.0-beta.5', labels=True, locked=True)
    saved_pins = sorted([n - 1, *_socket_of(n, base['cards'])] for n in old)
    saved_labels = {str(n): f'L{n}' for n in old}
    _open_file(page, tmp_path, project, 'OldLocked')
    held = _state(page)
    assert held['client'] == saved_pins and held['server'] == saved_pins
    assert held['labels'] == saved_labels and held['locked']
    assert any('locked' in n for n in _notes(page)), _notes(page)
    # a commit on it releases nothing
    page.evaluate("() => window.app.updateLayers(window.app.project.layers, true, 'Touch')")
    page.wait_for_timeout(300)
    assert _state(page)['client'] == saved_pins

    new = _new_walk(page)
    want = _expected(old, new, base['cards'])
    rides = _rides(old, new)
    _unlock(page)
    s = _landed(page, want)
    assert s['client'] == want and s['server'] == want and s['tray'] == want
    assert s['labels'] == {str(rides[n]): f'L{n}' for n in rides}
    assert s['action'] == 'Unlock Layers' and not s['locked']
    assert any('moved with their cabinets' in n for n in _notes(page)), _notes(page)

    # one undo puts the lock, the pins and the names back, server included
    page.evaluate("() => window.app.undo()")
    u = _landed(page, saved_pins)
    assert u['locked'] and u['client'] == saved_pins and u['server'] == saved_pins
    assert u['labels'] == saved_labels
    # redo, and an unlock after the undo, both land on the follow
    page.evaluate("() => window.app.redo()")
    r = _landed(page, want)
    assert r['client'] == want and r['server'] == want and not r['locked']
    page.evaluate("() => window.app.undo()")
    _landed(page, saved_pins)
    _unlock(page)
    r = _landed(page, want)
    assert r['client'] == want and r['server'] == want
    # nothing is left to run a second time
    page.evaluate("() => window.app.updateLayers(window.app.project.layers, true, 'Touch')")
    page.wait_for_timeout(300)
    assert _state(page)['client'] == want


def test_a_locked_screen_still_follows_after_a_save_and_a_reopen(page, tmp_path):
    """The save stamps this build on the file, so the stamp can no longer
    say the locked screen is behind: the screen carries that itself."""
    base = _base(page)
    project, old = _show(page, base, 'OldLockSave', '1.6.0-beta.5', locked=True)
    saved_pins = sorted([n - 1, *_socket_of(n, base['cards'])] for n in old)
    _open_file(page, tmp_path, project, 'OldLockSave')
    page.wait_for_timeout(300)
    saved = _as_saved(page)
    saved['name'] = 'OldLockSave2'
    _open_file(page, tmp_path, saved, 'OldLockSave2')
    assert _state(page)['client'] == saved_pins
    want = _expected(old, _new_walk(page), base['cards'])
    _unlock(page)
    s = _landed(page, want)
    assert s['client'] == want and s['server'] == want
    # unlocked and saved, it is done
    page.wait_for_timeout(300)
    saved = _as_saved(page)
    saved['name'] = 'OldLockSave3'
    _open_file(page, tmp_path, saved, 'OldLockSave3')
    assert _state(page)['client'] == want


@pytest.mark.parametrize('stamp', ['1.6.0-beta.6', '1.6.0', '1.6.1'])
def test_a_show_saved_by_this_numbering_is_left_as_it_is(page, tmp_path, stamp):
    base = _base(page)
    project, _old = _show(page, base, f'New{stamp}', stamp, pin='new')
    pins = sorted([p['index'], p['cardId'], p['port']]
                  for p in project['port_assignments']['pins'])
    assert len(pins) == 47
    _open_file(page, tmp_path, project, f'New{stamp}')
    s = _state(page)
    assert s['client'] == pins and s['server'] == pins
    assert not any('stacked' in n for n in _notes(page))


def test_predates_leftover_stacks_reads_the_beta(page):
    got = page.evaluate("""() => ['1.6.0-beta.4', '1.6.0-beta.5', '1.6.0-beta.6',
        '1.6.0-beta.10', '1.6.0', '1.5.4', '1.6.1', '1.7.0-beta.1', '', null]
        .map(v => window.app.predatesLeftoverStacks({ app_version: v }))""")
    assert got == [True, True, False, False, False, True, False, False, True, True]


def test_a_custom_screen_keeps_its_drawing_and_its_pins(page, tmp_path):
    """Today's behavior: a saved drawing is never rewritten, so its numbers
    did not move and its pins have nothing to follow."""
    paths, n = {}, 0
    for row in range(5):
        step = 17 if row == 4 else 8
        for c in range(0, 84, step):
            n += 1
            paths[str(n)] = [{'row': row, 'col': x} for x in range(c, min(c + step, 84))]
    base = _base(page)
    project, _old = _show(page, base, 'OldCustom', '1.6.0-beta.5', pin=None,
                          flowPattern='custom', lastFlowPattern='tl-h',
                          customPortPaths=paths, customPortIndex=n + 1)
    pins = [[i, base['cards'][i // 20], i % 20 + 1] for i in range(n)]
    project['port_assignments']['pins'] = [
        {'layerId': '1', 'index': i, 'cardId': c, 'port': p} for i, c, p in pins]
    _open_file(page, tmp_path, project, 'OldCustom')
    s = _state(page)
    assert s['client'] == pins and s['server'] == pins


def test_max_capacity_has_nothing_to_follow(page, tmp_path):
    base = _base(page)
    project, old = _show(page, base, 'OldMax', '1.6.0-beta.5',
                         processorType='brompton', portMappingMode='max-capacity')
    pins = sorted([n - 1, *_socket_of(n, base['cards'])] for n in old)
    _open_file(page, tmp_path, project, 'OldMax')
    s = _state(page)
    assert s['client'] == pins and s['server'] == pins


def test_an_armor_screen_flagged_max_capacity_follows_as_organized(page, tmp_path):
    """The open puts such a screen back on Organized, so it walks with the
    stacks, and the follow reads it after that."""
    base = _base(page)
    project, old = _show(page, base, 'OldArmorMax', '1.6.0-beta.5')
    project['layers'][0]['portMappingMode'] = 'max-capacity'
    assert sorted(old) == list(range(1, 50))
    _open_file(page, tmp_path, project, 'OldArmorMax')
    want = _expected(old, _new_walk(page), base['cards'])
    s = _follow(page, want)
    assert s['required'] == 47 and s['client'] == want and s['server'] == want


def test_the_older_down_numbering_and_the_stacks_compose(page, tmp_path):
    """A show from before beta 4 went through both changes: its numbers by
    place, then the stacks. Every socket still lands on its cabinets."""
    base = _base(page)
    project, old = _show(page, base, 'OldBoth', '1.6.0-beta.3', by_place=True)
    middle = page.evaluate("""(file) => { const h = window.__pf, app = window.app;
        const held = app.project;
        app.project = file;
        try { return h.walk(file.layers[0], true); } finally { app.project = held; } }""", project)
    middle = {int(k): v for k, v in middle.items()}
    assert middle != old
    _open_file(page, tmp_path, project, 'OldBoth')
    new = _new_walk(page)
    first = _rides(old, middle)
    second = _rides(middle, new)
    want = sorted([second[first[n]] - 1, *_socket_of(n, base['cards'])]
                  for n in old if first.get(n) in second)
    assert len(want) == 47
    s = _follow(page, want)
    assert s['client'] == want and s['server'] == want and s['first'] == want


def test_a_pin_on_a_taken_over_port_stays_with_it(page, tmp_path):
    drawn = [{'row': 0, 'col': c} for c in range(8)]
    base = _base(page)
    project, old = _show(page, base, 'OldOverride', '1.6.0-beta.5',
                         customPortOverrides=[1], customPortPaths={'1': drawn})
    assert 1 in old
    _open_file(page, tmp_path, project, 'OldOverride')
    new = _new_walk(page)
    assert new[1] == old[1]
    want = _expected(old, new, base['cards'])
    assert want[0] == [0, *_socket_of(1, base['cards'])]
    assert _follow(page, want)['client'] == want


def test_the_opens_own_repair_and_the_follow_land_in_one_first_step(page, tmp_path):
    """A taken-over number with nothing drawn closes up on the open
    (trimPortsOffWall, the pins through /merge) ahead of the follow: both
    reach the server in order and the first undo step holds the end of it."""
    base = _base(page)
    project, old = _show(page, base, 'OldHole', '1.6.0-beta.5',
                         customPortOverrides=[5], customPortPaths={'5': []})
    assert 5 not in old
    _open_file(page, tmp_path, project, 'OldHole')
    new = _new_walk(page)
    assert sorted(new) == list(range(1, 48))
    closed = {(n - 1 if n > 5 else n): cells for n, cells in old.items()}
    rides = _rides(closed, new)
    want = sorted([rides[n - 1 if n > 5 else n] - 1, *_socket_of(n, base['cards'])]
                  for n in old if (n - 1 if n > 5 else n) in rides)
    assert _follow(page, want)['client'] == want


def test_a_mirror_holds_nothing_to_follow(page, tmp_path):
    base = _base(page)
    project, _old = _show(page, base, 'OldMirror', '1.6.0-beta.5', extra=[
        {'id': 2, 'name': 'Copy', 'offset_x': 20000, 'dataMirrorOf': 1,
         'portLabelOverridesPrimary': {'48': 'KEEP'}}])
    _open_file(page, tmp_path, project, 'OldMirror')
    page.wait_for_timeout(200)
    assert _state(page, 2)['labels'] == {'48': 'KEEP'}


def test_nothing_pinned_or_named_says_nothing(page, tmp_path):
    base = _base(page)
    project, _old = _show(page, base, 'OldBare', '1.6.0-beta.5', pin=None)
    _open_file(page, tmp_path, project, 'OldBare')
    assert not any('stacked' in n for n in _notes(page))


def test_a_mapping_change_keeps_pins_on_their_numbers_like_labels(page, tmp_path):
    """The label rule is defined here (test_power_labels_like_data): Organized
    to Max Capacity leaves a typed name on its number, and the pin stays on
    its number with it. A number with no port now releases its pin (no
    phantom ports, _releasePinsOffPorts). The follow is for a show opened on
    a build that numbers it differently, and no setting comes into it."""
    base = _base(page)
    project, _old = _show(page, base, 'NewMapping', '1.6.0-beta.6', pin='new',
                          labels=True, columns=5, rows=3, cabinet_width=256,
                          cabinet_height=256, halfRow=None, processorType='brompton',
                          flowPattern='tl-v')
    _open_file(page, tmp_path, project, 'NewMapping')
    before = _state(page)
    assert before['required'] == 3
    page.evaluate("""() => { const app = window.app;
        app.selectLayer(app.project.layers[0]);
        app.selectedLayerIds = new Set([app.project.layers[0].id]);
        document.getElementById('mapping-max-capacity').click(); }""")
    after = settled(page, lambda: _state(page), lambda v: v['server'] == v['client']
                    and v['required'] == 2)
    assert after['required'] == 2
    assert after['labels'] == before['labels']
    assert after['client'] == before['client'][:2]
