"""Crowding words and box labels after the round 8 audit.

2. A visible multi past a one-circuit output a hidden screen also holds:
   the checks and the tray say the output's whole count, as the pull
   sheet and the distro sheet do, and name the hidden holder.
3. The distro sheet's Crowded line names a box the way the sheet's table
   and the pull sheet do (distroBoxLabels).
5. "an L21-30 208V", never "a L21-30 208V": the overflow line, the tray
   and the box chip.
6. The Power Wiring caption marks an overfull multi box; the pin refusal
   names a hidden holder.

The show is test_distro_rulings_1018's: WALL A (10 x 6, six circuits, one
multi) before WALL B (6 x 3) in the layer list, on PD: TRUE1 x 3 (outputs
1-3, direct) then Socapex x 2 (outputs 4-5).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r8_crowding.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_distro_rulings_1018 import (  # noqa: E402,F401 - fixtures
    _guard, page, seeded, ev, FACE,
)
from test_r6_hidden_slots import setup, HIDDEN  # noqa: E402
from test_r7_crowding import SURFACES_JS  # noqa: E402
from test_audit_final_fixes import CAPTIONS_JS  # noqa: E402

# ── 2. the checks name the hidden holder and agree on the count ──────────

def test_a_visible_multi_past_an_output_a_hidden_screen_holds_names_it(seeded):
    """WALL A (hidden) holds PD1, a TRUE1, with one circuit; WALL B's three
    circuits are pinned onto it. The checks and the tray say the output's
    four circuits, as the pull sheet and the distro sheet do, and name A."""
    pg, errors_ = seeded
    setup(pg, distros=[FACE], walls={
        'a': dict({'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'},
                   'powerSocaNumber': {'1': 1}}, **HIDDEN),
        'b': {'powerSocaSplits': [3], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    out = ev(pg, SURFACES_JS, 1)
    said = ("WALL B's 3 circuits are on PD1, a TRUE1 that takes one circuit only, and PD1 "
            "carries 4 circuits in all. Move it to a multi output. WALL A is hidden and still holds it.")
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    assert out['crowded'] == 4, out
    assert out['binder'] == [['Crowded', 'PD1 TRUE1 carries 4 circuits · a multi on a '
                              'one-circuit output, move it to a multi output']], out['binder']
    assert not errors_, errors_


def test_a_visible_multi_alone_past_its_output_keeps_its_plain_line(seeded):
    pg, errors_ = seeded
    setup(pg, distros=[FACE], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}},
        'b': {'powerSocaSplits': [3], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    out = ev(pg, SURFACES_JS, 1)
    assert ("WALL B's 3 circuits are on PD1, a TRUE1 that takes one circuit only. "
            'Move it to a multi output.') in out['checks'], out['checks']
    assert out['crowded'] == 3, out
    assert not errors_, errors_


# ── 3. the Crowded line names the box as the sheet does ──────────────────

LABELS_JS = """
    app._circuitTailCache = null;
    const d = app.getDistros()[0];
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        if (title === 'Distro') caught.push(pairs.map(p => p.slice()));
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bKvLines = orig; }
    const list = app.buildPullList();
    const box = (list.byScreen[B.id].boxes || []).find(b => b.number === arg) || {};
    return {
        label: app.distroBoxLabels().get(`d1|${arg}`),
        pull: box.name || null,
        binder: (caught[0] || []).filter(([k]) => k === 'Crowded' || k === 'Over capacity'),
        where: app._faceCrowding(d).map(c => c.where),
    };"""


def test_the_crowded_line_of_an_overfull_box_names_it_as_the_sheet_does(seeded):
    pg, errors_ = seeded
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}
    setup(pg, distros=[FACE], walls={'a': dict(pin, powerSocaNames={'1': 'BIG SOCA'}, **HIDDEN),
                                     'b': dict(pin, powerSocaSplits=[3])})
    out = ev(pg, LABELS_JS, 4)
    assert out['label'] == 'BIG SOCA' and out['pull'] == 'BIG SOCA', out
    assert out['binder'] == [['Crowded', 'BIG SOCA Socapex 208V carries 9 circuits · more than '
                              'the six it holds, move a multi to another output']], out['binder']
    assert not errors_, errors_


def test_the_crowded_line_of_a_direct_output_names_it_as_the_sheet_does(seeded):
    pg, errors_ = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[FACE], walls={'a': dict(one, powerSocaNames={'1': 'MAIN'}, **HIDDEN),
                                     'b': dict(one)})
    out = ev(pg, LABELS_JS, 1)
    assert out['label'] == 'MAIN' and out['pull'] == 'MAIN', out
    assert out['where'] == ['MAIN'], out
    assert out['binder'] == [['Crowded', 'MAIN TRUE1 carries 2 circuits · a multi on a '
                              'one-circuit output, move it to a multi output']], out['binder']
    assert not errors_, errors_


# ── 5. an L21-30 ─────────────────────────────────────────────────────────

L2130 = {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
         'outputRows': [{'id': 'r1', 'connector': 'l2130', 'count': 2, 'coupling': 'll',
                         'breakerA': 20}]}


def test_an_overfull_l2130_box_reads_an_l2130(seeded):
    pg, errors_ = seeded
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[L2130], walls={'a': dict(pin, powerSocaSplits=[3], **HIDDEN),
                                      'b': dict(pin, powerSocaSplits=[2])})
    out = ev(pg, """app._circuitTailCache = null;
        const d = app.getDistros()[0];
        app.renderHardwareDock();
        return { checks: app.distroChecks(d).map(w => w.text),
                 strip: (app._dockPowerWarnings || []).map(w => w.text),
                 titles: [...document.querySelectorAll('[title*="OVERFLOW"]')].map(e => e.title) };""")
    said = ('PD1 has more circuits than the three an L21-30 208V holds. '
            'WALL A is hidden and still holds it.')
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    assert out['titles'] and all('three an L21-30' in t for t in out['titles']), out['titles']
    joined = json.dumps(out)
    assert 'a L21-30' not in joined and 'a L6-20' not in joined, joined
    assert not errors_, errors_


def test_the_article_rule(seeded):
    pg, _ = seeded
    out = ev(pg, "return ['L21-30', 'L6-20', 'Edison', 'TRUE1', 'Socapex 208V', 'powerCON 20A',"
                 " 'Multi 208', 'Harting 16E', ''].map(w => app._aAn(w));")
    assert out == ['an', 'an', 'an', 'a', 'a', 'a', 'a', 'a', 'a'], out


# ── 6. the wiring caption and the pin refusal ────────────────────────────

def test_the_pin_refusal_names_a_hidden_holder(seeded):
    pg, _ = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}}
    setup(pg, distros=[FACE], walls={'a': dict(one, powerSocaNumber={'1': 3}, **HIDDEN),
                                     'b': dict(one)})
    out = ev(pg, """const n = app.historyIndex;
        const t = app.setSocaNumber(B, 1, 3);
        return { touched: t.length, same: app.historyIndex === n, pin: (B.powerSocaNumber || {})[1] ?? null,
                 status: document.getElementById('status-message').textContent };""")
    assert out['touched'] == 0 and out['same'] and out['pin'] is None, out
    assert out['status'] == ('PD3 already carries its one circuit, and a TRUE1 takes no more. '
                             'WALL A is hidden and still holds it.'), out


def test_the_wiring_caption_marks_an_overfull_box(seeded):
    pg, errors_ = seeded
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}
    setup(pg, distros=[FACE], walls={'a': dict(pin, **HIDDEN), 'b': dict(pin, powerSocaSplits=[3])})
    titles = pg.evaluate(CAPTIONS_JS, 'WALL B')
    assert [t for t in titles if t.endswith(' · 9 circuits on a six-circuit output')], titles
    # a box within its six says nothing of the kind
    setup(pg, distros=[FACE], walls={'a': dict(pin), 'b': dict(pin, powerSocaSplits=[3], powerSocaNumber={'1': 5})})
    titles = pg.evaluate(CAPTIONS_JS, 'WALL B')
    assert not [t for t in titles if 'circuits on a' in t], titles
    assert not errors_, errors_
