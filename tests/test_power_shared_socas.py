"""One physical soca serving two screens, declared by pinning a multi number.

The reference show (2026 NCMF) does this entirely by hand today: ON SL STRIP
and CEN SL STRIP both carry a multi named C2-3 - one box across two screens -
and the second screen's circuits are labelled onto tails 4-6 purely through
typed powerLabelOverrides (C2-3-4, C2-3-5, C2-3-6). The costs of that
workaround are exactly what this feature removes: the rollup counted each
partial multi as its own soca (phantom multis at the distro), Balance could
not see the real tails, and every label was typed by hand.

The model under test:

  - A multi assigned to a distro can PIN its number (powerSocaNumber,
    keyed by the stable socaIndex like every per-multi store). Auto numbers
    exactly as always - per distro, layer order - dealing AROUND pins.
  - Two multis pinned to the same (distro, number) ARE one physical soca.
    The tuple is the join key; there is no separate link to manage.
  - A stored tail set (balance, hand move, a join stamping incumbents) is
    LAW: it claims exactly its tails in any box, before any dealing, and
    is never rearranged. An unstored member lands on the box's remaining
    free tails; layer order decides only among unstored members. Two
    STORED sets on one tail is a CLASH, said out loud (the clashing
    circuit chips, the multi section's hw-dock-multi-clash, the dock's
    issue strip) the way port assignment reports an occupied socket.
    Joining an occupied box stamps the incumbents' rendered tails into
    their own stores first - what was showing becomes held - so a joiner
    never renumbers a wall someone may have already cabled.
    More than six legs on one box is an overflow clash: a soca has six
    tails, and the extras number 7, 8, ... so the wrongness is visible.
  - Labels flow through the ONE authority: <box name>-<true tail>, so the
    second screen derives the exact strings the user used to type.
  - The rollup books one feeds row per box (watts summed, legs combined,
    both screens named); the balancer moves the box as one multi.
  - Separation is re-picking: another number, Auto, or another distro.
  - No pins = byte-identical numbering, tails and labels to before.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_power_shared_socas.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# The strings the user hand-typed into the NCMF file's powerLabelOverrides
# for CEN SL STRIP - the acceptance bar is deriving these character for
# character, with nothing typed.
NCMF_TYPED_OVERRIDES = ['C2-3-4', 'C2-3-5', 'C2-3-6']


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    # The hardware dock is the one power UI surface now (the Power sidebar
    # is gone) and it only renders in the power view - open it once for the
    # tests that read the multi headers, chips and issue strip.
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg
    context.close()


# Same builder shape as test_power_phase_labels.py: 100V x 5A / 100W = a
# 5-tile circuit, tl-v organized, 5 rows - so `columns` IS the circuit
# count. ncmf() builds the reference pair: two 3-circuit screens pinned to
# multi 3 of a distro named C2 - the ON SL STRIP + CEN SL STRIP shape.
HELPERS_JS = """
window.__sh = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            columns: 3, rows: 5,
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
    distro(name) {
        return { id: 'd1', name: name || 'C2', ratingA: 400, voltage: 208, phase: 3 };
    },
    ncmf() {
        const A = this.screen({ id: 1, name: 'ON SL STRIP',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 3 } });
        const B = this.screen({ id: 2, name: 'CEN SL STRIP', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 3 } });
        return { A, B, project: { layers: [A, B], distros: [this.distro()] } };
    },
    // The reference show's C1 distro, shapes only: a 3-circuit strip split
    // after its 1st circuit sits ABOVE two 4-circuit walls in layer order,
    // part A pinned onto OFF SR US's box (No. 2), part B onto CEN SR US's
    // (No. 3). `o.strip/o.off/o.cen` override per screen - the tests vary
    // the stores and the pins, never the wall.
    c1(o) {
        o = o || {};
        const STRIP = this.screen(Object.assign({ id: 61,
            name: 'ON SR STRIP', columns: 3, powerSocaSplits: [1],
            powerSocaDistro: { 1: 'd1', 2: 'd1' },
            powerSocaNumber: { 1: 2, 2: 3 } }, o.strip || {}));
        const OFF = this.screen(Object.assign({ id: 62, name: 'OFF SR US',
            columns: 4, offset_x: 1000,
            powerSocaDistro: { 1: 'd1' },
            powerSocaNumber: { 1: 2 } }, o.off || {}));
        const CEN = this.screen(Object.assign({ id: 63, name: 'CEN SR US',
            columns: 4, offset_x: 2000,
            powerSocaDistro: { 1: 'd1' },
            powerSocaNumber: { 1: 3 } }, o.cen || {}));
        return { STRIP, OFF, CEN,
                 project: { layers: [STRIP, OFF, CEN],
                            distros: [this.distro('C1')] } };
    },
    withProject(project, fn) {
        const saved = window.app.project;
        window.app.project = Object.assign(
            { layers: [], groups: [], canvases: [], rack: [] }, project);
        try { return fn(); } finally { window.app.project = saved; }
    },
    labelsOf(S) {
        window.app._circuitTailCache = null;
        return window.app.screenCircuits(S).map(c =>
            window.app.getPowerCircuitLabel(S, c.num));
    },
    planOf(S) {
        window.app._circuitTailCache = null;
        return window.app.getSocaPlan(S).map(s => ({
            soca: s.soca, number: s.number, name: s.name,
            legs: s.legs.map(l => l.leg),
        }));
    },
    shareOf(S, idx) {
        window.app._circuitTailCache = null;
        return window.app.getSocaShare(S, idx);
    },
};
"""


# ── 1. the NCMF acceptance shape ──────────────────────────────────────────

def test_ncmf_shared_box_labels_match_the_hand_typed_overrides(page):
    """ON SL STRIP + CEN SL STRIP, both pinned to multi 3 of distro C2:
    one box named C2-3, the first screen on tails 1-3, the second on the
    box's next free tails 4-6 - and the second screen's labels derive the
    EXACT strings the user hand-typed into the NCMF file, character for
    character, with nothing typed."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { A, B, project } = sh.ncmf();
        return sh.withProject(project, () => ({
            a: sh.labelsOf(A), b: sh.labelsOf(B),
            planA: sh.planOf(A), planB: sh.planOf(B),
            share: sh.shareOf(B, 1),
        }));
    }""")
    assert out['a'] == ['C2-3-1', 'C2-3-2', 'C2-3-3']
    assert out['b'] == NCMF_TYPED_OVERRIDES, \
        'the derived labels must equal the strings the user used to type'
    # one box: same name, same number, tails split 1-3 / 4-6
    assert out['planA'] == [{'soca': 1, 'number': 3, 'name': 'C2-3', 'legs': [1, 2, 3]}]
    assert out['planB'] == [{'soca': 1, 'number': 3, 'name': 'C2-3', 'legs': [4, 5, 6]}]
    share = out['share']
    assert share and not share['clash'] and not share['overflow']
    assert [m['layerName'] for m in share['members']] == ['ON SL STRIP', 'CEN SL STRIP']
    assert [m['tails'] for m in share['members']] == [[1, 2, 3], [4, 5, 6]]


def test_rollup_counts_one_soca_with_combined_legs(page):
    """The distro rollup books ONE feeds row for the shared box - both
    screens named, legs combined, watts summed - never the two phantom
    multis the hand-override workflow produced. The bucket's total watts
    still carry both screens' load."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { project } = sh.ncmf();
        return sh.withProject(project, () => {
            window.app._circuitTailCache = null;
            const d1 = window.app.getDistroLoads().find(b => b.id === 'd1');
            return { socas: d1.socas, watts: d1.watts, amps: d1.amps };
        });
    }""")
    assert len(out['socas']) == 1, 'one physical box = one feeds row'
    row = out['socas'][0]
    assert row['name'] == 'C2-3'
    assert row['layer'] == 'ON SL STRIP + CEN SL STRIP'
    assert row['legs'] == 6
    # 15 panels x 100 W per screen, both screens on the box
    assert row['watts'] == 3000
    assert out['watts'] == 3000
    assert abs(out['amps'] - 3000 / (208 * 1.73)) < 0.01


# ── 2. numbering: auto deals around pins ──────────────────────────────────

def test_auto_numbering_deals_around_pins(page):
    """A pin owns its number outright, wherever the pinned screen sits in
    layer order: with S1 pinned to 2, the autos number 1 and 3 - never a
    silent collision, never a renumbered pin."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const P = sh.screen({ id: 1, name: 'Pinned',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 } });
        const A = sh.screen({ id: 2, name: 'AutoA', offset_x: 600,
            powerSocaDistro: { 1: 'd1' } });
        const B = sh.screen({ id: 3, name: 'AutoB', offset_x: 1200,
            powerSocaDistro: { 1: 'd1' } });
        return sh.withProject(
            { layers: [P, A, B], distros: [sh.distro()] },
            () => ({ p: sh.planOf(P), a: sh.planOf(A), b: sh.planOf(B) }));
    }""")
    assert out['p'][0]['number'] == 2
    assert out['a'][0]['number'] == 1
    assert out['b'][0]['number'] == 3
    assert out['p'][0]['name'] == 'C2-2'
    assert out['a'][0]['name'] == 'C2-1'
    assert out['b'][0]['name'] == 'C2-3'


# ── 3. clashes: stored tails are never rearranged; six tails is physics ───

def test_stored_tail_collision_reports_a_clash_verbatim(page):
    """TWO stored tail sets landing on the same tails is a clash: both keep
    their tails (the duplicate labels stay visible), and the share record
    says which tails are claimed twice - nothing is silently rearranged."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A = sh.screen({ id: 1, name: 'First',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaPhasePos: { 1: [1, 2, 3] } });
        const B = sh.screen({ id: 2, name: 'Second', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaPhasePos: { 1: [1, 2, 3] } });
        return sh.withProject(
            { layers: [A, B], distros: [sh.distro()] },
            () => ({ a: sh.labelsOf(A), b: sh.labelsOf(B),
                     share: sh.shareOf(A, 1) }));
    }""")
    assert out['a'] == ['C2-1-1', 'C2-1-2', 'C2-1-3']
    assert out['b'] == ['C2-1-1', 'C2-1-2', 'C2-1-3'], \
        'stored tails print verbatim - the duplicate IS the report'
    share = out['share']
    assert share['clash'] and not share['overflow']
    assert share['members'][1]['clashTails'] == [1, 2, 3]


def test_unstored_member_deals_around_a_stored_set(page):
    """A stored tail set is LAW wherever its member sits in layer order: the
    EARLIER, unstored member deals into the tails the stored set leaves
    free instead of sitting down on them - no clash, nothing rearranged."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A = sh.screen({ id: 1, name: 'First',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const B = sh.screen({ id: 2, name: 'Second', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaPhasePos: { 1: [1, 2, 3] } });
        return sh.withProject(
            { layers: [A, B], distros: [sh.distro()] },
            () => ({ a: sh.labelsOf(A), b: sh.labelsOf(B),
                     share: sh.shareOf(A, 1) }));
    }""")
    assert out['b'] == ['C2-1-1', 'C2-1-2', 'C2-1-3'], \
        'the stored set renders on exactly its tails'
    assert out['a'] == ['C2-1-4', 'C2-1-5', 'C2-1-6'], \
        'the unstored member takes the free tails, layer order or not'
    share = out['share']
    assert not share['clash'] and not share['overflow']
    assert [m['tails'] for m in share['members']] == [[4, 5, 6], [1, 2, 3]]


def test_more_than_six_legs_reports_overflow(page):
    """4 + 3 circuits on one box is seven legs on a six-tail fan: the
    seventh circuit numbers tail 7 (the wrongness stays visible) and the
    share record flags the overflow."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A = sh.screen({ id: 1, name: 'Four', columns: 4,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const B = sh.screen({ id: 2, name: 'Three', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        return sh.withProject(
            { layers: [A, B], distros: [sh.distro()] },
            () => ({ b: sh.labelsOf(B), share: sh.shareOf(B, 1) }));
    }""")
    assert out['b'] == ['C2-1-5', 'C2-1-6', 'C2-1-7'], \
        'the extra circuit numbers past the fan - never wrapped or hidden'
    assert out['share']['overflow']
    assert out['share']['members'][1]['overTails'] == [7]


# ── 4. separation is re-picking ───────────────────────────────────────────

def test_dropping_the_pin_restores_standalone_numbering(page):
    """Back to Auto on the second screen: it leaves the box, takes the next
    free auto number (1 - the pin on 3 is dealt around), and its labels
    return to its own multi. The remaining pin keeps its number and is no
    longer shared."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { A, B, project } = sh.ncmf();
        return sh.withProject(project, () => {
            delete B.powerSocaNumber[1];
            return { a: sh.labelsOf(A), b: sh.labelsOf(B),
                     shareA: sh.shareOf(A, 1), shareB: sh.shareOf(B, 1) };
        });
    }""")
    assert out['a'] == ['C2-3-1', 'C2-3-2', 'C2-3-3']
    assert out['b'] == ['C2-1-1', 'C2-1-2', 'C2-1-3']
    assert out['shareA'] is None and out['shareB'] is None


def test_set_soca_number_is_one_named_undoable_write(page):
    """setSocaNumber writes the pin (and clears it on Auto) through the same
    updateLayers(save, action) convention every power edit uses, so one
    Ctrl+Z covers it."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const S = sh.screen({ id: 1, name: 'S', powerSocaDistro: { 1: 'd1' } });
        return sh.withProject({ layers: [S], distros: [sh.distro()] }, () => {
            const calls = [];
            const orig = app.updateLayers;
            app.updateLayers = (layers, save, action) =>
                calls.push({ n: layers.length, save, action });
            try {
                app.setSocaNumber(S, 1, '3');
                const pinned = { ...(S.powerSocaNumber || {}) };
                app.setSocaNumber(S, 1, null);
                const cleared = { ...(S.powerSocaNumber || {}) };
                return { calls, pinned, cleared };
            } finally {
                app.updateLayers = orig;
            }
        });
    }""")
    assert out['pinned'] == {'1': 3}
    assert out['cleared'] == {}
    assert out['calls'] == [
        {'n': 1, 'save': True, 'action': 'Set Multi Number'},
        {'n': 1, 'save': True, 'action': 'Set Multi Number'},
    ]


# ── 5. the name follows the distro; a typed name still wins its member ────

def test_distro_rename_propagates_to_every_member(page):
    """The box is named off (distro, number), so renaming the distro renames
    both screens' labels at once - the propagation the user did by
    re-typing six overrides."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { A, B, project } = sh.ncmf();
        return sh.withProject(project, () => {
            project.distros[0].name = 'K9';
            return { a: sh.labelsOf(A), b: sh.labelsOf(B) };
        });
    }""")
    assert out['a'] == ['K9-3-1', 'K9-3-2', 'K9-3-3']
    assert out['b'] == ['K9-3-4', 'K9-3-5', 'K9-3-6']


def test_hand_name_stays_per_member(page):
    """A hand-typed multi name is that member's text (top of the ladder,
    never reformatted); the unnamed member keeps deriving from the distro.
    The tails still split as one box either way."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { A, B, project } = sh.ncmf();
        A.powerSocaNames = { 1: 'FOH RIG' };
        return sh.withProject(project, () => ({
            a: sh.labelsOf(A), b: sh.labelsOf(B),
        }));
    }""")
    assert out['a'] == ['FOH RIG-1', 'FOH RIG-2', 'FOH RIG-3']
    assert out['b'] == NCMF_TYPED_OVERRIDES


# ── 6. balance treats the box as one multi ────────────────────────────────

def test_balancer_targets_the_box_once_and_excludes_a_full_box(page):
    """A 2+2 box is ONE balance target - combined tail set, both members,
    four legs - and the full 3+3 box is excluded exactly as a full single
    multi is: with all six tails in use there is nothing to choose."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A2 = sh.screen({ id: 1, name: 'A2', columns: 2,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const B2 = sh.screen({ id: 2, name: 'B2', columns: 2, offset_x: 600,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const half = sh.withProject(
            { layers: [A2, B2], distros: [sh.distro()] },
            () => {
                window.app._circuitTailCache = null;
                return window.app._balanceTargets().map(t => ({
                    legs: t.legs, positions: t.positions,
                    members: (t.members || []).map(m => m.layer.name),
                    layerName: t.layerName,
                }));
            });
        const { project } = sh.ncmf();
        const full = sh.withProject(project, () => {
            window.app._circuitTailCache = null;
            return window.app._balanceTargets().length;
        });
        return { half, full };
    }""")
    assert out['half'] == [{
        'legs': 4, 'positions': [1, 2, 3, 4],
        'members': ['A2', 'B2'], 'layerName': 'A2 + B2',
    }], 'one target for the whole box, never one per member'
    assert out['full'] == 0, 'a full box balances itself - nothing to move'


def test_applying_a_box_move_deals_tails_across_both_screens(page):
    """Applying a box move re-deals the chosen tail SET in member order -
    ascending tails to the earlier screen, each member's slice ascending -
    and the labels on both screens follow the one authority."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const A = sh.screen({ id: 1, name: 'A2', columns: 2,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const B = sh.screen({ id: 2, name: 'B2', columns: 2, offset_x: 600,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        return sh.withProject({ layers: [A, B], distros: [sh.distro()] }, () => {
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            try {
                app.applyPhaseBalance([{
                    layerId: 1, soca: 1, name: 'C2-1',
                    members: [{ layerId: 1, soca: 1, legs: 2 },
                              { layerId: 2, soca: 1, legs: 2 }],
                    from: [1, 2, 3, 4], to: [1, 2, 4, 6],
                }]);
            } finally {
                app.updateLayers = orig;
            }
            return {
                storeA: A.powerSocaPhasePos[1], storeB: B.powerSocaPhasePos[1],
                a: sh.labelsOf(A), b: sh.labelsOf(B),
            };
        });
    }""")
    assert out['storeA'] == [1, 2]
    assert out['storeB'] == [4, 6]
    assert out['a'] == ['C2-1-1', 'C2-1-2']
    assert out['b'] == ['C2-1-4', 'C2-1-6']


# ── 7. no pins = byte-identical to before ─────────────────────────────────

def test_no_pins_keeps_todays_numbering_and_labels(page):
    """A project with no pinned numbers numbers and labels exactly as it
    always has: per-distro sequence in layer order, natural tails, template
    labels off a distro. (The capture that guards the migration.)"""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A = sh.screen({ id: 1, name: 'A', powerSocaDistro: { 1: 'd1' } });
        const B = sh.screen({ id: 2, name: 'B', offset_x: 600,
            powerSocaDistro: { 1: 'd1' } });
        const U = sh.screen({ id: 3, name: 'U', offset_x: 1200 });
        return sh.withProject(
            { layers: [A, B, U], distros: [sh.distro('D')] },
            () => ({ a: sh.labelsOf(A), b: sh.labelsOf(B), u: sh.labelsOf(U),
                     planA: sh.planOf(A), planB: sh.planOf(B) }));
    }""")
    assert out['a'] == ['D1-1', 'D1-2', 'D1-3']
    assert out['b'] == ['D2-1', 'D2-2', 'D2-3']
    assert out['u'] == ['S1-1', 'S1-2', 'S1-3'], \
        'an unassigned screen keeps its template labels byte-identical'
    assert out['planA'][0]['number'] == 1
    assert out['planB'][0]['number'] == 2


# ── 8. the dock says one box, and the strip says what is wrong ────────────
#
# The soca tiles died with the Power sidebar; the shared box's facts moved
# onto the hardware dock. One multi SECTION per box, and (ruling 2026-08-30,
# user screenshot of "SR1 [100ft] SR1 [100ft] SR1 [100ft]") ONE name field
# and ONE home-run length field regardless of member count - a multi shared
# by N screens is ONE physical box with ONE home run. The fields anchor on
# the FIRST member's keys (power-soca-name-<layerId>-<socaIdx>) and write
# through to every member; the other members' field keys no longer exist in
# the DOM. The detail reads "<legs> circuits · <amps> A" and the glance
# "<used>/6". The six circuit chips name holder and label per tail, and
# clashes go red on the chips, on the section (hw-dock-multi-clash) and as
# rows on the issue strip (#hw-dock-issues).

SHOW_BOX_JS = """(cfg) => {
    const sh = window.__sh;
    const app = window.app;
    const { A, B, project } = sh.ncmf();
    // a clash needs TWO stored sets on one tail - a lone stored set is law
    // and the unstored member simply deals around it
    if (cfg && cfg.clash) {
        A.powerSocaPhasePos = { 1: [1, 2, 3] };
        B.powerSocaPhasePos = { 1: [1, 2, 3] };
    }
    return sh.withProject(project, () => {
        const savedLayer = app.currentLayer;
        try {
            app.currentLayer = B;
            app._circuitTailCache = null;
            app.renderHardwareDock();
            const txt = el => el
                ? el.textContent.replace(/\\s+/g, ' ').trim() : null;
            const nameA = document.querySelector(
                '[data-lrd-field="power-soca-name-1-1"]');
            const nameB = document.querySelector(
                '[data-lrd-field="power-soca-name-2-1"]');
            const head = nameA && nameA.closest('.hw-dock-head-row');
            const sec = nameA && nameA.closest('.hw-dock-multi');
            const chips = sec ? [...sec.querySelectorAll('.lrd-tile')]
                .map(t => {
                    const lines = t.querySelectorAll('.lrd-tile-line');
                    return {
                        line: txt(lines[0]), who: txt(lines[1]),
                        clash: t.classList.contains('lrd-tile-clash'),
                        box: t.dataset.lrdTileBox || null,
                    };
                }) : null;
            return {
                oneField: !!(nameA && !nameB),
                placeholder: nameA && nameA.placeholder,
                staticLabel: !!(head
                    && head.querySelector('.hw-dock-unit-name')),
                detail: sec
                    ? txt(sec.querySelector('.hw-dock-unit-info')) : null,
                glance: sec
                    ? txt(sec.querySelector('.hw-dock-unit-use')) : null,
                clashClass: !!(sec
                    && sec.classList.contains('hw-dock-multi-clash')),
                chips,
                strip: [...document.querySelectorAll(
                    '#hw-dock-issues .hw-dock-issue')].map(r => ({
                        text: txt(r),
                        mild: r.classList.contains('hw-dock-issue-mild'),
                    })),
                retiredPanel: !!document.getElementById('power-soca-runs'),
            };
        } finally {
            app.currentLayer = savedLayer;
        }
    });
}"""


def test_dock_multi_reads_one_box_not_two_multis(page):
    """The shared box is ONE multi section on the dock with ONE name field
    (ruling 2026-08-30: one physical box, one home run - N identical
    member pairs were N-1 too many), keyed by the FIRST member and
    wearing the derived shared name as placeholder; the second member's
    field key exists nowhere. The detail and glance carry the combined
    figures, and the chips name each member on exactly its tails. The
    slot is stated by the chips' own box key (multi-<distro>-<n>) - the
    old Distro/No. selects and their panel are gone: picking a slot is
    the dock's drag."""
    out = page.evaluate(SHOW_BOX_JS, {})
    assert not out['retiredPanel'], \
        'the retired Power sidebar soca panel is back'
    assert out['oneField'], (
        f'the shared box must carry exactly ONE name field, anchored on '
        f'the first member\'s key: {out}')
    assert out['placeholder'] == 'C2-3', \
        'the one field reads as the shared derived name'
    assert not out['staticLabel'], \
        'an occupied box wears its members, not a static slot label'
    assert out['detail'] == '6 circuits · 30.0 A', out
    assert out['glance'] == '6/6', out
    assert not out['clashClass']
    assert [c['box'] for c in out['chips']] == ['multi-d1-3'] * 6, (
        f'every chip states the slot it belongs to: {out["chips"]}')
    assert [c['line'] for c in out['chips']] == [
        '1 C2-3-1', '2 C2-3-2', '3 C2-3-3',
        '4 C2-3-4', '5 C2-3-5', '6 C2-3-6'], out['chips']
    assert [c['who'] for c in out['chips']] == (
        ['ON SL STRIP'] * 3 + ['CEN SL STRIP'] * 3), out['chips']
    assert not any(c['clash'] for c in out['chips'])
    assert out['strip'] == [], (
        f'a healthy box raises no strip question: {out["strip"]}')


def test_dock_wears_the_clash(page):
    """A tail collision wears the same clash dress a double-booked port
    chip wears: lrd-tile-clash on the claimed chips (their face saying
    'clash' and both labels), hw-dock-multi-clash on the box's section,
    and one red strip row per tail naming both claimants."""
    out = page.evaluate(SHOW_BOX_JS, {"clash": True})
    assert out['clashClass'], 'the section must wear hw-dock-multi-clash'
    chips = out['chips']
    assert [c['clash'] for c in chips] == [True] * 3 + [False] * 3, chips
    assert [c['who'] for c in chips[:3]] == ['clash'] * 3, chips
    assert [c['line'] for c in chips[:3]] == [
        '1 C2-3-1 / C2-3-1', '2 C2-3-2 / C2-3-2', '3 C2-3-3 / C2-3-3'], \
        'a clashing chip prints BOTH claims - the duplicate IS the report'
    reds = [r for r in out['strip'] if 'claimed twice' in r['text']]
    assert len(reds) == 3, f'one strip row per claimed tail: {out["strip"]}'
    assert all(not r['mild'] for r in reds), 'a clash is a red question'
    for t, r in zip((1, 2, 3), reds):
        assert f'C2 3 circuit {t} is claimed twice' in r['text'], r
        assert f'ON SL STRIP C2-3-{t}' in r['text'] \
            and f'CEN SL STRIP C2-3-{t}' in r['text'], r


# ── 9. persistence + undo, against the real server ────────────────────────

def test_pin_round_trips_and_undoes_on_the_real_server(page):
    """The pin is a layer field with the three-lists discipline: a real
    setSocaNumber survives the PUT echo (client re-stamp), lands in the
    server's copy of the layer (allow-list), and one undo removes it."""
    out = page.evaluate("""async () => {
        const app = window.app;
        // a real screen + a real distro on the shared server project
        const resp = await fetch('/api/layer/add', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'SharedSocaRT', columns: 3, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: 2600, offset_y: 0 }),
        });
        const made = await resp.json();
        app.project = await (await fetch('/api/project')).json();
        const L = app.project.layers.find(l => l.id === made.id);
        L.powerVoltage = '100'; L.powerAmperage = '5'; L.panelWatts = '100';
        L.powerOrganized = true; L.powerMaximize = false;
        L.powerFlowPattern = 'tl-v';
        app.currentLayer = L;
        if (!app.project.distros) app.project.distros = [];
        app.project.distros.push({ id: 'd77', name: 'RT', ratingA: 400,
                                   voltage: 208, phase: 3 });
        app._circuitTailCache = null;
        app.setSocaDistro(L, 1, 'd77');
        await new Promise(r => setTimeout(r, 400));
        app.setSocaNumber(L, 1, '4');
        await new Promise(r => setTimeout(r, 600));
        const clientAfterSet = { ...(L.powerSocaNumber || {}) };
        const server = await (await fetch('/api/project')).json();
        const serverLayer = server.layers.find(l => l.id === made.id);
        const serverPin = { ...(serverLayer.powerSocaNumber || {}) };
        await app.undo();
        await new Promise(r => setTimeout(r, 600));
        const live = app.project.layers.find(l => l.id === made.id);
        const clientAfterUndo = { ...((live && live.powerSocaNumber) || {}) };
        // clean up what this test added
        await fetch('/api/layer/' + made.id, { method: 'DELETE' });
        return { clientAfterSet, serverPin, clientAfterUndo };
    }""")
    assert out['clientAfterSet'] == {'1': 4}
    assert out['serverPin'] == {'1': 4}, \
        'the pin must survive the PUT allow-list and the echo re-stamp'
    assert out['clientAfterUndo'] == {}, 'one undo removes the pin'


def test_one_field_writes_through_every_member_and_one_undo_walks_back(page):
    """Ruling 2026-08-30 (user screenshot of "SR1 [100ft] SR1 [100ft]
    SR1 [100ft]"): a shared box is ONE physical box with ONE home run, so
    its header carries ONE name field and ONE length field, anchored on
    the FIRST member's keys. The field shows the first member's stored
    value even when legacy per-member values disagree, and a commit
    writes through to EVERY member - one history entry, one PUT batch -
    so the first edit converges the disagreement and one undo walks all
    members back."""
    out = page.evaluate("""async () => {
        const app = window.app;
        const mk = (name, ox) => fetch('/api/layer/add', { method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, columns: 3, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: ox, offset_y: 0 }) }).then(r => r.json());
        const a = await mk('ShareOneA', 3000);
        const b = await mk('ShareOneB', 3700);
        app.project = await (await fetch('/api/project')).json();
        const A = app.project.layers.find(l => l.id === a.id);
        const B = app.project.layers.find(l => l.id === b.id);
        for (const L of [A, B]) {
            L.powerVoltage = '100'; L.powerAmperage = '5';
            L.panelWatts = '100'; L.powerOrganized = true;
            L.powerMaximize = false; L.powerFlowPattern = 'tl-v';
        }
        if (!app.project.distros) app.project.distros = [];
        app.project.distros.push({ id: 'd78', name: 'WT', ratingA: 400,
                                   voltage: 208, phase: 3 });
        // one box - both pinned to (d78, 1) - with DISAGREEING legacy
        // per-member values, the state the old two-field header could
        // leave behind
        A.powerSocaDistro = { 1: 'd78' }; A.powerSocaNumber = { 1: 1 };
        B.powerSocaDistro = { 1: 'd78' }; B.powerSocaNumber = { 1: 1 };
        A.powerSocaNames = { 1: 'FIRST' };
        B.powerSocaNames = { 1: 'SECOND' };
        A.powerSocaLengths = { 1: '50ft' };
        B.powerSocaLengths = { 1: '75ft' };
        app._circuitTailCache = null;
        app.renderHardwareDock();
        // Baseline the hand-stamped seed state: undo restores the PREVIOUS
        // history entry, and the direct mutations above never snapshotted.
        app.saveState('Seed Shared Box');
        const q = (k) => document.querySelector(
            `[data-lrd-field="${k}"]`);
        const nameField = q(`power-soca-name-${a.id}-1`);
        const lenField = q(`power-soca-length-${a.id}-1`);
        const shown = {
            name: nameField && nameField.value,
            len: lenField && lenField.value,
            secondMemberField: !!q(`power-soca-name-${b.id}-1`)
                || !!q(`power-soca-length-${b.id}-1`),
        };
        const h0 = app.history.length;
        nameField.value = 'HOUSE';
        nameField.dispatchEvent(new Event('change'));
        await new Promise(r => setTimeout(r, 800));
        const entries = app.history.slice(h0).map(e => e.action);
        const client = [A, B].map(L => (L.powerSocaNames || {})['1']
                                        || (L.powerSocaNames || {})[1]);
        const server = await (await fetch('/api/project')).json();
        const sVals = [a.id, b.id].map(id => {
            const l = server.layers.find(x => x.id === id) || {};
            return (l.powerSocaNames || {})['1'];
        });
        await app.undo();
        await new Promise(r => setTimeout(r, 800));
        const walked = [a.id, b.id].map(id => {
            const l = app.project.layers.find(x => x.id === id);
            return ((l && l.powerSocaNames) || {})['1']
                || ((l && l.powerSocaNames) || {})[1];
        });
        await fetch('/api/layer/' + a.id, { method: 'DELETE' });
        await fetch('/api/layer/' + b.id, { method: 'DELETE' });
        return { shown, entries, client, sVals, walked };
    }""")
    assert not out['shown']['secondMemberField'], (
        f'the second member grew its own field - one box, one pair: {out}')
    assert out['shown'] == {'name': 'FIRST', 'len': '50ft',
                            'secondMemberField': False}, (
        f'disagreeing legacy values must show the FIRST member\'s: {out}')
    assert out['entries'] == ['Rename Multi'], (
        f'one commit must be exactly one history entry: {out["entries"]}')
    assert out['client'] == ['HOUSE', 'HOUSE'], (
        f'the commit must write through to every member: {out}')
    assert out['sVals'] == ['HOUSE', 'HOUSE'], (
        f'the write-through must land on the server for both members: {out}')
    assert out['walked'] == ['FIRST', 'SECOND'], (
        f'one undo must walk every member back: {out}')


# ── 10. multi splits: a chosen boundary, not fixed arithmetic ─────────────
#
# The reference show's remaining hand-work: CEN SL US had two circuits that
# belonged on ANOTHER box, and the only way to say so was typing the labels
# (C2-2-5, C2-2-6) as powerLabelOverrides while the load stayed booked on
# the wrong multi. A split breaks a multi at a chosen circuit boundary;
# each part is a multi of its own, so the remainder pins onto the other
# box's free tails through the ordinary shared-soca gesture and every label
# derives.

def test_no_splits_is_byte_identical_to_the_old_arithmetic(page):
    """A screen without powerSocaSplits groups circuits exactly as
    floor(ordinal / 6) always did - fourteen circuits are 6+6+2, legs
    numbered within each block - and reading the plan never invents the
    store."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 41, name: 'Wide', columns: 14 });
        return sh.withProject({ layers: [S], distros: [] }, () => {
            window.app._circuitTailCache = null;
            const plan = window.app.getSocaPlan(S);
            return {
                shape: plan.map(s => ({ soca: s.soca, legs: s.legs.map(l => l.leg) })),
                store: S.powerSocaSplits === undefined,
            };
        });
    }""")
    assert out['shape'] == [
        {'soca': 1, 'legs': [1, 2, 3, 4, 5, 6]},
        {'soca': 2, 'legs': [1, 2, 3, 4, 5, 6]},
        {'soca': 3, 'legs': [1, 2]},
    ], out
    assert out['store'] is True, 'reading a plan must not create the store'


def test_split_divides_one_multi_and_later_multis_keep_their_spans(page):
    """Splitting multi 1 of a 14-circuit screen after its 2nd circuit gives
    [1-2][3-6][7-12][13-14]: the split divides ITS multi only - the 6-block
    grid stays put, so every multi after the boundary keeps the circuits it
    always had, one index later. Its stores step with it."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 42, name: 'Wide', columns: 14,
            powerSocaNames: { 2: 'MID' }, powerSocaLengths: { 2: '50ft' } });
        return sh.withProject({ layers: [S], distros: [] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            const ok = app.splitSocaAfter(S, 1, 2);
            app._circuitTailCache = null;
            return {
                ok,
                store: S.powerSocaSplits,
                shape: app.getSocaPlan(S).map(s =>
                    ({ soca: s.soca, legs: s.legs.length })),
                names: S.powerSocaNames, lengths: S.powerSocaLengths,
            };
        });
    }""")
    assert out['ok'] is True
    assert out['store'] == [2]
    assert out['shape'] == [
        {'soca': 1, 'legs': 2}, {'soca': 2, 'legs': 4},
        {'soca': 3, 'legs': 6}, {'soca': 4, 'legs': 2}], out
    # the old multi 2 (circuits 7-12) is multi 3 now, name and length intact
    assert out['names'] == {'3': 'MID'}, out
    assert out['lengths'] == {'3': '50ft'}, out


def test_unsplit_rejoins_and_drops_the_second_parts_stores(page):
    """Un-split removes the stored boundary: the parts weld back into the
    natural block, the surviving multi keeps the FIRST part's identity, the
    second part's stores go with its identity, and every later multi steps
    back down."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 43, name: 'Wide', columns: 14,
            powerSocaNames: { 2: 'MID' } });
        return sh.withProject({ layers: [S], distros: [] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            app.splitSocaAfter(S, 1, 2);
            // name the split-off part so the un-split has something to drop
            (S.powerSocaNames || (S.powerSocaNames = {}))[2] = 'TAIL';
            app._circuitTailCache = null;
            const ok = app.unsplitSocaAfter(S, 1);
            app._circuitTailCache = null;
            return {
                ok,
                store: S.powerSocaSplits,
                shape: app.getSocaPlan(S).map(s =>
                    ({ soca: s.soca, legs: s.legs.length })),
                names: S.powerSocaNames,
            };
        });
    }""")
    assert out['ok'] is True
    assert out['store'] == []
    assert out['shape'] == [
        {'soca': 1, 'legs': 6}, {'soca': 2, 'legs': 6},
        {'soca': 3, 'legs': 2}], out
    assert out['names'] == {'2': 'MID'}, out


def test_center_beach_shape_split_remainder_joins_the_other_box(page):
    """The CEN SL US arrangement, without one typed override: four circuits
    split 2+2, the head keeps its own box, the remainder pins onto the
    OFF SL US box (No. 2, tails 1-4 taken) and lands on tails 5-6 - deriving
    C2-2-5 and C2-2-6, the exact strings the user hand-typed into the live
    file."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const OFF = sh.screen({ id: 44, name: 'OFF SL US', columns: 4,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 } });
        const CEN = sh.screen({ id: 45, name: 'CEN SL US', columns: 4,
            offset_x: 1000, powerSocaDistro: { 1: 'd1' } });
        const d = { id: 'd1', name: 'C2', ratingA: 400, voltage: 208, phase: 3 };
        return sh.withProject({ layers: [OFF, CEN], distros: [d] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            app.splitSocaAfter(CEN, 1, 2);
            (CEN.powerSocaDistro || (CEN.powerSocaDistro = {}))[2] = 'd1';
            (CEN.powerSocaNumber || (CEN.powerSocaNumber = {}))[2] = 2;
            app._circuitTailCache = null;
            const labels = app.screenCircuits(CEN).map(c =>
                app.getPowerCircuitLabel(CEN, c.num));
            const share = app.getSocaShare(CEN, 2);
            const box = app.getDistroLoads().find(b => b.id === 'd1');
            return {
                labels,
                shareKey: share && share.key,
                clash: !!(share && (share.clash || share.overflow)),
                tails: share && share.members.map(m =>
                    ({ layer: m.layerName, tails: m.tails })),
                feedsRows: box.socas.length,
            };
        });
    }""")
    assert out['labels'][2:] == ['C2-2-5', 'C2-2-6'], out
    assert out['shareKey'] == 'd1:2'
    assert out['clash'] is False
    assert out['tails'] == [
        {'layer': 'OFF SL US', 'tails': [1, 2, 3, 4]},
        {'layer': 'CEN SL US', 'tails': [5, 6]}], out
    # one feeds row for the shared box, one for CEN's own head multi
    assert out['feedsRows'] == 2, out


def test_split_points_ignore_a_wall_that_shrank(page):
    """A stored boundary at or past the plan's end degrades on read like a
    stale tail set: ignored, never deleted, and the plan falls back to the
    natural blocks."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 46, name: 'Shrunk', columns: 3,
            powerSocaSplits: [2, 3, 9] });
        return sh.withProject({ layers: [S], distros: [] }, () => {
            window.app._circuitTailCache = null;
            return {
                shape: window.app.getSocaPlan(S).map(s =>
                    ({ soca: s.soca, legs: s.legs.length })),
                store: S.powerSocaSplits,
            };
        });
    }""")
    # 3 circuits: boundary 2 still applies, 3 is the plan's own end, 9 is gone
    assert out['shape'] == [{'soca': 1, 'legs': 2}, {'soca': 2, 'legs': 1}], out
    assert out['store'] == [2, 3, 9], 'degrade on read, never rewrite the store'


def test_migrate_soca_keying_leaves_split_ordinals_alone(page):
    """migrateSocaKeying shifts MULTI-NUMBER keys on an S3-# screen;
    powerSocaSplits is keyed by circuit ordinal, not by multi number, so the
    rekey must not walk it."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 47, name: 'Old', columns: 8,
            powerLabelTemplate: 'S3-#',
            powerSocaSplits: [2],
            powerSocaLengths: { 3: '100ft' } });
        delete S.powerSocaKeying;
        return sh.withProject({ layers: [S], distros: [] }, () => {
            const changed = window.app.migrateSocaKeying(S);
            return { changed, splits: S.powerSocaSplits,
                     lengths: S.powerSocaLengths };
        });
    }""")
    assert out['changed'] is True
    assert out['lengths'] == {'1': '100ft'}, out
    assert out['splits'] == [2], 'split ordinals are not multi numbers'


def test_split_round_trips_and_undoes_on_the_real_server(page):
    """The split store follows the three-lists discipline: a real
    splitSocaAfter survives the PUT echo, lands in the server's copy of the
    layer (allow-list), and one undo removes it."""
    out = page.evaluate("""async () => {
        const app = window.app;
        const resp = await fetch('/api/layer/add', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'SplitRT', columns: 4, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: 3400, offset_y: 0 }),
        });
        const made = await resp.json();
        app.project = await (await fetch('/api/project')).json();
        const L = app.project.layers.find(l => l.id === made.id);
        L.powerVoltage = '100'; L.powerAmperage = '5'; L.panelWatts = '100';
        L.powerOrganized = true; L.powerMaximize = false;
        L.powerFlowPattern = 'tl-v';
        app.currentLayer = L;
        app._circuitTailCache = null;
        app.splitSocaAfter(L, 1, 2);
        await new Promise(r => setTimeout(r, 600));
        const clientAfterSplit = (L.powerSocaSplits || []).slice();
        const server = await (await fetch('/api/project')).json();
        const serverLayer = server.layers.find(l => l.id === made.id);
        const serverSplits = (serverLayer.powerSocaSplits || []).slice();
        await app.undo();
        await new Promise(r => setTimeout(r, 600));
        const live = app.project.layers.find(l => l.id === made.id);
        const clientAfterUndo = ((live && live.powerSocaSplits) || []).slice();
        await fetch('/api/layer/' + made.id, { method: 'DELETE' });
        return { clientAfterSplit, serverSplits, clientAfterUndo };
    }""")
    assert out['clientAfterSplit'] == [2]
    assert out['serverSplits'] == [2], \
        'the split must survive the PUT allow-list and the echo re-stamp'
    assert out['clientAfterUndo'] == [], 'one undo removes the split'


def test_multi_name_and_length_edit_on_the_dock_header(page):
    """The soca tiles died with the Power sidebar; a multi's NAME and
    home-run LENGTH edit inline on its dock multi header (keys
    power-soca-name-<layerId>-<idx> / power-soca-length-<layerId>-<idx>,
    the length wearing hw-dock-name-len), and the slot is stated by the
    section's own chips (data-lrd-tile-box "multi-<distro>-<n>") in place
    of the old read-only where line. Split and un-split never came back as
    controls: dropping a slot chip on a later circuit IMPLIES the boundary
    (splitSocaOnto, above; dragged for real in test_hardware_dock.py) and
    right-click merges back. An UNASSIGNED multi has no dock section, so
    no name or length editor until it lands on a distro - the new
    contract: the dock shows hardware, and an unassigned part is only
    spare demand."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 48, name: 'SplitUI', columns: 3,
            powerSocaDistro: { 1: 'd1' } });
        return sh.withProject({ layers: [S], distros: [sh.distro()] }, () => {
            const app = window.app;
            const savedLayer = app.currentLayer;
            try {
                app.currentLayer = S;
                app._circuitTailCache = null;
                app.splitSocaAfter(S, 1, 2);
                app._circuitTailCache = null;
                app.renderHardwareDock();
                const q = k => document.querySelector(
                    `[data-lrd-field="${k}"]`);
                const name1 = q('power-soca-name-48-1');
                const len1 = q('power-soca-length-48-1');
                const head = name1 && name1.closest('.hw-dock-head-row');
                const sec = name1 && name1.closest('.hw-dock-multi');
                return {
                    name1: !!name1,
                    len1: !!len1,
                    lenClass: !!(len1
                        && len1.classList.contains('hw-dock-name-len')),
                    lenPlaceholder: len1 && len1.placeholder,
                    sameHead: !!(head && len1 && head.contains(len1)),
                    name2: !!q('power-soca-name-48-2'),
                    len2: !!q('power-soca-length-48-2'),
                    splitControls: !!document.querySelector(
                        '.power-soca-split, .power-soca-unsplit'),
                    boxes: sec ? [...sec.querySelectorAll(
                        '[data-lrd-tile-box]')].map(
                            t => t.dataset.lrdTileBox) : null,
                };
            } finally { app.currentLayer = savedLayer; }
        });
    }""")
    assert out['name1'] and out['len1'], (
        f'the assigned part must edit name and length on its header: {out}')
    assert out['sameHead'], f'name and length ride ONE multi header: {out}'
    assert out['lenClass'] and out['lenPlaceholder'] == '100ft', out
    assert not out['name2'] and not out['len2'], (
        f'an unassigned multi has no dock section to edit on: {out}')
    assert not out['splitControls'], (
        f'split controls came back as UI: {out}')
    assert out['boxes'] == ['multi-d1-1', 'multi-d1-1'], (
        f'the chips state the slot the old where line stated: {out}')


# ── 10b. the drop-implied split: the boundary falls out of the drop ───────
#
# splitSocaOnto is the engine under app-dock's slot drop: a multi slot
# dropped on a circuit that is NOT the first of its multi splits the multi
# there and the tail-end circuits take the dropped (distro, number) in the
# same motion. Real pointer drags exercising it live in
# test_hardware_dock.py; here the composition itself is pinned.

def test_split_onto_splits_and_assigns_in_one_motion(page):
    """Dropping box (d1, No. 2) on the 3rd circuit of a 4-circuit multi:
    split after 2, the tail part takes the pin - the stores land exactly as
    the old Split-select-then-number-pick pair left them."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 51, name: 'DropSplit', columns: 4 });
        return sh.withProject({ layers: [S], distros: [sh.distro()] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            const r = app.splitSocaOnto(S, 1, 2, 'd1', 2);
            app._circuitTailCache = null;
            return {
                r,
                splits: S.powerSocaSplits,
                distro: S.powerSocaDistro, num: S.powerSocaNumber,
                shape: app.getSocaPlan(S).map(s =>
                    ({ soca: s.soca, legs: s.legs.length })),
            };
        });
    }""")
    assert out['r'] == {'ok': True, 'took': 2, 'tailLen': 2, 'free': 6}, out
    assert out['splits'] == [2]
    assert out['distro'] == {'2': 'd1'} and out['num'] == {'2': 2}, out
    assert out['shape'] == [{'soca': 1, 'legs': 2}, {'soca': 2, 'legs': 2}], out


def test_split_onto_derives_the_center_beach_labels(page):
    """The CEN SL US arrangement in ONE gesture: the remainder joins the
    OFF SL US box (No. 2, tails 1-4 taken) on tails 5-6 and derives C2-2-5,
    C2-2-6 - the strings the user used to hand-type - with the head keeping
    its own multi."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const OFF = sh.screen({ id: 52, name: 'OFF SL US', columns: 4,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 } });
        const CEN = sh.screen({ id: 53, name: 'CEN SL US', columns: 4,
            offset_x: 1000, powerSocaDistro: { 1: 'd1' } });
        return sh.withProject(
            { layers: [OFF, CEN], distros: [sh.distro()] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            const r = app.splitSocaOnto(CEN, 1, 2, 'd1', 2);
            const labels = sh.labelsOf(CEN);
            const share = sh.shareOf(CEN, 2);
            return {
                ok: r.ok, labels,
                clash: !!(share && (share.clash || share.overflow)),
                tails: share && share.members.map(m =>
                    ({ layer: m.layerName, tails: m.tails })),
            };
        });
    }""")
    assert out['ok'] is True
    assert out['labels'][2:] == ['C2-2-5', 'C2-2-6'], out
    assert out['clash'] is False
    assert out['tails'] == [
        {'layer': 'OFF SL US', 'tails': [1, 2, 3, 4]},
        {'layer': 'CEN SL US', 'tails': [5, 6]}], out


def test_split_onto_takes_what_fits_and_leaves_the_rest(page):
    """place-overflow's convention, in tails: the box holds one free tail
    (an incumbent pinned on 5), the drop offers four circuits - one lands,
    on the box's last tail, and the other three become their own multi,
    UNASSIGNED and visible as spare, never rammed onto the full fan as an
    overflow clash."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const OFF = sh.screen({ id: 54, name: 'BigWall', columns: 5,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 } });
        const B = sh.screen({ id: 55, name: 'Joiner', columns: 6,
            offset_x: 1000 });
        return sh.withProject(
            { layers: [OFF, B], distros: [sh.distro()] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            const r = app.splitSocaOnto(B, 1, 2, 'd1', 2);
            const share = sh.shareOf(B, 2);
            return {
                r,
                splits: B.powerSocaSplits,
                distro: B.powerSocaDistro, num: B.powerSocaNumber,
                shape: app.getSocaPlan(B).map(s =>
                    ({ soca: s.soca, legs: s.legs.length,
                       distro: s.distroId || null })),
                clash: !!(share && (share.clash || share.overflow)),
                joinedTail: sh.labelsOf(B)[2],
            };
        });
    }""")
    assert out['r'] == {'ok': True, 'took': 1, 'tailLen': 4, 'free': 1}, out
    assert out['splits'] == [2, 3], out
    assert out['distro'] == {'2': 'd1'} and out['num'] == {'2': 2}, out
    assert out['shape'] == [
        {'soca': 1, 'legs': 2, 'distro': None},
        {'soca': 2, 'legs': 1, 'distro': 'd1'},
        {'soca': 3, 'legs': 3, 'distro': None}], out
    assert out['clash'] is False, 'take-what-fits must never overflow the box'
    assert out['joinedTail'] == 'C2-2-6', out


def test_split_onto_refuses_a_full_box_and_moves_nothing(page):
    """No free tail means the drop refuses outright - the split does not
    happen for nothing, so every store stays byte-identical."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const OFF = sh.screen({ id: 56, name: 'FullWall', columns: 6,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 } });
        const B = sh.screen({ id: 57, name: 'Joiner', columns: 4,
            offset_x: 1000 });
        return sh.withProject(
            { layers: [OFF, B], distros: [sh.distro()] }, () => {
            const app = window.app;
            app._circuitTailCache = null;
            const r = app.splitSocaOnto(B, 1, 2, 'd1', 2);
            return {
                r,
                splits: B.powerSocaSplits === undefined,
                distro: B.powerSocaDistro === undefined,
                num: B.powerSocaNumber === undefined,
            };
        });
    }""")
    assert out['r'] == {'ok': False, 'free': 0, 'tailLen': 2}, out
    assert out['splits'] and out['distro'] and out['num'], (
        f'a refused drop mutated a store: {out}')


# ── 11. one name on two numbers is flagged, never blocked ─────────────────

SAME_NAME_JS = """(joinThem) => {
    const sh = window.__sh;
    const app = window.app;
    const A = sh.screen({ id: 49, name: 'WallA',
        powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
        powerSocaNames: { 1: 'K1' } });
    const B = sh.screen({ id: 50, name: 'WallB', offset_x: 1000,
        powerSocaDistro: { 1: 'd1' },
        powerSocaNumber: { 1: joinThem ? 1 : 2 },
        powerSocaNames: { 1: 'K1' } });
    return sh.withProject(
        { layers: [A, B], distros: [sh.distro('SR')] }, () => {
        const savedLayer = app.currentLayer;
        try {
            app.currentLayer = A;
            app._circuitTailCache = null;
            app.renderHardwareDock();
            const nameA = document.querySelector(
                '[data-lrd-field="power-soca-name-49-1"]');
            const nameB = document.querySelector(
                '[data-lrd-field="power-soca-name-50-1"]');
            return {
                rows: [...document.querySelectorAll(
                    '#hw-dock-issues .hw-dock-issue')].map(r => ({
                        text: r.textContent.replace(/\\s+/g, ' ').trim(),
                        mild: r.classList.contains('hw-dock-issue-mild'),
                    })),
                values: [nameA && nameA.value, nameB && nameB.value],
                fields: [!!nameA, !!nameB],
            };
        } finally { app.currentLayer = savedLayer; }
    });
}"""


def test_same_name_on_two_numbers_warns_amber_and_the_join_clears_it(page):
    """Two multis on one distro DISPLAYING one name while pinned to two
    different numbers: the paperwork says one box, the patch says two. The
    dock's issue strip says so - one AMBER row (a label problem, not a
    block) naming both holders, their numbers, and the way out - stated
    once per (distro, name) because the collision is symmetric. Pinning
    both to one number - the shared-box gesture - clears the row and the
    two headers become one section with ONE name field (ruling
    2026-08-30: one physical box, one field pair - the field anchors on
    the first member's key and the second member's key leaves the
    DOM)."""
    out = page.evaluate(SAME_NAME_JS, False)
    warns = [r for r in out['rows'] if 'names two multis' in r['text']]
    assert len(warns) == 1, (
        f'one symmetric collision is one row, stated once: {out["rows"]}')
    row = warns[0]
    assert row['mild'], f'a label problem warns amber, never red: {row}'
    for piece in ('K1 names two multis on SR', 'WallA at No. 1',
                  'WallB at No. 2', 'Same box? Pin both to No. 1.'):
        assert piece in row['text'], f'{piece!r} missing: {row["text"]}'
    assert out['fields'] == [True, True], \
        'two numbers are two boxes - a field on each header'
    assert out['values'] == ['K1', 'K1'], out

    joined = page.evaluate(SAME_NAME_JS, True)
    assert not any('names two multis' in r['text']
                   for r in joined['rows']), joined['rows']
    assert joined['fields'] == [True, False], (
        'pinned to one number they are one box - ONE name field, the '
        f'first member\'s: {joined}')
    assert joined['values'][0] == 'K1', joined


# ── 12. stored tails are law; joining materializes the incumbents ─────────
#
# The reference show's C1 distro found the two holes in the first cut of
# the model: the strip's pinned parts resolved FIRST (layer order), took
# tail 1 of each box and slid the walls already cabled onto tails 2-5 -
# silent renumbering - and "put me back on 1-4" evaporated because tails
# 1..N were normalized away as the natural arrangement even on a shared
# box, where they are one specific claim among six. These tests pin the
# repaired semantics on the same shapes.

def test_stored_sets_are_law_and_the_joiner_takes_the_free_tails(page):
    """The acceptance arrangement, from stores alone: OFF SR US holds
    1-4 on box 2 and CEN SR US holds 1-4 on box 3 by stored tail set; the
    strip's unstored parts - EARLIER in layer order - take each box's free
    tails. Box 2 reads OFF 1-4 + strip 5, box 3 reads CEN 1-4 + strip 5-6,
    no clash anywhere."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const { STRIP, OFF, CEN, project } = sh.c1({
            off: { powerSocaPhasePos: { 1: [1, 2, 3, 4] } },
            cen: { powerSocaPhasePos: { 1: [1, 2, 3, 4] } },
        });
        return sh.withProject(project, () => ({
            strip: sh.labelsOf(STRIP), off: sh.labelsOf(OFF),
            cen: sh.labelsOf(CEN),
            share2: sh.shareOf(OFF, 1), share3: sh.shareOf(CEN, 1),
        }));
    }""")
    assert out['off'] == ['C1-2-1', 'C1-2-2', 'C1-2-3', 'C1-2-4']
    assert out['cen'] == ['C1-3-1', 'C1-3-2', 'C1-3-3', 'C1-3-4']
    assert out['strip'] == ['C1-2-5', 'C1-3-5', 'C1-3-6'], \
        'the joiner lands on the free tails, wherever it sits in layer order'
    for k in ('share2', 'share3'):
        share = out[k]
        assert share and not share['clash'] and not share['overflow'], out[k]
    assert [m['tails'] for m in out['share2']['members']] == [[5], [1, 2, 3, 4]]
    assert [m['tails'] for m in out['share3']['members']] == [[5, 6], [1, 2, 3, 4]]


def test_pinning_onto_an_occupied_box_stamps_the_incumbents_tails(page):
    """The join materializes what was showing: OFF SR US renders 1-4 alone
    on box 2, and the moment the strip's part pins onto that box, those
    tails become OFF's own stored set - so the joiner deals into tail 5
    and the incumbent's labels never move. The stamped layer rides the
    same updateLayers write as the pin."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const { STRIP, OFF, project } = sh.c1({
            strip: { powerSocaNumber: {} } });
        return sh.withProject(project, () => {
            const calls = [];
            const orig = app.updateLayers;
            app.updateLayers = (layers, save, action) =>
                calls.push({ names: layers.map(l => l.name).sort(),
                             save, action });
            try {
                app._circuitTailCache = null;
                app.setSocaNumber(STRIP, 1, '2');
            } finally { app.updateLayers = orig; }
            return {
                calls,
                offStore: (OFF.powerSocaPhasePos || {})[1] || null,
                off: sh.labelsOf(OFF), strip: sh.labelsOf(STRIP),
            };
        });
    }""")
    assert out['offStore'] == [1, 2, 3, 4], \
        'what the incumbent was showing becomes held'
    assert out['off'] == ['C1-2-1', 'C1-2-2', 'C1-2-3', 'C1-2-4'], \
        'the incumbent keeps the tails it was rendering'
    assert out['strip'][0] == 'C1-2-5', 'the joiner takes the free tail'
    assert out['calls'] == [{
        'names': ['OFF SR US', 'ON SR STRIP'],
        'save': True, 'action': 'Set Multi Number',
    }], 'the stamp persists in the same undoable write as the pin'


def test_the_full_split_and_join_gesture_lands_without_moving_anyone(page):
    """The reference gesture end to end on live setters: split the strip
    after circuit 1, pin part A onto OFF's box, assign and pin part B onto
    CEN's box. Both incumbents' tails are stamped at each join, and the
    final render is the acceptance arrangement on both boxes."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const { STRIP, OFF, CEN, project } = sh.c1({
            strip: { powerSocaSplits: undefined,
                     powerSocaDistro: { 1: 'd1' }, powerSocaNumber: {} } });
        return sh.withProject(project, () => {
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            try {
                app._circuitTailCache = null;
                app.splitSocaAfter(STRIP, 1, 1);
                app._circuitTailCache = null;
                app.setSocaNumber(STRIP, 1, '2');
                app._circuitTailCache = null;
                app.setSocaDistro(STRIP, 2, 'd1');
                app._circuitTailCache = null;
                app.setSocaNumber(STRIP, 2, '3');
            } finally { app.updateLayers = orig; }
            return {
                offStore: (OFF.powerSocaPhasePos || {})[1] || null,
                cenStore: (CEN.powerSocaPhasePos || {})[1] || null,
                strip: sh.labelsOf(STRIP), off: sh.labelsOf(OFF),
                cen: sh.labelsOf(CEN),
            };
        });
    }""")
    assert out['offStore'] == [1, 2, 3, 4]
    assert out['cenStore'] == [1, 2, 3, 4]
    assert out['off'] == ['C1-2-1', 'C1-2-2', 'C1-2-3', 'C1-2-4']
    assert out['cen'] == ['C1-3-1', 'C1-3-2', 'C1-3-3', 'C1-3-4']
    assert out['strip'] == ['C1-2-5', 'C1-3-5', 'C1-3-6']


def test_a_tail_restore_of_one_to_n_persists_on_a_shared_box(page):
    """The exact repair the user typed against the bug: with the strip's
    part sitting on tail 1 and the wall slid to 2-5, "put OFF SR US back
    on 1-4" is a REAL claim on a shared box - stored, honored, and the
    joiner moves to the free tail - never normalized away as the natural
    arrangement."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const { STRIP, OFF, CEN, project } = sh.c1();
        return sh.withProject(project, () => {
            const before = {
                strip: sh.labelsOf(STRIP), off: sh.labelsOf(OFF) };
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            let ok1, ok2;
            try {
                app._circuitTailCache = null;
                ok1 = app.setSocaCircuitPositions(OFF, 1, [1, 2, 3, 4], 4);
                app._circuitTailCache = null;
                ok2 = app.setSocaCircuitPositions(CEN, 1, [1, 2, 3, 4], 4);
            } finally { app.updateLayers = orig; }
            return {
                before, ok1, ok2,
                offStore: (OFF.powerSocaPhasePos || {})[1] || null,
                cenStore: (CEN.powerSocaPhasePos || {})[1] || null,
                strip: sh.labelsOf(STRIP), off: sh.labelsOf(OFF),
                cen: sh.labelsOf(CEN),
            };
        });
    }""")
    # the bugged arrangement this repairs: joiner on tail 1, wall slid
    assert out['before']['strip'][0] == 'C1-2-1'
    assert out['before']['off'] == ['C1-2-2', 'C1-2-3', 'C1-2-4', 'C1-2-5']
    assert out['ok1'] and out['ok2']
    assert out['offStore'] == [1, 2, 3, 4], \
        'tails 1..N on a shared box are a claim, not a default - stored'
    assert out['cenStore'] == [1, 2, 3, 4]
    assert out['off'] == ['C1-2-1', 'C1-2-2', 'C1-2-3', 'C1-2-4']
    assert out['cen'] == ['C1-3-1', 'C1-3-2', 'C1-3-3', 'C1-3-4']
    assert out['strip'] == ['C1-2-5', 'C1-3-5', 'C1-3-6']


def test_a_natural_set_still_normalizes_on_a_solo_multi(page):
    """On a multi that owns its whole box, tails 1..N remain the natural
    arrangement: storing them deletes the entry exactly as before - the
    shared-box exception never leaks into solo behavior."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const S = sh.screen({ id: 71, name: 'Solo',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        return sh.withProject({ layers: [S], distros: [sh.distro()] }, () => {
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            try {
                app._circuitTailCache = null;
                app.setSocaCircuitPositions(S, 1, [2, 3, 5], 3);
                const moved = ((S.powerSocaPhasePos || {})[1] || null);
                app._circuitTailCache = null;
                app.setSocaCircuitPositions(S, 1, [1, 2, 3], 3);
                const natural = (S.powerSocaPhasePos || {})[1] || null;
                return { moved, natural };
            } finally { app.updateLayers = orig; }
        });
    }""")
    assert out['moved'] == [2, 3, 5]
    assert out['natural'] is None, 'solo 1..N normalizes away, as always'


def test_a_leaving_member_keeps_its_stored_set(page):
    """Separation keeps the paperwork: OFF SR US leaves box 2 (back to
    Auto) carrying its stored tails 2-5, which keep rendering on its own
    box; the remaining member's store is untouched and it deals the now
    free tails."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const { STRIP, OFF, project } = sh.c1({
            off: { powerSocaPhasePos: { 1: [2, 3, 4, 5] } } });
        return sh.withProject(project, () => {
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            try {
                app._circuitTailCache = null;
                app.setSocaNumber(OFF, 1, null);
            } finally { app.updateLayers = orig; }
            return {
                offStore: (OFF.powerSocaPhasePos || {})[1] || null,
                stripStore: (STRIP.powerSocaPhasePos || {})[1] || null,
                off: sh.labelsOf(OFF), strip: sh.labelsOf(STRIP),
                share: sh.shareOf(STRIP, 1),
            };
        });
    }""")
    assert out['offStore'] == [2, 3, 4, 5], \
        'its tails are its paperwork - they leave with it'
    assert out['stripStore'] is None, 'the remaining member is untouched'
    # OFF now solo on its auto number (1 - the pins on 2 and 3 are dealt
    # around), still on its stored tails
    assert out['off'] == ['C1-1-2', 'C1-1-3', 'C1-1-4', 'C1-1-5']
    assert out['strip'][0] == 'C1-2-1', \
        'the sole remaining member deals the free tails'
    assert out['share'] is None


def test_layer_order_breaks_ties_only_among_unstored_members(page):
    """Three members on one box: the stored set claims its tails first;
    the two unstored members deal the remaining free tails in layer order.
    (All-unstored boxes keep their layer-order deal byte for byte - the
    NCMF acceptance test above pins that capture.)"""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const A = sh.screen({ id: 72, name: 'UnstoredA', columns: 1,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const B = sh.screen({ id: 73, name: 'StoredB', columns: 2,
            offset_x: 600,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaPhasePos: { 1: [2, 3] } });
        const C = sh.screen({ id: 74, name: 'UnstoredC', columns: 2,
            offset_x: 1200,
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        return sh.withProject(
            { layers: [A, B, C], distros: [sh.distro()] },
            () => ({ share: sh.shareOf(A, 1) }));
    }""")
    share = out['share']
    assert not share['clash'] and not share['overflow']
    assert [(m['layerName'], m['tails']) for m in share['members']] == [
        ('UnstoredA', [1]), ('StoredB', [2, 3]), ('UnstoredC', [4, 5])], \
        'stored claims first; the unstored deal around it in layer order'


def test_balance_apply_sticks_on_a_shared_box_with_stored_members(page):
    """Balance on the post-join state (incumbent stored, joiner stored by a
    previous apply): suggest persists nothing, apply writes every member's
    slice, and the arrangement RENDERS - the stores survive the resolve
    instead of being re-dealt."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const app = window.app;
        const { STRIP, OFF, CEN, project } = sh.c1({
            off: { powerSocaPhasePos: { 1: [1, 2, 3, 4] } },
            cen: { powerSocaPhasePos: { 1: [1, 2, 3, 4] } },
        });
        return sh.withProject(project, () => {
            app._circuitTailCache = null;
            const r = app.suggestPhaseBalance('d1');
            const afterSuggest = {
                off: ((OFF.powerSocaPhasePos || {})[1] || []).slice(),
                strip: (STRIP.powerSocaPhasePos || {})[1] || null,
            };
            const orig = app.updateLayers;
            app.updateLayers = () => {};
            try {
                // member order on box d1:2 is layer order: the strip's
                // part (1 leg), then OFF (4 legs) - the deal gives the
                // strip tail 2 and OFF tails 3-6
                app.applyPhaseBalance([{
                    layerId: 61, soca: 1, name: 'C1-2',
                    members: [{ layerId: 61, soca: 1, legs: 1 },
                              { layerId: 62, soca: 1, legs: 4 }],
                    from: [5, 1, 2, 3, 4], to: [2, 3, 4, 5, 6],
                }]);
            } finally { app.updateLayers = orig; }
            return {
                afterSuggest,
                stripStore: (STRIP.powerSocaPhasePos || {})[1] || null,
                offStore: (OFF.powerSocaPhasePos || {})[1] || null,
                strip: sh.labelsOf(STRIP), off: sh.labelsOf(OFF),
                share: sh.shareOf(OFF, 1),
            };
        });
    }""")
    assert out['afterSuggest']['off'] == [1, 2, 3, 4], \
        'suggest only suggests - the stored set survives the search'
    assert out['afterSuggest']['strip'] is None
    assert out['stripStore'] == [2]
    assert out['offStore'] == [3, 4, 5, 6]
    assert out['strip'][0] == 'C1-2-2'
    assert out['off'] == ['C1-2-3', 'C1-2-4', 'C1-2-5', 'C1-2-6'], \
        'the applied arrangement sticks and renders'
    assert not out['share']['clash'] and not out['share']['overflow']
