"""Phase balancing and the ONE power-label authority (v0.12.0).

The user's report (Kelly Clarkson, screen SR), in two rounds:

Round 1: after #power-distro-balance wrote powerSocaPhasePos {1: [6,2,5,1,3]},
the canvas showed S1-1, S1-3, S1-5, S1-4, S1-5 - a duplicate S1-5 and no
S1-2. Root cause: the AUTO label arithmetic (((num-1)%6)+1) never read the
balanced fan positions, so auto labels and stale user overrides collided.
The first fix surfaced the TRUE tails - and the wall then read S1-6, S1-2,
S1-5, S1-1, S1-3: the balancer's raw permutation.

Round 2 (user: "they needed to be numerical in order", second screenshot
showed the rotation S1-5, S1-6, S1-1, S1-2, S1-3): a wall must READ IN
ORDER. Balancing chooses WHICH tails are in use, never their order.

The rule under test (user decision, fixed):

  - Balancing (or a breaker offset, or anything else) selects the tail SET
    a multi occupies. Circuits map to the chosen tails ascending in wall
    (circuit) order - a wall on tails {1,2,3,5,6} reads S1-1, S1-2, S1-3,
    S1-5, S1-6 left to right, gaps where a tail is skipped. No permutation
    or rotation ever surfaces, on any surface.
  - Stored arrays normalize ascending ON READ: projects carrying an old
    permutation ([6,2,5,1,3]) or rotation ([5,6,1,2,3]) display in wall
    order immediately, same tails occupied, no re-balance needed.
  - An AUTO-NAMED label (the # template, no override) numbers the TRUE
    PHYSICAL TAIL. The valid tail range is the soca HARDWARE's 6 legs,
    never the used-circuit count.
  - Explicit powerLabelOverrides are the user's text and NEVER change.
  - (NOT COVERED HERE: upstream also asserted that breaker STICKER rows and
    SCHEMATIC drop labels follow the balanced tails. Those two tests -
    test_breaker_sticker_rows_land_on_the_balanced_tails, which needs the
    Labels feature (_lblMultiAtDistro), and
    test_schematic_drop_labels_and_feed_text_follow_balanced_tails, which
    needs the schematic sheet renderer - were removed rather than skipped,
    because neither feature exists on this branch. The label AUTHORITY they
    consumed is still pinned below; restore them with those features.)
  - Unbalanced screens (natural positions) keep today's labels
    byte-identical - including custom-drawn screens with gaps in the
    numbering, where the drawn number is user intent.
  - Everything flows through getPowerCircuitLabel / getSocaPlan: canvas
    tiles, soca plan legDetail, schematic drop labels + feed bubbles, the
    report soca table and the breaker stickers must agree.

Plus the splitter fan-out label placement fix: the shared circuit's ONE
bubble sits centered across the span of its run-head panels, stubs
radiating to every head; single-run circuits keep the first-panel label.

Browser tests use the synthetic-project style of test_power_splitters.py.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_power_phase_labels.py -v --browser chromium
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# What the old balancer stored on SR, and what the wall must read: the same
# five tails, ascending in wall order.
STORED = [6, 2, 5, 1, 3]
DISPLAYED = [1, 2, 3, 5, 6]


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(e2e_server):
    """Same isolation as test_power_splitters.py: snapshot the live e2e
    server's project when this module starts and put it back when it ends."""
    import copy
    import app as app_module
    saved_project = copy.deepcopy(app_module.current_project)
    saved_next = app_module.next_layer_id
    yield
    app_module.current_project = saved_project
    app_module.next_layer_id = saved_next


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# Same builder shape as test_power_splitters.py. `five()` is the synthetic
# reproduction rig: five 5-tile column circuits (organized tl-v at a 5-tile
# capacity) on ONE 6-leg multi. `srlike()` is the user's SR shape: nine
# drawn custom paths merged [[1,2],[3,4],[5,6],[7,8]] into five shared
# circuits numbered 1,3,5,7,9. `unequal()` is the balancer rig: five drawn
# circuits of 5/4/3/2/4 tiles, deliberately unequal so the tail-subset
# choice matters.
HELPERS_JS = """
window.__ph = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            columns: 5, rows: 5,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 100, powerVoltage: 100, powerAmperage: 5,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            group_id: null,
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                });
            }
        }
        o.panels = panels;
        return o;
    },
    five(extra) {
        // 100V x 5A / 100W = 5-tile capacity, tl-v organized: one circuit
        // per 5-tall column, five circuits on one 6-leg multi
        return this.screen(Object.assign({ id: 1, name: 'Five' }, extra || {}));
    },
    srlike(extra) {
        const paths = {};
        for (let c = 0; c < 9; c++) paths[c + 1] = [{row:0,col:c},{row:1,col:c}];
        return this.screen(Object.assign({
            id: 2, name: 'SRLike', columns: 9, rows: 2,
            powerFlowPattern: 'custom', powerCustomIndex: 10,
            powerCustomPaths: paths,
            powerSplitters: { enabled: false, maxWays: 2,
                manual: { merge: [[1, 2], [3, 4], [5, 6], [7, 8]], split: [] } },
        }, extra || {}));
    },
    unequal(extra) {
        // circuit tiles 5,4,3,2,4 -> 500/400/300/200/400 W on one 5-circuit
        // multi assigned to a 208V 3-phase distro; 100V circuits default to
        // the rotating-ln scheme (tails 1..6 -> X Y Z X Y Z)
        const cols = { 1: [[0,0],[1,0],[2,0],[0,1],[1,1]],
                       2: [[2,1],[0,2],[1,2],[2,2]],
                       3: [[0,3],[1,3],[2,3]],
                       4: [[0,4],[1,4]],
                       5: [[2,4],[0,5],[1,5],[2,5]] };
        const paths = {};
        for (const k in cols) paths[k] = cols[k].map(rc => ({row: rc[0], col: rc[1]}));
        return this.screen(Object.assign({
            id: 3, name: 'Unequal', columns: 6, rows: 3,
            powerAmperage: 6,
            powerFlowPattern: 'custom', powerCustomIndex: 6,
            powerCustomPaths: paths,
            powerSocaDistro: { 1: 'd1' },
        }, extra || {}));
    },
    distro() {
        // Named 'D', not 'D1': a multi takes its name from its distro plus
        // its number under that distro, so the one multi on this distro is
        // D1 and its circuits read D1-1, D1-2, ... A distro called 'D1'
        // would name its first multi 'D11', which is correct and unreadable.
        return { id: 'd1', name: 'D', ratingA: 400, voltage: 208, phase: 3 };
    },
    withProject(project, fn) {
        const saved = window.app.project;
        window.app.project = Object.assign(
            { layers: [], groups: [], canvases: [], rack: [] }, project);
        try { return fn(); } finally { window.app.project = saved; }
    },
    labelsOf(S) {
        // The naming index is prepared once per render burst and dropped on
        // the next microtask. A test that edits a name and reads it back
        // inside ONE evaluate never reaches that microtask, so it would read
        // the index built before its own edit.
        window.app._circuitTailCache = null;
        return window.app.screenCircuits(S).map(c =>
            window.app.getPowerCircuitLabel(S, c.num));
    },
    planOf(S) {
        window.app._circuitTailCache = null;
        return window.app.getSocaPlan(S).map(s => ({
            soca: s.soca, number: s.number, name: s.name,
            length: s.length, legs: s.legs.map(l => l.leg),
        }));
    },
    // 100V x 5A / 100W = 5-tile capacity, tl-v organized: one circuit per
    // 5-tall column, so `columns` IS the circuit count. Eight columns is two
    // multis - six circuits on the first, two on the second.
    col5(id, name, columns, extra) {
        return this.screen(Object.assign({ id, name, columns, rows: 5 },
                                         extra || {}));
    },
    box(id, name) {
        return { id, name, ratingA: 400, voltage: 208, phase: 3 };
    },
};
"""


# ── 1. balanced positions drive the auto labels, in wall order ────────────

def test_balanced_positions_produce_ascending_true_tail_labels(page):
    """powerSocaPhasePos {1: [6,2,5,1,3]} on a five-circuit multi: the wall
    reads S1-1, S1-2, S1-3, S1-5, S1-6 left to right - the TRUE tails of
    the chosen set, ascending in wall order, tail 4 skipped, all five
    distinct. The stored permutation itself never surfaces."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.five({ powerSocaPhasePos: { 1: [6, 2, 5, 1, 3] } });
        return ph.withProject({ layers: [S] }, () => ph.labelsOf(S));
    }""")
    assert out == ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6']
    assert out == sorted(out), 'the wall must read in ascending order'
    assert len(set(out)) == 5, 'no duplicate labels after balancing'


def test_unbalanced_screen_labels_name_the_multi_they_are_on(page):
    """An unbalanced multi still reads 1..N down the wall.

    The gapped case is the one that MOVED, deliberately. Nine drawn paths
    merged into five circuits numbered 1, 3, 5, 7, 9 are five circuits on
    ONE multi - the soca panel has always said so - but the label used to be
    arithmetic on the raw drawn number, which wrapped circuit 7 onto a
    second multi and printed S2-1. There is no second multi. Now that a
    multi's number comes from its distro rather than from the screen's own
    template, that arithmetic cannot survive at all: 'S2' would name a multi
    that does not exist and could collide with a real S2 on another screen.
    So a circuit is named by the multi it is on and the tail it lands on,
    and the five read S1-1..S1-5."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const plain = ph.five();
        const gapped = ph.srlike();
        return {
            plain: ph.withProject({ layers: [plain] }, () => ph.labelsOf(plain)),
            gapped: ph.withProject({ layers: [gapped] }, () => ph.labelsOf(gapped)),
            socas: ph.withProject({ layers: [gapped] }, () =>
                window.app.getSocaPlan(gapped).map(s => s.name)),
        };
    }""")
    assert out['plain'] == ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5']
    assert out['socas'] == ['S1'], 'the five merged circuits are ONE multi'
    assert out['gapped'] == ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5'], \
        'the labels name the multi the soca panel says they are on'


def test_explicit_override_survives_balancing_verbatim(page):
    """A powerLabelOverride is the user's text: balancing renames the AUTO
    labels around it (in wall order) and never touches the override itself."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.five({
            powerSocaPhasePos: { 1: [6, 2, 5, 1, 3] },
            powerLabelOverrides: { 2: 'FOH RIG B' },
        });
        return ph.withProject({ layers: [S] }, () => ph.labelsOf(S));
    }""")
    assert out == ['S1-1', 'FOH RIG B', 'S1-3', 'S1-5', 'S1-6']


def test_user_sr_shape_regression_wall_reads_in_order(page):
    """The exact SR shape from the report (merges [[1,2],[3,4],[5,6],[7,8]],
    stale overrides on 6-9, stored [6,2,5,1,3]): the AUTO-labelled shared
    circuits read S1-1, S1-2, S1-3 in wall order - never the permutation's
    S1-6, S1-2, S1-5 - and the overrides print verbatim, so the whole wall
    reads S1-1..S1-5 left to right."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.srlike({
            powerLabelOverrides: { 6: 'S1-3', 7: 'S1-4', 8: 'S1-4', 9: 'S1-5' },
            powerSocaPhasePos: { 1: [6, 2, 5, 1, 3] },
        });
        return ph.withProject({ layers: [S] }, () => ph.labelsOf(S));
    }""")
    # circuits 1, 3, 5 are auto-named; 7 and 9 wear the user's overrides
    assert out == ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5']


# ── 2. the soca plan reports physical tails; the load math is untouched ───

def test_soca_plan_legs_report_ascending_tails_amps_watts_unchanged(page):
    """getSocaPlan's legDetail `leg` is the physical tail of the balanced
    SET, ascending in circuit order ([1,2,3,5,6] for stored [6,2,5,1,3]);
    tiles/watts/amps per circuit and the multi total are byte-identical to
    the unbalanced plan - balancing only renumbers."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const planOf = (S) => ph.withProject({ layers: [S] }, () =>
            window.app.getSocaPlan(S).map(s => ({
                soca: s.soca, watts: s.watts, amps: s.amps,
                legs: s.legs.map(l => ({ leg: l.leg, circuit: l.circuit,
                    tiles: l.tiles, watts: l.watts, amps: l.amps })),
            })));
        return {
            flat: planOf(ph.five()),
            bal: planOf(ph.five({ powerSocaPhasePos: { 1: [6, 2, 5, 1, 3] } })),
        };
    }""")
    flat, bal = out['flat'], out['bal']
    assert [l['leg'] for l in flat[0]['legs']] == [1, 2, 3, 4, 5]
    assert [l['leg'] for l in bal[0]['legs']] == DISPLAYED, \
        'legDetail reports the occupied tails ascending, in circuit order'
    strip = lambda plan: [{**l, 'leg': None} for s in plan for l in s['legs']]
    assert strip(flat) == strip(bal), 'amps/watts/tiles untouched by balancing'
    assert (flat[0]['watts'], flat[0]['amps']) == (bal[0]['watts'], bal[0]['amps'])
# ── 3. schematic power sheet agrees ───────────────────────────────────────
# ── 4. canvas fan-out label placement (defect A) ──────────────────────────

def test_shared_circuit_label_centers_over_the_run_head_span(page):
    """Three 5-tile columns shared through a 3fer (heads at x=64/192/320):
    the ONE label bubble draws centered over the head span (x=192), not on
    run 1's first panel; a single-run circuit keeps its first-panel label at
    (64, 64)."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const app = window.app, cr = window.canvasRenderer;
        const arcs = [];
        const orig = CanvasRenderingContext2D.prototype.arc;
        try {
            CanvasRenderingContext2D.prototype.arc = function (x, y, r, ...a) {
                arcs.push([x, y]);
                return orig.call(this, x, y, r, ...a);
            };
            const S = ph.screen({ id: 7, name: 'Wall', columns: 3, rows: 5,
                powerAmperage: 15,
                powerSplitters: { enabled: true, maxWays: 3,
                                  manual: { merge: [], split: [] } } });
            const shared = ph.withProject({ layers: [S] }, () => {
                cr.renderPowerArrows(S);
                return arcs.splice(0);
            });
            const P = ph.screen({ id: 8, name: 'One', columns: 1, rows: 5 });
            const single = ph.withProject({ layers: [P] }, () => {
                cr.renderPowerArrows(P);
                return arcs.splice(0);
            });
            return { shared, single };
        } finally {
            CanvasRenderingContext2D.prototype.arc = orig;
        }
    }""")
    assert out['shared'] == [[192, 64]], \
        'shared label anchor x = midpoint of the run-head span (64..320)'
    assert out['single'] == [[64, 64]], 'single-run placement unchanged'


def test_fanout_stubs_radiate_from_the_bubble_to_every_head(page):
    """The dashed stubs start at the bubble center and reach EVERY run head
    (three stubs for a 3fer), not run-1-head to the others."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const app = window.app, cr = window.canvasRenderer;
        const moves = [], lines = [];
        let dashed = false;
        const ctxp = CanvasRenderingContext2D.prototype;
        const oMove = ctxp.moveTo, oLine = ctxp.lineTo, oDash = ctxp.setLineDash;
        try {
            ctxp.setLineDash = function (seg) { dashed = !!(seg && seg.length); return oDash.call(this, seg); };
            ctxp.moveTo = function (x, y) { if (dashed) moves.push([x, y]); return oMove.call(this, x, y); };
            ctxp.lineTo = function (x, y) { if (dashed) lines.push([x, y]); return oLine.call(this, x, y); };
            const S = ph.screen({ id: 9, name: 'Wall', columns: 3, rows: 5,
                powerAmperage: 15,
                powerSplitters: { enabled: true, maxWays: 3,
                                  manual: { merge: [], split: [] } } });
            ph.withProject({ layers: [S] }, () => cr.renderPowerArrows(S));
            return { moves, lines };
        } finally {
            ctxp.moveTo = oMove; ctxp.lineTo = oLine; ctxp.setLineDash = oDash;
        }
    }""")
    assert out['moves'] == [[192, 64]] * 3, \
        'every stub starts at the centered bubble'
    assert sorted(out['lines']) == [[64, 64], [192, 64], [320, 64]], \
        'one stub per run head, including run 1'


# ── 5. wall-order semantics: read normalization + the subset balancer ─────

def test_stored_permutation_and_rotation_normalize_on_read(page):
    """Both wrong shapes the user photographed - the raw permutation
    [6,2,5,1,3] and the rotation [5,6,1,2,3] - read back as the ascending
    tail set [1,2,3,5,6]: same tails occupied, wall order, no re-balance.
    A shuffle of the NATURAL set ([2,1,3,4,5]) IS natural - labels stay
    byte-identical S1-1..S1-5. The legacy block offset keeps its purpose:
    offset 1 on five circuits occupies tails 2..6, already ascending."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const posOf = (store) => {
            const S = ph.five(store);
            return ph.withProject({ layers: [S] }, () => ({
                pos: window.app.socaCircuitPositions(S, 1, 5),
                labels: ph.labelsOf(S),
            }));
        };
        return {
            perm: posOf({ powerSocaPhasePos: { 1: [6, 2, 5, 1, 3] } }),
            rot: posOf({ powerSocaPhasePos: { 1: [5, 6, 1, 2, 3] } }),
            natp: posOf({ powerSocaPhasePos: { 1: [2, 1, 3, 4, 5] } }),
            off: posOf({ powerSocaPhaseOffset: { 1: 1 } }),
        };
    }""")
    assert out['perm']['pos'] == DISPLAYED
    assert out['rot']['pos'] == DISPLAYED, \
        'the rotation is the same tail set - it must read in wall order'
    assert out['rot']['labels'] == ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6']
    assert out['natp']['pos'] == [1, 2, 3, 4, 5]
    assert out['natp']['labels'] == ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5'], \
        'a shuffled natural set is natural - labels byte-identical'
    assert out['off']['pos'] == [2, 3, 4, 5, 6], \
        'the offset still selects tails off+1..off+L'
    assert out['off']['labels'] == ['S1-2', 'S1-3', 'S1-4', 'S1-5', 'S1-6']


def test_balancer_picks_a_tail_subset_and_returns_it_sorted(page):
    """The real balance routine on an unequal rig (circuit watts
    500/400/300/200/400 on one 5-circuit multi, 208V 3-phase, rotating-ln
    X Y Z X Y Z): naturally X=700, Y=800, Z=300 (50% worst-leg imbalance);
    the best tail SET skips tail 4 - X=500, Y=400+200, Z=300+400 - a flat
    16.7%. The proposed move is that subset, strictly ascending
    [1,2,3,5,6]: the balancer skips a tail when balance calls for it and
    never returns a permutation."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.unequal();
        return ph.withProject({ layers: [S], distros: [ph.distro()] }, () => {
            const r = window.app.suggestPhaseBalance();
            return { before: r.before, after: r.after,
                     moves: r.moves.map(m => ({ from: m.from, to: m.to })),
                     store: (S.powerSocaPhasePos || {})[1] || null };
        });
    }""")
    assert abs(out['before'] - 50.0) < 0.5
    assert abs(out['after'] - 100.0 / 6) < 0.5, 'skipping tail 4 evens the legs'
    assert [m['to'] for m in out['moves']] == [[1, 2, 3, 5, 6]], \
        'the move is the tail SET, ascending, tail 4 skipped'
    for m in out['moves']:
        assert m['to'] == sorted(m['to']), 'positions strictly ascending'
        assert len(set(m['to'])) == len(m['to'])
    assert out['store'] is None, 'suggest only suggests - nothing persisted'


SHOW_PANELS_JS = """(store) => {
    const ph = window.__ph;
    const app = window.app;
    const S = ph.five(Object.assign({
        powerSplitters: { enabled: true, maxWays: 2,
                          manual: { merge: [], split: [] } },
    }, store || {}));
    return ph.withProject({ layers: [S] }, () => {
        const savedLayer = app.currentLayer;
        try {
            app.currentLayer = S;
            // the stamp updatePowerCapacityDisplay writes for the selected
            // layer - the editor sizes itself from it on auto screens
            S._powerCircuitsRequired = app.screenCircuitCount(S);
            app.refreshSocaRuns();
            app.refreshSplitterPanel();
            app.updatePowerLabelEditor();
            const txt = el => el ? el.textContent.replace(/\\s+/g, ' ').trim() : null;
            return {
                authority: ph.labelsOf(S),
                tails: app.getSocaPlan(S).flatMap(s => s.legs.map(l => l.leg)),
                socaRows: [...document.querySelectorAll('#power-soca-runs label')]
                    .map(txt).filter(t => t && / legs? /.test(t)),
                splitterRows: [...document.querySelectorAll(
                        '#power-splitters .splitter-circuit-row label')]
                    .map(l => txt(l).split(' \\u00b7 ')[0]),
                editor: [...document.querySelectorAll('#power-label-list > div')]
                    .filter(r => r.querySelector('input[type=text]'))
                    .map(r => ({
                        col: txt(r.children[1]),
                        title: r.querySelector('input[type=checkbox]').title,
                        placeholder: r.querySelector('input[type=text]').placeholder,
                    })),
            };
        } finally {
            app.currentLayer = savedLayer;
        }
    });
}"""


# ── 6. the LEFT PANE panels print the authority's numbers ─────────────────

def test_left_pane_panels_match_authority_for_balanced_multi(page):
    """User report round 3: 'when balanced the circuit numbers should match
    in the left pane too'. On a balanced multi (stored [6,2,5,1,3], wall
    reads tails 1,2,3,5,6) every sidebar Power-panel row prints the
    authority's numbers: splitter rows and label-editor placeholders carry
    getPowerCircuitLabel verbatim, and the editor's number column and
    checkbox tooltip show the PHYSICAL TAIL - 1, 2, 3, 5, 6 down the pane,
    identical to the canvas bubbles - never the sequential 1..5."""
    out = page.evaluate(SHOW_PANELS_JS,
                        {"powerSocaPhasePos": {"1": STORED}})
    labels = ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6']
    assert out['authority'] == labels
    assert out['tails'] == DISPLAYED
    assert out['splitterRows'] == labels, \
        'splitter rows must print the authority labels'
    assert [r['placeholder'] for r in out['editor']] == labels, \
        'editor placeholders must print the authority labels'
    assert [r['col'] for r in out['editor']] == ['1', '2', '3', '5', '6'], \
        'the editor number column lists the physical tails, wall order'
    assert [r['title'] for r in out['editor']] == labels, \
        'the row tooltip names the circuit like the canvas bubble does'
    assert out['socaRows'] == ['S1 \u00b7 5 legs \u00b7 25.0 A'], \
        'the multi header keeps its name and leg count'


def test_left_pane_editor_column_stays_sequential_when_unbalanced(page):
    """Byte-identity pin for the today path: no phase positions stored, the
    editor keeps its sequential number column and 'Circuit N' tooltips, and
    the splitter rows keep the sequential labels."""
    out = page.evaluate(SHOW_PANELS_JS, {})
    labels = ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5']
    assert out['splitterRows'] == labels
    assert [r['col'] for r in out['editor']] == ['1', '2', '3', '4', '5']
    assert [r['title'] for r in out['editor']] == [
        'Circuit 1', 'Circuit 2', 'Circuit 3', 'Circuit 4', 'Circuit 5']
    assert [r['placeholder'] for r in out['editor']] == labels


def test_balance_dialog_names_circuits_by_their_labels(page):
    """The Balance dialog's move rows name each circuit by its CURRENT
    authority label (the bubble on the canvas), never a re-derived 'circuit
    N' ordinal - and clicking Apply repaints the splitter rows and the
    label editor synchronously with the new tails."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const app = window.app;
        const S = ph.unequal(
            { powerSplitters: { enabled: false, maxWays: 2,
                                manual: { merge: [], split: [] } } });
        return ph.withProject({ layers: [S], distros: [ph.distro()] }, () => {
            const savedLayer = app.currentLayer;
            const savedUpdate = app.updateLayers;
            try {
                app.currentLayer = S;
                app.updateLayers = () => {};
                const r = app.suggestPhaseBalance();
                app.showBalanceDialog();
                const el = document.getElementById('balance-modal');
                const body = el.textContent.replace(/\\s+/g, ' ');
                el.querySelector('.balance-apply').click();
                const txt = e => e.textContent.replace(/\\s+/g, ' ').trim();
                return {
                    moveLabels: r.moves.map(m => m.labels),
                    body,
                    ordinal: /circuit \\d/.test(body),
                    modalGone: !document.getElementById('balance-modal'),
                    splitterAfter: [...document.querySelectorAll(
                            '#power-splitters .splitter-circuit-row label')]
                        .map(l => txt(l).split(' \\u00b7 ')[0]),
                    editorAfter: [...document.querySelectorAll(
                            '#power-label-list input[type=text]')]
                        .map(i => i.placeholder),
                };
            } finally {
                app.currentLayer = savedLayer;
                app.updateLayers = savedUpdate;
            }
        });
    }""")
    # This multi is on the distro named 'D', so it is D1 and its circuits
    # read D1-1..D1-6 - the distro naming its own load, the way a card names
    # its own ports on the Data tab.
    assert out['moveLabels'] == [['D1-1', 'D1-2', 'D1-3', 'D1-4', 'D1-5']], \
        "moves carry the circuits' pre-move authority labels"
    # natural [1..5] -> best [1,2,3,5,6]: circuits 4 and 5 move, and the
    # dialog names them D1-4 and D1-5 - their labels on the canvas today
    assert 'D1-4 (' in out['body'] and 'D1-5 (' in out['body']
    assert 'tail 4 \u2192' in out['body']
    assert not out['ordinal'], 'no "circuit N" ordinals anywhere in the dialog'
    assert out['modalGone']
    assert out['splitterAfter'] == ['D1-1', 'D1-2', 'D1-3', 'D1-5', 'D1-6'], \
        'Apply repaints the splitter rows with the new tails, no round-trip'
    assert out['editorAfter'] == ['D1-1', 'D1-2', 'D1-3', 'D1-5', 'D1-6'], \
        'Apply repaints the label editor with the new tails, no round-trip'


def test_wall_order_wins_brute_force_and_apply_stores_sorted(page):
    """Wall order is the hard constraint and imbalance the objective under
    it: on the unequal rig the balancer's answer matches a brute force over
    ALL six 5-of-6 tail subsets with wall-order assignment - permutations
    are simply not in the space. Applying the moves stores the sorted set
    and the wall reads strictly ascending."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.unequal();
        return ph.withProject({ layers: [S], distros: [ph.distro()] }, () => {
            const app = window.app;
            // brute force: every 5-of-6 tail subset, wall-order assignment
            let bruteBest = Infinity;
            for (let skip = 1; skip <= 6; skip++) {
                S.powerSocaPhasePos = { 1: [1, 2, 3, 4, 5, 6].filter(p => p !== skip) };
                bruteBest = Math.min(bruteBest, app._worstImbalance());
            }
            delete S.powerSocaPhasePos;
            const r = app.suggestPhaseBalance();
            // apply without the server round-trip (synthetic layer)
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            let stored, labels;
            try {
                app.applyPhaseBalance(r.moves);
                stored = (S.powerSocaPhasePos || {})[1] || null;
                labels = ph.labelsOf(S);
            } finally { app.updateLayers = orig; }
            return { bruteBest, after: r.after, stored, labels };
        });
    }""")
    assert abs(out['after'] - out['bruteBest']) < 0.1, \
        'the balancer finds the best subset achievable WITHOUT permuting'
    assert out['stored'] == [1, 2, 3, 5, 6], 'applied moves store the sorted set'
    # On the distro named 'D', so the multi is D1 (see ph.distro).
    assert out['labels'] == ['D1-1', 'D1-2', 'D1-3', 'D1-5', 'D1-6']
    assert out['labels'] == sorted(out['labels'])


# ── which phasing scheme a distro runs on, and where it came from ─────────
#
# Reported as "if i select 208 then the phasing should default to 208", and
# settled as "a change manually should override the default".
#
# powerPhasingFor already derived the line-to-line scheme when the circuit
# voltage matched the service voltage, and getDistroLoads already ran the leg
# maths on it - the rollup was right the whole time. What was wrong was the
# SELECT: it marked its options from the rollup's schemeId, which is only set
# once a multi has landed on the distro, so a distro with nothing assigned
# marked nothing and the browser fell back to whichever option was first in
# the list. A fresh 208V distro therefore read as a line-to-neutral scheme.
#
# And the select had no way to SAY "deriving": a scheme picked by hand looked
# identical to one the voltage chose, though only the first survives a voltage
# change. It now carries a Match-voltage entry that clears distro.phasing,
# which is both the state and the way back to it.

PHASING_STATE_JS = """(opts) => {
    const ph = window.__ph;
    const d = Object.assign(ph.distro(), opts.distro || {});
    const layers = opts.unassigned ? [] : [ph.unequal({ powerVoltage: opts.circuitV })];
    return ph.withProject({ layers: layers, distros: [d] }, () => {
        const st = window.app.distroPhasingState(d);
        const roll = window.app.getDistroLoads().find(b => b.id === d.id);
        return { scheme: st.scheme.id, derived: st.derived.id,
                 explicit: st.explicit, circuitVoltage: st.circuitVoltage,
                 rollup: roll && roll.legs ? roll.legs.schemeId : null };
    });
}"""


def test_a_deriving_distro_follows_the_circuit_voltage(page):
    """208V circuits on a 208V service are line-to-line; the same service
    feeding 120V circuits is line-to-neutral. The rollup and the state the
    panel reads have to agree - they are the same derivation."""
    ll = page.evaluate(PHASING_STATE_JS, {'circuitV': 208})
    assert ll['scheme'] == 'paired-ll', f"208V circuits did not land line-to-line: {ll}"
    assert ll['rollup'] == 'paired-ll', f"the leg maths disagrees with the panel: {ll}"
    assert not ll['explicit'], f"nobody picked this scheme, so it is derived: {ll}"

    ln = page.evaluate(PHASING_STATE_JS, {'circuitV': 120})
    assert ln['scheme'] == 'rotating-ln', f"120V circuits did not land line-to-neutral: {ln}"
    assert ln['rollup'] == 'rotating-ln', f"the leg maths disagrees with the panel: {ln}"


def test_a_distro_with_nothing_assigned_still_reports_a_scheme(page):
    """The reported defect. With no multi on it there is no rollup to read a
    scheme off, and the panel used to fall through to the first option in the
    list - so a 208V distro read as a line-to-neutral scheme until something
    was assigned to it."""
    out = page.evaluate(PHASING_STATE_JS, {'unassigned': True})
    assert out['circuitVoltage'] == 208, (
        f"an unassigned distro has no circuits to read, so it is taken at its "
        f"own voltage: {out}")
    assert out['scheme'] == 'paired-ll', (
        f"a 208V distro with nothing on it did not report the 208V scheme: {out}")
    assert not out['explicit'], out


def test_an_explicit_scheme_survives_a_voltage_change(page):
    """Somebody read the box. A later voltage change moves the DEFAULT and
    must not overwrite a choice - that choice is paperwork about how a real
    distro is wired, and 208V is predominantly but not always paired XY ZX
    YZ."""
    for circuit_v in (120, 208):
        out = page.evaluate(PHASING_STATE_JS, {
            'circuitV': circuit_v, 'distro': {'phasing': 'paired-ll-alt'}})
        assert out['scheme'] == 'paired-ll-alt', (
            f"an explicit scheme was overwritten at {circuit_v}V circuits: {out}")
        assert out['explicit'], out
        assert out['rollup'] == 'paired-ll-alt', (
            f"the leg maths ignored the explicit scheme at {circuit_v}V: {out}")
    # and the derivation is still there underneath, which is what the panel
    # shows on the entry that hands the choice back to the voltage
    assert page.evaluate(PHASING_STATE_JS, {
        'circuitV': 208, 'distro': {'phasing': 'paired-ll-alt'}})['derived'] == 'paired-ll'


PHASING_SELECT_JS = """(opts) => {
    const ph = window.__ph;
    const d = Object.assign(ph.distro(), opts.distro || {});
    const out = ph.withProject(
        { layers: [ph.unequal({ powerVoltage: opts.circuitV })], distros: [d] },
        () => {
            window.app.refreshDistroPanel();
            const sel = document.querySelector('#power-distros .distro-phasing');
            if (!sel) return null;
            return { value: sel.value,
                     text: sel.options[sel.selectedIndex].text,
                     firstValue: sel.options[0].value,
                     firstText: sel.options[0].text,
                     options: sel.options.length };
        });
    window.app.refreshDistroPanel();   // put the real project's rows back
    return out;
}"""


def test_the_phasing_select_says_whether_it_is_deriving(page):
    """Two distros can run the same scheme, one because somebody read the box
    and one because nobody has - and only the second follows a voltage change.
    The select has to be able to tell them apart, and to offer the way back."""
    ll = page.evaluate(PHASING_SELECT_JS, {'circuitV': 208})
    assert ll, "the distro row built no phasing select"
    assert ll['value'] == '', f"a derived scheme is not shown as derived: {ll}"
    assert 'Line-to-line' in ll['text'], (
        f"the derived entry does not name what it resolves to: {ll}")
    assert 'XY ZX YZ' in ll['text'], (
        f"the derived entry does not name the pattern it resolves to: {ll}")

    ln = page.evaluate(PHASING_SELECT_JS, {'circuitV': 120})
    assert ln['value'] == '', f"a derived scheme is not shown as derived: {ln}"
    assert 'Line-to-neutral' in ln['text'], (
        f"the derived entry did not follow the circuit voltage: {ln}")

    picked = page.evaluate(PHASING_SELECT_JS, {
        'circuitV': 208, 'distro': {'phasing': 'paired-ll-alt'}})
    assert picked['value'] == 'paired-ll-alt', (
        f"an explicitly picked scheme is not the one shown: {picked}")
    assert picked['firstValue'] == '', (
        f"there is no way back to deriving once a scheme is picked - choosing "
        f"one would be a one-way door: {picked}")
    assert picked['options'] == ll['options'], (
        f"the option list changed shape between the two states: {picked}")


def test_choosing_a_scheme_and_choosing_the_voltage_again_round_trips(page):
    """The whole workflow through the real panel: a 208V distro fed by 208V
    circuits derives the line-to-line scheme, an explicit pick sticks across a
    voltage change, and the follow-the-voltage entry hands the choice back."""
    page.locator('[data-mode="power"]').click()
    page.wait_for_timeout(400)
    seeded = page.evaluate("""() => {
        const app = window.app;
        const set = (id, v) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.value = v;
            el.dispatchEvent(new Event('change', { bubbles: true }));
        };
        set('power-voltage-select', '208');
        set('power-panel-watts', '400');
        const d = app.getDistros().length ? app.getDistros()[0] : app.addDistro();
        const l = app.currentLayer;
        app.getSocaPlan(l).forEach(s => app.setSocaDistro(l, s.soca, d.id));
        app.updateDistro(d.id, { voltage: 208, phase: 3, phasing: '' });
        app.refreshDistroPanel();
        return d.id;
    }""")
    page.wait_for_timeout(600)
    read = """() => {
        const sel = document.querySelector('#power-distros .distro-phasing');
        const d = window.app.getDistros()[0];
        return { value: sel.value, text: sel.options[sel.selectedIndex].text,
                 stored: d.phasing === undefined ? '(undefined)' : d.phasing };
    }"""
    try:
        derived = page.evaluate(read)
        assert derived['value'] == '' and 'Line-to-line' in derived['text'], (
            f"208V circuits on a 208V distro did not derive the 208V scheme "
            f"through the real panel: {derived}")
        assert derived['stored'] in (None, '(undefined)'), (
            f"the panel stamped an explicit scheme just by rendering, which "
            f"would stop the derivation ever firing again: {derived}")

        page.select_option('#power-distros .distro-phasing', 'rotating-ll')
        page.wait_for_timeout(600)
        page.evaluate("""() => {
            window.app.updateDistro(window.app.getDistros()[0].id, { voltage: 240 });
            window.app.refreshDistroPanel();
        }""")
        page.wait_for_timeout(400)
        kept = page.evaluate(read)
        assert kept['value'] == 'rotating-ll' and kept['stored'] == 'rotating-ll', (
            f"changing the voltage overwrote a scheme somebody chose: {kept}")

        page.select_option('#power-distros .distro-phasing', '')
        page.wait_for_timeout(600)
        back = page.evaluate(read)
        assert back['value'] == '' and back['stored'] is None, (
            f"the follow-the-voltage entry did not hand the choice back to "
            f"the voltage: {back}")
    finally:
        page.evaluate("""(id) => {
            window.app.removeDistro(id);
            window.app.refreshDistroPanel();
        }""", seeded)


# ── 8. ONE SCHEME, ONE NAME ───────────────────────────────────────────────
#
# A user asked "what is the difference between line to line and paired?".
# The question only existed because the SAME scheme was labelled two ways:
# "208V - paired, XY ZX YZ" in the list and "line-to-line" on the derived
# entry. Both were true and they name DIFFERENT AXES, so showing one here and
# the other there made two orthogonal things look like alternatives:
#
#   coupling   line-to-neutral (one leg, X) or line-to-line (two, XY)
#   order      rotating (advance every circuit) or paired (two circuits on
#              one assignment, then advance)
#
# And the volts in those names were not merely untidy, they were wrong: the
# distro voltage select offers 400V and 415V, where line-to-neutral is 230V,
# so "120V - rotating" lied on every EU service. The leg maths was already
# voltage-agnostic (V / sqrt(3)); only the labels assumed North America.

SCHEMES_JS = """() => window.app.powerPhasingSchemes().map(s => ({
    id: s.id, name: s.name, pattern: s.pattern,
    order: s.order, lineToLine: s.lineToLine }))"""

SCHEME_IDS = ['rotating-ln', 'paired-ln', 'paired-ll', 'paired-ll-alt',
              'rotating-ll']


def test_every_scheme_name_gives_both_axes_and_none_leads_with_a_voltage(page):
    """The five patterns and their ids are fixed. Each name says its coupling
    first and its dealing order second, and none of them carries a voltage -
    line-to-neutral is 120V on a 208V service and 230V on a 400V one, so the
    figure belongs to the SERVICE and cannot name a scheme."""
    import re
    schemes = page.evaluate(SCHEMES_JS)
    assert [s['id'] for s in schemes] == SCHEME_IDS, (
        f"the scheme list changed shape - ids and order are fixed: {schemes}")
    for s in schemes:
        m = re.match(r'^(Line-to-neutral|Line-to-line), (rotating|paired) '
                     r'\(([XYZ ]+)\)$', s['name'])
        assert m, f"the name does not give both axes: {s}"
        coupling, order, pattern = m.groups()
        assert (coupling == 'Line-to-line') == s['lineToLine'], (
            f"the name's coupling contradicts the leg maths: {s}")
        assert order == s['order'], f"the name's order is not the record's: {s}"
        assert pattern == s['pattern'], f"the name's pattern drifted: {s}"
        assert not re.search(r'\d\s*V', s['name']), (
            f"a voltage names this scheme, and the same scheme is a different "
            f"voltage on a 400V service: {s}")


NAMING_JS = """(opts) => {
    const ph = window.__ph;
    const app = window.app;
    const d = Object.assign(ph.distro(), opts.distro || {});
    const out = ph.withProject(
        { layers: [ph.unequal({ powerVoltage: opts.circuitV })], distros: [d] },
        () => {
            app.refreshDistroPanel();
            const sel = document.querySelector('#power-distros .distro-phasing');
            app.showPhasingHelp();
            const modal = document.getElementById('phasing-help-modal');
            const cells = [...modal.querySelectorAll(
                '.phasing-scheme-table tr')].slice(1).map(tr => ({
                    name: tr.children[0].childNodes[0].textContent.trim(),
                    spread: tr.children[1].textContent.trim(),
                }));
            const res = {
                options: [...sel.options].map(o => o.text),
                values: [...sel.options].map(o => o.value),
                selected: sel.options[sel.selectedIndex].text,
                groups: [...sel.querySelectorAll('optgroup')].map(g => ({
                    label: g.label,
                    options: [...g.querySelectorAll('option')].map(o => o.text),
                })),
                derivedName: app.distroPhasingState(d).derived.name,
                modalNames: cells.map(c => c.name),
                modalSpreads: cells.map(c => c.spread),
                modalText: modal.textContent.replace(/\\s+/g, ' '),
            };
            modal.remove();
            return res;
        });
    app.refreshDistroPanel();   // put the real project's rows back
    return out;
}"""


def test_one_scheme_one_name_in_the_select_the_derived_entry_and_the_help(page):
    """The same scheme must never be called two different things. The select
    prints powerPhasingSchemes' names, the derived entry prints the name of
    what it resolves to, and the help modal's table is generated from the same
    records - so all three carry byte-identical strings."""
    schemes = page.evaluate(SCHEMES_JS)
    names = [s['name'] for s in schemes]
    out = page.evaluate(NAMING_JS, {'circuitV': 208})

    assert out['options'][1:] == names, (
        f"the select does not print the scheme names verbatim: {out}")
    assert out['modalNames'] == names, (
        f"the help modal names the schemes differently from the select - the "
        f"exact drift that made a user ask what the difference was: {out}")
    assert out['selected'] == f"Follow the circuit voltage — {out['derivedName']}", (
        f"the derived entry names its scheme its own way: {out}")
    assert out['derivedName'] == 'Line-to-line, paired (XY ZX YZ)', (
        f"208V circuits on a 208V service derive the line-to-line scheme: {out}")
    for name in names:
        assert out['modalText'].count(name) >= 1, (
            f"{name!r} is missing from the help modal: {out['modalText']}")
    # the modal's circuit row is read out of _circuitLegs itself, so prose
    # cannot drift from the maths
    assert out['modalSpreads'] == [
        'X Y Z X Y Z', 'X X Y Y Z Z', 'XY XY ZX ZX YZ YZ',
        'XY XY YZ YZ ZX ZX', 'XY XZ YZ XY XZ YZ'], out['modalSpreads']


def test_the_help_modal_explains_the_two_axes(page):
    """The answer to "what is the difference between line to line and
    paired?" lives here: they are not alternatives, they are the two axes
    every scheme name carries."""
    out = page.evaluate(NAMING_JS, {'circuitV': 208})
    text = out['modalText']
    assert 'Two things vary, and they are independent' in text, text
    for phrase in ('Coupling', 'Order',
                   'Line-to-neutral is one hot and a neutral',
                   'Line-to-line is two hots and no neutral',
                   'Rotating advances on every circuit',
                   'Paired puts two consecutive circuits'):
        assert phrase in text, f"{phrase!r} missing from the help modal: {text}"
    assert 'divided by √3' in text, (
        f"the modal does not say where the line-to-neutral figure comes "
        f"from: {text}")
    # neither line-to-line paired map may be sold as the standard one
    for claim in ('best-attested', 'most common', 'recommended', 'default pattern'):
        assert claim not in text.lower(), (
            f"the modal ranks one documented map above another: {claim!r}")


def test_deriving_and_the_schemes_are_visibly_different_kinds_of_entry(page):
    """"Match voltage" sitting in one flat list beside "paired" read as if
    the two were alternatives of the same kind. They are not: one is an
    instruction to the app, the others describe how a box is wired - so they
    are grouped as two, and the derive entry is phrased as an instruction."""
    schemes = page.evaluate(SCHEMES_JS)
    out = page.evaluate(NAMING_JS, {'circuitV': 208})
    assert len(out['groups']) == 2, (
        f"the two kinds of entry are not separated: {out['groups']}")
    derive, wiring = out['groups']
    assert derive['options'] == [out['selected']], (
        f"the derive entry does not stand alone in its group: {out}")
    assert wiring['options'] == [s['name'] for s in schemes], (
        f"the schemes are not grouped together: {out}")
    assert out['values'][0] == '', (
        "deriving is still the empty value that clears distro.phasing")
    assert derive['options'][0].startswith('Follow the circuit voltage'), (
        f"the derive entry does not read as an instruction: {derive}")
    assert not any(o.startswith('Follow') for o in wiring['options']), out


def test_the_resolved_volts_follow_the_distro_not_the_scheme(page):
    """A EU 400V service: line-to-neutral is 230V there, 120V on a 208V one.
    The figures are shown against the GROUP, derived from that distro's own
    voltage - the scheme names stay identical on both services."""
    na = page.evaluate(NAMING_JS, {'circuitV': 208})
    eu = page.evaluate(NAMING_JS,
                       {'circuitV': 400, 'distro': {'voltage': 400}})
    assert na['groups'][1]['options'] == eu['groups'][1]['options'], (
        f"the scheme names changed with the service voltage: "
        f"{na['groups'][1]} vs {eu['groups'][1]}")
    assert '120 V line-to-neutral, 208 V line-to-line' in na['groups'][1]['label'], (
        f"the 208V service does not resolve to 120V line-to-neutral: {na}")
    assert '231 V line-to-neutral, 400 V line-to-line' in eu['groups'][1]['label'], (
        f"the 400V service does not resolve to its own line-to-neutral "
        f"figure: {eu}")
    for name in eu['groups'][1]['options']:
        assert '400' not in name and '231' not in name, (
            f"a service voltage leaked into a scheme name: {name}")


# ── the distro names the power, the way the processor names the ports ─────
#
# The three changes that are one feature (v0.12.x):
#
#   * A multi's NUMBER runs per distro, over the whole show, in layer-list
#     order bottom up - the same order the Data tab hands out card ports.
#     Numbering per screen was what let two screens both own an S1.
#   * A multi's NAME comes down a ladder, top wins: an explicit circuit
#     override, then a name typed onto the multi, then the distro's name plus
#     the multi's number under it (SL1, SL2), then the screen's template.
#   * A multi's IDENTITY is (layer, socaIndex) and nothing else. Everything
#     per-multi - length, tail positions, breaker offset, distro assignment,
#     name - is keyed by that index, because the number is now a thing that
#     CHANGES when a multi is assigned.


def test_multis_number_per_distro_in_layer_order_bottom_up(page):
    """Two screens, two distros. Numbering restarts per DISTRO, not per
    screen, and walks project layer order - which is the layer list read
    bottom up, and the same order the Data tab allocates card ports in.

    Reversing the layer order reverses the numbers, which is the proof that
    the order is the one being claimed and not an accident of the screens'
    ids or names."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        // A: one multi (3 circuits). B: two multis (8 circuits).
        const mk = () => ({
            A: ph.col5(11, 'A', 3, { powerSocaDistro: { 1: 'dl' } }),
            B: ph.col5(12, 'B', 8, { powerSocaDistro: { 1: 'dl', 2: 'dr' } }),
        });
        const distros = [ph.box('dl', 'SL'), ph.box('dr', 'SR')];
        const read = (layers) => ph.withProject({ layers, distros }, () =>
            layers.map(L => ph.planOf(L).map(s => s.name)));
        const up = mk(), down = mk();
        return {
            up: read([up.A, up.B]),
            down: read([down.B, down.A]),
        };
    }""")
    assert out['up'] == [['SL1'], ['SL2', 'SR1']], (
        "A is first in layer order so it takes SL1; B's first multi is the "
        f"second on SL and its second multi opens SR: {out['up']}")
    assert out['down'] == [['SL1', 'SR1'], ['SL2']], (
        f"reversing the layer order did not reverse the numbering: {out['down']}")


def test_unassigned_multis_are_numbered_too(page):
    """Nothing goes blank waiting for a distro: multis on no distro number
    themselves in their own bucket, over the whole show, in the same order -
    so two screens with no distros anywhere read S1 and S2, never S1 and
    S1."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const A = ph.col5(13, 'A', 3);
        const B = ph.col5(14, 'B', 3);
        return ph.withProject({ layers: [A, B] }, () => ({
            names: [ph.planOf(A), ph.planOf(B)].map(p => p.map(s => s.name)),
            labels: [ph.labelsOf(A), ph.labelsOf(B)],
        }));
    }""")
    assert out['names'] == [['S1'], ['S2']], (
        f"two screens both restarted at S1: {out['names']}")
    assert out['labels'] == [['S1-1', 'S1-2', 'S1-3'],
                             ['S2-1', 'S2-2', 'S2-3']]


def test_a_multi_keeps_its_length_tails_and_distro_when_its_number_changes(page):
    """The crux. B's multi is the second in the unassigned bucket (S2) and
    carries a home run, a balanced tail set and a hand name. Assigning A's
    multi to a distro takes A out of that bucket and renumbers B's multi to
    1 - and B's multi must come through with everything it owns, because it
    was never identified by its number in the first place."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const A = ph.col5(15, 'A', 3);
        const B = ph.col5(16, 'B', 5, {
            powerSocaLengths: { 1: '100ft' },
            powerSocaPhasePos: { 1: [1, 2, 3, 5, 6] },
            powerSocaDistro: { 1: 'dr' },
        });
        const distros = [ph.box('dl', 'SL'), ph.box('dr', 'SR')];
        return ph.withProject({ layers: [A, B], distros }, () => {
            const before = ph.planOf(B)[0];
            // A lands on SR too, ahead of B in layer order, so B's multi
            // stops being SR1 and becomes SR2.
            window.app.setSocaDistro(A, 1, 'dr');
            const after = ph.planOf(B)[0];
            return { before, after, labels: ph.labelsOf(B) };
        });
    }""")
    assert out['before']['name'] == 'SR1'
    assert out['after']['name'] == 'SR2', (
        f"B's multi did not renumber when A joined its distro: {out['after']}")
    assert out['after']['length'] == '100ft', 'the home run was orphaned'
    assert out['after']['legs'] == [1, 2, 3, 5, 6], 'the tail set was orphaned'
    assert out['after']['soca'] == out['before']['soca'] == 1, (
        'the stable index must not move when the number does')
    assert out['labels'] == ['SR2-1', 'SR2-2', 'SR2-3', 'SR2-5', 'SR2-6']


def test_an_old_keyed_project_migrates_losslessly(page):
    """A project saved when the per-multi stores were keyed by the number the
    screen's own template produced. On `S3-#` that screen's two multis were
    stored under 3 and 4; they are now 1 and 2, and everything under the old
    keys has to arrive under the new ones.

    Run twice on purpose: the stamp is the only thing stopping a second pass
    walking an S3-# screen's keys down past 1 and deleting them."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.col5(17, 'Old', 8, {
            powerLabelTemplate: 'S3-#',
            powerSocaLengths: { 3: '100ft', 4: '25ft' },
            powerSocaDistro: { 3: 'dl' },
            powerSocaPhasePos: { 4: [2, 5] },
            powerSocaPhaseOffset: { 3: 1 },
            powerSocaNames: { 4: 'HOUSE' },
        });
        const distros = [ph.box('dl', 'SL')];
        const snap = () => JSON.parse(JSON.stringify({
            lengths: S.powerSocaLengths, distro: S.powerSocaDistro,
            pos: S.powerSocaPhasePos, offset: S.powerSocaPhaseOffset,
            names: S.powerSocaNames, stamp: S.powerSocaKeying,
        }));
        const first = window.app.migrateSocaKeying(S);
        const once = snap();
        const second = window.app.migrateSocaKeying(S);
        return ph.withProject({ layers: [S], distros }, () => ({
            first, second, once, twice: snap(),
            plan: ph.planOf(S),
        }));
    }""")
    assert out['first'] is True and out['second'] is False, (
        'the rekey must run once and then never again')
    assert out['once'] == {
        'lengths': {'1': '100ft', '2': '25ft'},
        'distro': {'1': 'dl'},
        'pos': {'2': [2, 5]},
        'offset': {'1': 1},
        'names': {'2': 'HOUSE'},
        'stamp': 'index',
    }, f"the rekey lost or moved something: {out['once']}"
    assert out['twice'] == out['once'], 'the second pass moved the keys again'
    # and it is lossless where it counts - through the plan, not just the raw
    # dicts: multi 1 keeps its home run and lands on SL, multi 2 keeps the
    # name typed onto it and the tails it was balanced onto.
    assert [s['name'] for s in out['plan']] == ['SL1', 'HOUSE']
    assert [s['length'] for s in out['plan']] == ['100ft', '25ft']
    assert out['plan'][1]['legs'] == [2, 5]


def test_the_four_naming_levels_each_win_in_turn(page):
    """The ladder, from the bottom up. One multi, one circuit read four
    times, each rung added on top of the last and each one taking over."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.col5(18, 'Ladder', 3);
        const distros = [ph.box('dl', 'SL')];
        return ph.withProject({ layers: [S], distros }, () => {
            const seen = {};
            seen.template = ph.labelsOf(S);
            S.powerSocaDistro = { 1: 'dl' };
            seen.distro = ph.labelsOf(S);
            S.powerSocaNames = { 1: 'HOUSE' };
            seen.hand = ph.labelsOf(S);
            S.powerLabelOverrides = { 2: 'FOH RIG B' };
            seen.override = ph.labelsOf(S);
            return seen;
        });
    }""")
    assert out['template'] == ['S1-1', 'S1-2', 'S1-3'], \
        'no distro, no name: the screen template'
    assert out['distro'] == ['SL1-1', 'SL1-2', 'SL1-3'], \
        'the distro names its own load'
    assert out['hand'] == ['HOUSE-1', 'HOUSE-2', 'HOUSE-3'], \
        'a name typed onto the multi beats the distro'
    assert out['override'] == ['HOUSE-1', 'FOH RIG B', 'HOUSE-3'], \
        "the user's own text beats everything"


def test_renaming_a_distro_follows_the_multis_that_have_no_name_of_their_own(page):
    """Rename the box and every multi still following it is renamed. A multi
    somebody named by hand has stopped following and does not move."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const A = ph.col5(19, 'A', 3, { powerSocaDistro: { 1: 'dl' } });
        const B = ph.col5(20, 'B', 3, { powerSocaDistro: { 1: 'dl' },
                                        powerSocaNames: { 1: 'HOUSE' } });
        const distros = [ph.box('dl', 'SL')];
        return ph.withProject({ layers: [A, B], distros }, () => {
            const before = [ph.labelsOf(A)[0], ph.labelsOf(B)[0]];
            window.app.updateDistro('dl', { name: 'STAGE' });
            return { before, after: [ph.labelsOf(A)[0], ph.labelsOf(B)[0]] };
        });
    }""")
    assert out['before'] == ['SL1-1', 'HOUSE-1']
    assert out['after'] == ['STAGE1-1', 'HOUSE-1'], (
        f"renaming the distro did not reach the multi following it, or "
        f"reached the one that had stopped following: {out['after']}")


def test_explicit_overrides_are_byte_identical_through_every_rename(page):
    """A label the user typed is the user's text. Assigning the multi to a
    distro, renaming the distro and naming the multi by hand all rename the
    AUTO labels around it and never touch it."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.col5(21, 'Fixed', 3, {
            powerLabelOverrides: { 1: 'FOH A', 2: 'FOH B', 3: 'DIMMER 12' },
        });
        const distros = [ph.box('dl', 'SL')];
        return ph.withProject({ layers: [S], distros }, () => {
            const steps = [ph.labelsOf(S)];
            S.powerSocaDistro = { 1: 'dl' };
            steps.push(ph.labelsOf(S));
            window.app.updateDistro('dl', { name: 'STAGE LEFT' });
            steps.push(ph.labelsOf(S));
            S.powerSocaNames = { 1: 'HOUSE' };
            steps.push(ph.labelsOf(S));
            return steps;
        });
    }""")
    fixed = ['FOH A', 'FOH B', 'DIMMER 12']
    assert out == [fixed, fixed, fixed, fixed], (
        f"an override moved when something upstream was renamed: {out}")


def test_a_balanced_multi_under_a_named_distro_reads_true_tails(page):
    """The two rules meet. A five-circuit multi balanced onto tails
    {1,2,3,5,6}, on a distro named SL: the wall reads SL1-2, SL1-3, SL1-5 in
    the middle - the TRUE physical tails - and never a renumbered 1, 2, 3."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.col5(22, 'Bal', 5, {
            powerSocaDistro: { 1: 'dl' },
            powerSocaPhasePos: { 1: STORED_HERE },
        });
        const distros = [ph.box('dl', 'SL')];
        return ph.withProject({ layers: [S], distros }, () => ({
            labels: ph.labelsOf(S),
            tails: ph.planOf(S)[0].legs,
        }));
    }""".replace('STORED_HERE', str(STORED)))
    assert out['tails'] == DISPLAYED
    assert out['labels'] == ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-5', 'SL1-6'], (
        f"the distro name and the true tails did not survive together: "
        f"{out['labels']}")
    assert out['labels'][1:4] == ['SL1-2', 'SL1-3', 'SL1-5'], \
        'the middle three name their tails, not a renumbered 1, 2, 3'


def test_the_wall_the_sidebar_and_the_plan_all_read_the_same_names(page):
    """One authority, four surfaces. A wall on two distros named SL and SR:
    the canvas bubbles, the label editor's placeholders, the splitter rows
    and the soca plan's leg labels all print exactly the same strings."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const app = window.app, cr = window.canvasRenderer;
        const texts = [];
        const orig = CanvasRenderingContext2D.prototype.fillText;
        const savedLayer = app.currentLayer;
        try {
            CanvasRenderingContext2D.prototype.fillText = function (t, ...a) {
                texts.push(String(t));
                return orig.call(this, t, ...a);
            };
            const S = ph.col5(23, 'Wall', 8, {
                powerSocaDistro: { 1: 'dl', 2: 'dr' },
                powerSplitters: { enabled: true, maxWays: 2,
                                  manual: { merge: [], split: [] } },
            });
            const distros = [ph.box('dl', 'SL'), ph.box('dr', 'SR')];
            return ph.withProject({ layers: [S], distros }, () => {
                app.currentLayer = S;
                S._powerCircuitsRequired = app.screenCircuitCount(S);
                app.refreshSplitterPanel();
                app.updatePowerLabelEditor();
                cr.renderPowerArrows(S);
                const txt = e => e.textContent.replace(/\\s+/g, ' ').trim();
                return {
                    authority: ph.labelsOf(S),
                    planLegs: app.getSocaPlan(S).flatMap(
                        s => s.legs.map(l => l.label)),
                    canvas: texts.splice(0),
                    editor: [...document.querySelectorAll(
                        '#power-label-list input[type=text]')]
                        .map(i => i.placeholder),
                    splitterRows: [...document.querySelectorAll(
                            '#power-splitters .splitter-circuit-row label')]
                        .map(l => txt(l).split(' \\u00b7 ')[0]),
                    socaRows: [...document.querySelectorAll(
                            '#power-soca-runs label')]
                        .map(txt).filter(t => t && / legs? /.test(t)),
                };
            });
        } finally {
            CanvasRenderingContext2D.prototype.fillText = orig;
            app.currentLayer = savedLayer;
        }
    }""")
    expected = ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-5', 'SL1-6',
                'SR1-1', 'SR1-2']
    assert out['authority'] == expected, (
        f"two multis on two named distros: {out['authority']}")
    assert out['planLegs'] == expected, 'the soca plan disagrees with the wall'
    assert [t for t in out['canvas'] if t in expected] == expected, (
        f"the canvas bubbles do not read the authority: {out['canvas']}")
    assert out['editor'] == expected, 'the label editor disagrees with the wall'
    assert out['splitterRows'] == expected, \
        'the splitter rows disagree with the wall'


def test_a_multi_that_moves_distro_takes_the_new_distros_name(page):
    """The assignment select is a naming control as much as a load one: move
    the multi and its circuits are renamed by the box they now hang off."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const S = ph.col5(24, 'Move', 3, { powerSocaDistro: { 1: 'dl' } });
        const distros = [ph.box('dl', 'SL'), ph.box('dr', 'SR')];
        return ph.withProject({ layers: [S], distros }, () => {
            const saved = window.app.updateLayers;
            window.app.updateLayers = () => {};
            try {
                const before = ph.labelsOf(S);
                window.app.setSocaDistro(S, 1, 'dr');
                return { before, after: ph.labelsOf(S) };
            } finally { window.app.updateLayers = saved; }
        });
    }""")
    assert out['before'] == ['SL1-1', 'SL1-2', 'SL1-3']
    assert out['after'] == ['SR1-1', 'SR1-2', 'SR1-3']
