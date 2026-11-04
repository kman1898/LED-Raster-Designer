"""A locked screen sharing a multi box keeps its circuits.

The owner's standing rule: a locked screen stays unchanged until it is
unlocked, and any attempt says why (never silent). Two screens pinned to one
(distro, number) are one physical box, and the box deals its tails across
both. A gesture on the UNLOCKED screen - a circuit unplugged, the multi
cleared, re-pinned, moved, split, welded, a circuit dropped on a pip, a tail
moved, a share, a custom circuit cleared, a face row changed, a panel edit -
re-deals that box, and a locked member that does not store its tails used to
be dealt again with it (or written, to hold them: _materializeSocaBox stamped
its shown tails into its powerSocaPhasePos).

Now every such gesture runs the shared-box lock (_lockedPowerTrial): when the
locked screen's tails, numbers or circuits would move, the gesture is put back
whole and the locked error names the screen and why; when they stay exactly
as they are (the locked screen stores its tails), the gesture goes through
and the locked screen is not written at all.

The walls are synthetic: cabinets of 200 x 200 drawing 150 W on 208 V x
20 A. UnWall (unlocked, first in layer order) draws three custom circuits,
one per column; LockWall (locked) draws two. Both are pinned to box 1 of
distro S, so the box deals UnWall tails 1-3 and LockWall 4-5.
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


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(f'{e.message} {e.stack}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    pg._ls_errors = errors
    yield pg
    assert not errors, errors
    context.close()


HELPERS_JS = r"""
window.__ls = {
    // `screens` in layer order: { name, columns, fields }, each 5 rows of
    // 200 x 200 cabinets stacked down the canvas. `distros` on the show.
    // Returns the screen ids in the same order.
    async reset(spec) {
        const app = window.app, r = window.canvasRenderer;
        app._overrideEditing = null;
        app._circuitTrimHeld = null;
        await app._layerSavesSettled();
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        project.distros = (spec.distros || []).map(d =>
            Object.assign({ ratingA: 400, voltage: 208, phase: 3 }, d));
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        for (let i = 0; i < spec.screens.length; i++) {
            const s = spec.screens[i];
            await fetch('/api/layer/add', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: s.name, columns: s.columns, rows: 5,
                    cabinet_width: 200, cabinet_height: 200, offset_x: 0, offset_y: i * 2000,
                }),
            });
        }
        project = await (await fetch('/api/project')).json();
        const power = (fields) => Object.assign({
            powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v',
            powerCustomPath: false, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            powerSplitters: { enabled: false, maxWays: 3,
                              manual: { merge: [], split: [] } },
            powerLabelOverrides: {}, powerCircuitCables: {},
            sizeByDimensions: false, locked: false,
        }, fields || {});
        const ids = spec.screens.map(s => {
            const l = project.layers.find(x => x.name === s.name);
            Object.assign(l, power(s.fields));
            return l.id;
        });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('locked_shared_reset');
        const live = app.project.layers.find(l => l.id === ids[0]);
        app.selectLayer(live);
        app.selectedLayerIds = new Set([live.id]);
        app._circuitTailCache = null;
        r.viewMode = 'power';
        r.zoom = 0.2; r.panX = 20; r.panY = 60;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Locked Shared Baseline');
        window.__notes = [];
        window.__errs = [];
        if (!app.__lsToastWrapped) {
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => {
                (err ? window.__errs : window.__notes).push(m);
                return real(m, err, ms);
            };
            app.__lsToastWrapped = true;
        }
        return ids;
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    // circuit -> [multi number, tail, distro] off the plan the paperwork
    // reads, and the last history entry.
    state(id) {
        const app = window.app, l = this.layer(id);
        app._circuitTailCache = null;
        const feeds = {};
        app.getSocaPlan(l).forEach(s => s.legs.forEach(g => {
            feeds[g.circuit] = [s.distroId ? s.number : null, g.leg, s.distroId || null];
        }));
        return {
            feeds,
            history: (app.history && app.history[app.historyIndex])
                ? app.history[app.historyIndex].action : null,
        };
    },

    power(id) {
        const l = this.layer(id), out = {};
        Object.keys(l).forEach(k => { if (k.startsWith('power')) out[k] = l[k]; });
        return JSON.parse(JSON.stringify(out));
    },
};
"""

SHARED_ERR = 'LockWall is locked, and this would move its circuits on a shared multi.'


def cells(rows, cols):
    """Path steps over rows x cols, row by row."""
    return [{'row': r, 'col': c} for r in rows for c in cols]


def custom(columns):
    """One custom circuit per column, 5 cabinets each."""
    return {'powerFlowPattern': 'custom',
            'powerCustomPaths': {str(i + 1): cells(range(5), [i]) for i in range(columns)}}


def reset(page, unwall=None, lockwall=None, distros=None, unwall_columns=3):
    """UnWall (unlocked) then LockWall (locked), both on box 1 of distro S
    unless `unwall` / `lockwall` lay other fields over them."""
    un = dict(custom(unwall_columns), powerSocaDistro={'1': 'dsh'}, powerSocaNumber={'1': 1})
    un.update(unwall or {})
    lk = dict(custom(2), powerSocaDistro={'1': 'dsh'}, powerSocaNumber={'1': 1}, locked=True)
    lk.update(lockwall or {})
    ids = page.evaluate("(s) => window.__ls.reset(s)", {
        'distros': distros or [{'id': 'dsh', 'name': 'S'}],
        'screens': [{'name': 'UnWall', 'columns': unwall_columns, 'fields': un},
                    {'name': 'LockWall', 'columns': 2, 'fields': lk}],
    })
    page.wait_for_timeout(300)
    return ids


def st(page, lid):
    return page.evaluate("(id) => window.__ls.state(id)", lid)


def power(page, lid):
    return page.evaluate("(id) => window.__ls.power(id)", lid)


def errs(page):
    return page.evaluate("() => window.__errs")


def run(page, js, *args):
    """Run a gesture `js` (a function body over app, ids) and let its saves
    settle."""
    out = page.evaluate("([js, args]) => (new Function('app', 'args', js))(window.app, args)",
                        [js, list(args)])
    page.wait_for_timeout(300)
    return out


STORED = {'powerSocaPhasePos': {'1': [4, 5]}}
DEALT = {'1': [1, 4, 'dsh'], '2': [1, 5, 'dsh']}


def refused(page, un, lk, un_before, lk_power, history='Locked Shared Baseline'):
    """Nothing moved: UnWall reads as before, LockWall's stores and tails are
    untouched, no history entry, and the locked error says who and why."""
    assert st(page, un)['feeds'] == un_before
    assert power(page, lk) == lk_power
    assert st(page, lk)['feeds'] == DEALT
    assert st(page, un)['history'] == history
    e = errs(page)
    assert any(SHARED_ERR in m for m in e), e


def passed(page, lk, lk_power, history):
    """The gesture went through: LockWall was not written and kept every
    tail, nothing was said, and the gesture took its history entry."""
    assert power(page, lk) == lk_power
    assert st(page, lk)['feeds'] == DEALT
    assert errs(page) == []
    assert st(page, lk)['history'] == history


def _both(page, gesture, *args, history, check=None, **spec):
    """The refusal case (LockWall dealt, not stored) then the pass-through
    case (LockWall stores 4-5)."""
    un, lk = reset(page, **spec)
    assert st(page, lk)['feeds'] == DEALT
    un0, lk0 = st(page, un)['feeds'], power(page, lk)
    run(page, gesture, un, lk, *args)
    refused(page, un, lk, un0, lk0)

    spec = dict(spec)
    spec['lockwall'] = dict(spec.get('lockwall') or {}, **STORED)
    un, lk = reset(page, **spec)
    lk0 = power(page, lk)
    run(page, gesture, un, lk, *args)
    passed(page, lk, lk0, history)
    if check:
        check(st(page, un)['feeds'])


# ── Unplug circuit ────────────────────────────────────────────────────────

def test_unplug_circuit(page):
    """UnWall's circuit 2 off the box frees tail 2; LockWall, dealt the
    lowest free tails, would slide onto 2 and 4."""
    def check(feeds):
        assert feeds['1'] == [1, 1, 'dsh'] and feeds['3'] == [1, 3, 'dsh']
        assert feeds['2'][2] is None
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app._clearCircuitChip(l, 1, 2);""", history='Unplug Circuit', check=check)


# ── Unplug multi ──────────────────────────────────────────────────────────

def test_unplug_multi(page):
    """UnWall's whole multi off the box frees 1-3; LockWall would slide to
    1-2."""
    def check(feeds):
        assert all(f[2] is None for f in feeds.values())
    _both(page, """app._clearMultis([{ layerId: args[0], soca: 1 }], 'Unplug Multi');""",
          history='Unplug Multi', check=check)


# ── multi number: the pin moved to another box ────────────────────────────

def test_set_multi_number(page):
    """UnWall re-pinned to box 2 leaves box 1 to LockWall, which would deal
    1-2."""
    def check(feeds):
        assert feeds == {'1': [2, 1, 'dsh'], '2': [2, 2, 'dsh'], '3': [2, 3, 'dsh']}
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app.setSocaNumber(l, 1, 2);""", history='Set Multi Number', check=check)


# ── multi distro: taken off the distro ────────────────────────────────────

def test_set_multi_distro(page):
    def check(feeds):
        assert all(f[2] is None for f in feeds.values())
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app.setSocaDistro(l, 1, null);""", history='Assign Multi Distro', check=check)


# ── a multi dropped on a circuit joins the box (takeSocaOnto) ─────────────

def test_take_onto_a_shared_box(page):
    """UnWall starts on no distro; LockWall alone on box 1 deals 1-2. The
    take joins box 1 with UnWall first in layer order: unheld, LockWall
    would be dealt 4-5 (before this, LockWall was written to hold 1-2)."""
    un, lk = reset(page, unwall={'powerSocaDistro': {}, 'powerSocaNumber': {}})
    alone = {'1': [1, 1, 'dsh'], '2': [1, 2, 'dsh']}
    assert st(page, lk)['feeds'] == alone
    un0, lk0 = st(page, un)['feeds'], power(page, lk)
    take = """const l = app.project.layers.find(x => x.id === args[0]);
        return app.takeSocaOnto(l, 3, 'dsh', 1, 'Assign Multi Distro');"""
    r = run(page, take, un)
    assert r['ok'] is False and r['locked'] is True
    assert st(page, un)['feeds'] == un0
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == alone
    assert any(SHARED_ERR in m for m in errs(page)), errs(page)

    un, lk = reset(page, unwall={'powerSocaDistro': {}, 'powerSocaNumber': {}},
                   lockwall={'powerSocaPhasePos': {'1': [1, 2]}})
    lk0 = power(page, lk)
    r = run(page, take, un)
    assert r['ok'] is True
    assert st(page, un)['feeds'] == {'1': [1, 3, 'dsh'], '2': [1, 4, 'dsh'], '3': [1, 5, 'dsh']}
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == alone
    assert errs(page) == []
    assert st(page, un)['history'] == 'Assign Multi Distro'


# ── split ─────────────────────────────────────────────────────────────────

def test_split_multi(page):
    """Split after UnWall's first circuit: the second part starts off the
    box, freeing 2-3; LockWall would deal 2-3."""
    def check(feeds):
        assert feeds['1'] == [1, 1, 'dsh']
        assert feeds['2'][2] is None and feeds['3'][2] is None
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app.splitSocaAfter(l, 1, 1);""", history='Split Multi', check=check)


# ── un-split ──────────────────────────────────────────────────────────────

def test_unsplit_multi(page):
    """UnWall split after circuit 1, only the first part on the box (tail
    1), LockWall dealt 2-3. Welding takes UnWall to three circuits: unheld,
    LockWall would be dealt 4-5 (before this, it was written to hold 2-3)."""
    split = {'powerSocaSplits': [1]}
    un, lk = reset(page, unwall=split)
    after_split = {'1': [1, 2, 'dsh'], '2': [1, 3, 'dsh']}
    assert st(page, lk)['feeds'] == after_split
    un0, lk0 = st(page, un)['feeds'], power(page, lk)
    weld = """const l = app.project.layers.find(x => x.id === args[0]);
        return app.unsplitSocaAfter(l, 1);"""
    assert run(page, weld, un) is False
    assert st(page, un)['feeds'] == un0
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == after_split
    assert any(SHARED_ERR in m for m in errs(page)), errs(page)

    un, lk = reset(page, unwall=split, lockwall=STORED)
    lk0 = power(page, lk)
    assert run(page, weld, un) is True
    assert st(page, un)['feeds'] == {'1': [1, 1, 'dsh'], '2': [1, 2, 'dsh'], '3': [1, 3, 'dsh']}
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == DEALT
    assert errs(page) == []
    assert st(page, un)['history'] == 'Un-split Multi'


# ── a circuit pip dropped on another box ──────────────────────────────────

def test_circuit_pip_drop(page):
    """UnWall's circuit 3 dropped on box 2's pip 1: the head part keeps box
    1 with two circuits, freeing tail 3; LockWall would deal 3-4."""
    def check(feeds):
        assert feeds == {'1': [1, 1, 'dsh'], '2': [1, 2, 'dsh'], '3': [2, 1, 'dsh']}
    _both(page, """app._dockDropTail({ distroId: 'dsh', number: 2, tail: 1, title: 'S2' },
        { kind: 'run', layerId: args[0], num: 3 });""", history='Assign Circuit', check=check)


# ── phase balance: a multi's tails moved by hand ──────────────────────────

def test_move_circuits_on_the_box(page):
    """UnWall's tails moved to 1, 2 and 6 hold LockWall at 4-5 only while
    it stores them; dealt, LockWall would take 3-4. (Moved to 3, 4, 6 the
    refusal case: LockWall dealt 1-2.)"""
    un, lk = reset(page)
    un0, lk0 = st(page, un)['feeds'], power(page, lk)
    move = """const l = app.project.layers.find(x => x.id === args[0]);
        return app.setSocaCircuitPositions(l, 1, args[1], 3);"""
    assert run(page, move, un, [3, 4, 6]) is False
    refused(page, un, lk, un0, lk0)

    un, lk = reset(page, lockwall=STORED)
    lk0 = power(page, lk)
    assert run(page, move, un, [1, 2, 6]) is True
    passed(page, lk, lk0, 'Move Circuits')
    assert st(page, un)['feeds'] == {'1': [1, 1, 'dsh'], '2': [1, 2, 'dsh'], '3': [1, 6, 'dsh']}


# ── a share (2fer) on the unlocked screen ─────────────────────────────────

def test_share_circuits(page):
    """UnWall's circuits 1 and 2 shared through a 2fer: two circuits on the
    box instead of three, freeing tail 3; LockWall would deal 3-4."""
    def check(feeds):
        assert len(feeds) == 2
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app.mergeSplitterCircuits(l, [1, 2]);""", history='Edit Splitter Groups', check=check)


def test_batch_share_3fer_them(page):
    """"3fer them" over UnWall's three circuits: one circuit on the box,
    freeing 2-3; LockWall would deal 2-3. (The batch verb runs the repack
    lock, which runs the shared-box lock with it.)"""
    def check(feeds):
        assert len(feeds) == 1
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app.batchShareCircuits(l, [1, 2, 3], 3, '3fer Circuits');""",
          history='3fer Circuits', check=check)


# ── Clear Circuit (custom) ────────────────────────────────────────────────

def test_custom_clear_circuit(page):
    """The Clear Circuit button on UnWall's circuit 2: two circuits left on
    the box; LockWall would slide down a tail."""
    def check(feeds):
        assert sorted(feeds) == ['1', '3']
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        l.powerCustomIndex = 2;
        document.getElementById('power-custom-clear-circuit').click();""",
          history='Power Custom Clear Circuit', check=check)


def test_custom_clear_all(page):
    """Clear All on UnWall: its circuits all go, freeing 1-3; LockWall
    would deal 1-2."""
    def check(feeds):
        assert all(f[2] is None for f in feeds.values())
    _both(page, """document.getElementById('power-custom-clear-all').click();""",
          history='Power Custom Clear All', check=check)


def test_custom_cabinet_added(page):
    """UnWall drawing a fourth circuit on its fourth column: the first
    cabinet makes four circuits on the box; LockWall would deal 5-6."""
    def check(feeds):
        # held 4-5 stay LockWall's: the new circuit takes tail 6
        assert feeds['4'] == [1, 6, 'dsh']
    paths = {str(i + 1): cells(range(5), [i]) for i in range(3)}
    _both(page, """const l = app.project.layers.find(x => x.id === args[0]);
        l.powerCustomIndex = 4;
        const panel = (l.panels || []).find(p => p.row === 0 && p.col === 3);
        app.addPanelToCustomPowerPath(panel, l);""",
          history='Power Custom Path Edit', check=check, unwall_columns=4,
          unwall={'powerCustomPaths': paths})


# ── a distro output row changed ───────────────────────────────────────────

FACE = [{'id': 'dsh', 'name': 'S', 'system': '120/208',
         'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                         'breakerA': 20}]}]


def test_distro_output_rows(page):
    """Box 1 is a Socapex on a face distro, LockWall storing tails 5-6.
    Changed to an L21-30 (three circuits) the stored 5-6 no longer fit the
    box, so LockWall would be dealt again, onto 4-5: refused, the row kept.
    A third Socapex added moves nothing: it goes through and LockWall is
    not written."""
    held = {'powerSocaPhasePos': {'1': [5, 6]}}
    on_56 = {'1': [1, 5, 'dsh'], '2': [1, 6, 'dsh']}
    patch = """return !!app.updateDistro('dsh', { outputRows: args[1] });"""
    un, lk = reset(page, distros=FACE, lockwall=held)
    un0, lk0 = st(page, un)['feeds'], power(page, lk)
    assert st(page, lk)['feeds'] == on_56
    l2130 = [{'id': 'r1', 'connector': 'l2130', 'count': 2, 'coupling': 'll', 'breakerA': 20}]
    assert run(page, patch, un, l2130) is False
    assert st(page, un)['feeds'] == un0
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == on_56
    assert any(SHARED_ERR in m for m in errs(page)), errs(page)
    assert page.evaluate("() => window.app.getDistros()[0].outputRows[0].connector") == 'soca'
    assert st(page, un)['history'] == 'Locked Shared Baseline'

    un, lk = reset(page, distros=FACE, lockwall=held)
    lk0 = power(page, lk)
    three = [dict(FACE[0]['outputRows'][0], count=3)]
    assert run(page, patch, un, three) is True
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == on_56
    assert errs(page) == []
    assert page.evaluate("() => window.app.getDistros()[0].outputRows[0].count") == 3
    assert st(page, un)['history'] == 'Edit Distro'


# ── a panel edit on the unlocked screen (the edit funnel) ─────────────────

def test_panel_watts_edit(page):
    """UnWall automatic, three columns: one circuit at 150 W (tail 1),
    LockWall dealt 2-3. At 600 W each column is a circuit: UnWall would
    take 1-3 and LockWall be dealt 4-5. Refused, the watts put back.
    LockWall storing 2-3, UnWall deals 1, 4, 5 around it and the edit
    stands."""
    auto = {'powerFlowPattern': 'tl-v', 'powerCustomPaths': {}}
    edit = """const l = app.project.layers.find(x => x.id === args[0]);
        app.selectedLayerIds = new Set([l.id]);
        app.applyToSelectedLayers(x => { x.panelWatts = 600; });
        app.updateLayers([l]);
        app.saveState('Update Properties');"""
    un, lk = reset(page, unwall=auto)
    held = {'1': [1, 2, 'dsh'], '2': [1, 3, 'dsh']}
    assert st(page, lk)['feeds'] == held
    lk0 = power(page, lk)
    run(page, edit, un)
    assert page.evaluate("(id) => window.__ls.layer(id).panelWatts", un) == 150
    assert st(page, un)['feeds'] == {'1': [1, 1, 'dsh']}
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == held
    assert any(SHARED_ERR in m for m in errs(page)), errs(page)

    un, lk = reset(page, unwall=auto, lockwall={'powerSocaPhasePos': {'1': [2, 3]}})
    lk0 = power(page, lk)
    run(page, edit, un)
    assert page.evaluate("(id) => window.__ls.layer(id).panelWatts", un) == 600
    assert st(page, un)['feeds'] == {'1': [1, 1, 'dsh'], '2': [1, 4, 'dsh'], '3': [1, 5, 'dsh']}
    assert power(page, lk) == lk0
    assert st(page, lk)['feeds'] == held
    assert errs(page) == []


# ── an unlocked screen is never held ──────────────────────────────────────

def test_unlocked_partner_takes_the_gesture_as_before(page):
    """With LockWall unlocked the same unplug goes through and the partner
    holds its tails the way every join and split always held them."""
    un, lk = reset(page, lockwall={'locked': False})
    run(page, """const l = app.project.layers.find(x => x.id === args[0]);
        app._clearCircuitChip(l, 1, 2);""", un)
    assert st(page, lk)['feeds'] == DEALT
    assert power(page, lk)['powerSocaPhasePos'] == {'1': [4, 5]}
    assert errs(page) == []
    assert st(page, un)['history'] == 'Unplug Circuit'
