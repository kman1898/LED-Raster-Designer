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
  - Member order is project layer order. An unstored member lands on the
    box's next free tails; a stored tail set (balance, hand move) is never
    rearranged - if it collides, that is a CLASH, said out loud (tile face,
    lrd-tile-clash) the way port assignment reports an occupied socket.
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
    """A member whose STORED tails land on tails an earlier member holds is
    a clash: both keep their tails (the duplicate labels stay visible),
    and the share record says which tails are claimed twice - nothing is
    silently rearranged."""
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
    assert out['a'] == ['C2-1-1', 'C2-1-2', 'C2-1-3']
    assert out['b'] == ['C2-1-1', 'C2-1-2', 'C2-1-3'], \
        'stored tails print verbatim - the duplicate IS the report'
    share = out['share']
    assert share['clash'] and not share['overflow']
    assert share['members'][1]['clashTails'] == [1, 2, 3]


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


# ── 8. the tiles say one box, and the pick reads as the join ──────────────

SHOW_TILES_JS = """(cfg) => {
    const sh = window.__sh;
    const app = window.app;
    const { A, B, project } = sh.ncmf();
    if (cfg && cfg.clash) B.powerSocaPhasePos = { 1: [1, 2, 3] };
    return sh.withProject(project, () => {
        const savedLayer = app.currentLayer;
        try {
            app.currentLayer = cfg && cfg.first ? A : B;
            app._circuitTailCache = null;
            app.refreshSocaRuns();
            const txt = el => el ? el.textContent.replace(/\\s+/g, ' ').trim() : null;
            const tile = document.querySelector('#power-soca-runs .power-soca-row');
            const sel = tile.querySelector('.power-soca-number');
            return {
                face: txt(tile.querySelector('.lrd-tile-face')),
                clashClass: tile.classList.contains('lrd-tile-clash'),
                note: txt(tile.querySelector('.power-soca-share-note')),
                options: sel ? [...sel.options].map(o => o.textContent.trim()) : null,
                selected: sel ? sel.value : null,
            };
        } finally {
            app.currentLayer = savedLayer;
        }
    });
}"""


def test_tile_face_reads_one_box_not_two_multis(page):
    """The joined tile's face carries the shared name and THIS screen's
    tails - a tech glancing at the panel sees one box - and the body names
    every member with its tails. The number select annotates the occupied
    slot with who holds it, so picking it reads as the join."""
    out = page.evaluate(SHOW_TILES_JS, {})
    assert out['face'] == 'C2-3 · tails 4-6 · 15.0 A'
    assert not out['clashClass']
    assert out['note'] == ('One physical multi — ON SL STRIP tails 1-3 · '
                           'CEN SL STRIP tails 4-6')
    assert out['selected'] == '3'
    assert out['options'][0] == 'Auto'
    assert '3 — with ON SL STRIP' in out['options']


def test_tile_wears_the_clash(page):
    """A tail collision wears the same clash dress a double-booked port tile
    wears: lrd-tile-clash on the tile, TAIL CLASH on the face, and the body
    names the tails claimed twice."""
    out = page.evaluate(SHOW_TILES_JS, {"clash": True})
    assert out['clashClass']
    assert 'TAIL CLASH' in out['face']
    assert 'claimed twice' in out['note'] and '1-3' in out['note']


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


def test_split_controls_live_in_the_tile_editor(page):
    """The gesture is the tile's: a multi with more than one circuit offers
    "Split… / after <label>" in its open editor, the part whose end is a
    stored boundary offers Un-split, and a 1-leg part offers no split."""
    out = page.evaluate("""() => {
        const sh = window.__sh;
        const S = sh.screen({ id: 48, name: 'SplitUI', columns: 3 });
        return sh.withProject({ layers: [S], distros: [] }, () => {
            const app = window.app;
            const savedLayer = app.currentLayer;
            try {
                app.currentLayer = S;
                app._circuitTailCache = null;
                app.splitSocaAfter(S, 1, 2);
                app._circuitTailCache = null;
                app.refreshSocaRuns();
                const tiles = [...document.querySelectorAll(
                    '#power-soca-runs .power-soca-row')];
                return tiles.map(t => ({
                    split: [...(t.querySelector('.power-soca-split')
                        || { options: [] }).options].map(o => o.textContent.trim()),
                    unsplit: !!t.querySelector('.power-soca-unsplit'),
                }));
            } finally { app.currentLayer = savedLayer; }
        });
    }""")
    assert len(out) == 2, out
    # part 1 (2 legs, user boundary at its end): split offer + Un-split
    assert out[0]['split'][0] == 'Split…' and len(out[0]['split']) == 2
    assert out[0]['unsplit'] is True
    # part 2 (1 leg): nothing to split, no boundary at its end
    assert out[1]['split'] == [] and out[1]['unsplit'] is False


# ── 11. one name on two numbers is flagged, never blocked ─────────────────

def test_same_name_on_two_numbers_flags_the_tile_and_the_join_clears_it(page):
    """Two multis on one distro DISPLAYING one name while pinned to two
    different numbers: the paperwork says one box, the patch says two. The
    tile says so (SAME NAME on the face, the note naming the other holder)
    and pinning both to one number - the shared-box gesture - clears it."""
    out = page.evaluate("""(joinThem) => {
        const sh = window.__sh;
        const A = sh.screen({ id: 49, name: 'WallA',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaNames: { 1: 'K1' } });
        const B = sh.screen({ id: 50, name: 'WallB', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' },
            powerSocaNumber: { 1: joinThem ? 1 : 2 },
            powerSocaNames: { 1: 'K1' } });
        return sh.withProject(
            { layers: [A, B], distros: [sh.distro('SR')] }, () => {
            const app = window.app;
            const savedLayer = app.currentLayer;
            try {
                app.currentLayer = A;
                app._circuitTailCache = null;
                app.refreshSocaRuns();
                const tile = document.querySelector(
                    '#power-soca-runs .power-soca-row');
                const note = tile.querySelector('.power-soca-name-note');
                return {
                    face: tile.querySelector('.lrd-tile-face')
                        .textContent.replace(/\\s+/g, ' ').trim(),
                    note: note ? note.textContent.replace(/\\s+/g, ' ').trim() : null,
                };
            } finally { app.currentLayer = savedLayer; }
        });
    }""", False)
    assert 'SAME NAME' in out['face'], out
    assert out['note'] and 'K1' in out['note'] and 'WallB' in out['note'], out
    assert 'No. 1' in out['note'], out

    joined = page.evaluate("""(joinThem) => {
        const sh = window.__sh;
        const A = sh.screen({ id: 49, name: 'WallA',
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
            powerSocaNames: { 1: 'K1' } });
        const B = sh.screen({ id: 50, name: 'WallB', offset_x: 1000,
            powerSocaDistro: { 1: 'd1' },
            powerSocaNumber: { 1: joinThem ? 1 : 2 },
            powerSocaNames: { 1: 'K1' } });
        return sh.withProject(
            { layers: [A, B], distros: [sh.distro('SR')] }, () => {
            const app = window.app;
            const savedLayer = app.currentLayer;
            try {
                app.currentLayer = A;
                app._circuitTailCache = null;
                app.refreshSocaRuns();
                const tile = document.querySelector(
                    '#power-soca-runs .power-soca-row');
                return {
                    face: tile.querySelector('.lrd-tile-face')
                        .textContent.replace(/\\s+/g, ' ').trim(),
                    note: !!tile.querySelector('.power-soca-name-note'),
                    share: !!tile.querySelector('.power-soca-share-note'),
                };
            } finally { app.currentLayer = savedLayer; }
        });
    }""", True)
    assert 'SAME NAME' not in joined['face'], joined
    assert joined['note'] is False, joined
    assert joined['share'] is True, 'pinned to one number they are one box'
