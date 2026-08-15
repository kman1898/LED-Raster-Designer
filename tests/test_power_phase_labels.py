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
        return { id: 'd1', name: 'D1', ratingA: 400, voltage: 208, phase: 3 };
    },
    withProject(project, fn) {
        const saved = window.app.project;
        window.app.project = Object.assign(
            { layers: [], groups: [], canvases: [], rack: [] }, project);
        try { return fn(); } finally { window.app.project = saved; }
    },
    labelsOf(S) {
        return window.app.screenCircuits(S).map(c =>
            window.app.getPowerCircuitLabel(S, c.num));
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


def test_unbalanced_screen_labels_are_byte_identical_to_today(page):
    """No phase positions stored: the auto labels keep the sequential
    arithmetic - including the custom-drawn merge shape with GAPS in the
    numbering (1,3,5,7,9), where the drawn number is user intent and today's
    labels wrap the raw number (S2-1 for circuit 7)."""
    out = page.evaluate("""() => {
        const ph = window.__ph;
        const plain = ph.five();
        const gapped = ph.srlike();
        return {
            plain: ph.withProject({ layers: [plain] }, () => ph.labelsOf(plain)),
            gapped: ph.withProject({ layers: [gapped] }, () => ph.labelsOf(gapped)),
        };
    }""")
    assert out['plain'] == ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5']
    assert out['gapped'] == ['S1-1', 'S1-3', 'S1-5', 'S2-1', 'S2-3'], \
        'unbalanced custom numbering must not move'


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
                socaRows: [...document.querySelectorAll('#power-soca-runs .info-row label')]
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
    assert out['moveLabels'] == [['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5']], \
        "moves carry the circuits' pre-move authority labels"
    # natural [1..5] -> best [1,2,3,5,6]: circuits 4 and 5 move, and the
    # dialog names them S1-4 and S1-5 - their labels on the canvas today
    assert 'S1-4 (' in out['body'] and 'S1-5 (' in out['body']
    assert 'tail 4 \u2192' in out['body']
    assert not out['ordinal'], 'no "circuit N" ordinals anywhere in the dialog'
    assert out['modalGone']
    assert out['splitterAfter'] == ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6'], \
        'Apply repaints the splitter rows with the new tails, no round-trip'
    assert out['editorAfter'] == ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6'], \
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
    assert out['labels'] == ['S1-1', 'S1-2', 'S1-3', 'S1-5', 'S1-6']
    assert out['labels'] == sorted(out['labels'])
