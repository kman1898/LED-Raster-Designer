"""The Curve panel's redesign left the curve math as it was (app-curve.js).

The Header/Footer tab's Curve was reworked into three questions (which way
it bends, how much, where the build starts) with the rest under More. The
owner's ruling (2026-11-24): the curve math must not change, the same
settings lay the same bars at the same angles.

What this file pins: for several walls (a plain wall, two bar sizes, a
convex curve from one end, a datum dragged onto a joint, a corner, a three
screen group, a stacked group, a footer, a joint set by hand and a build
picked from Ways to build it), the bars laid on every screen and the angle
at every joint are exactly the ones the app laid before the redesign
(GOLDEN, recorded from dev/draft 3a7ae2d4 with the same steps). The steps
go through the app's own calls, the ones the panel's controls make, so
the comparison does not depend on the panel's layout.

Set LRD_CURVE_GOLDEN_WRITE to a file path to record the table again.

Run locally:
    python -m pytest tests/test_curve_panel_math.py -n 4 --dist loadfile
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_curve_obj import act, group_two, idle, open_rigging, reset  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


def wall(name='WALL', cols=16, x=0, y=0):
    return {'name': name, 'columns': cols, 'rows': 2, 'offset_x': x, 'offset_y': y}


# Each case: the screens, whether they are grouped, the lit sizes, and the
# steps, each [call, args...] on window.app with every screen selected
# (the first the one the tab shows).
CASES = {
    'plain_20_percent': {
        'screens': [wall()], 'sizes': [1],
        'steps': [['on']],
    },
    'two_sizes_72_degrees': {
        'screens': [wall()], 'sizes': [1, 2],
        'steps': [['field', 'entry', 'degrees'], ['field', 'value', 72], ['on']],
    },
    'convex_from_the_left_even': {
        'screens': [wall(cols=14)], 'sizes': [1, 2],
        'steps': [['field', 'bend', 'convex'], ['field', 'from', 'left'], ['field', 'goal', 'even'],
                  ['field', 'value', 15], ['on']],
    },
    'tightest_from_a_joint': {
        'screens': [wall(cols=12)], 'sizes': [1],
        'steps': [['on'], ['field', 'goal', 'tightest'], ['field', 'tolerance', 0.4], ['field', 'from', 5.5]],
    },
    'a_corner': {
        'screens': [wall(cols=12)], 'sizes': [1, 2],
        'steps': [['corner'], ['field', 'value', 8], ['on']],
    },
    'a_three_screen_group_from_the_right': {
        'screens': [wall(f'M{i + 1}', 4, i * 4 * 128) for i in range(3)], 'group': True, 'sizes': [1, 2],
        'steps': [['field', 'value', 15], ['field', 'from', 'right'], ['on']],
    },
    'a_stacked_group': {
        'screens': [wall('TOP', 8), wall('LOW', 4, 256, 256)], 'group': True, 'sizes': [1],
        'steps': [['field', 'value', 10], ['on']],
    },
    'a_footer': {
        'screens': [wall(cols=10)], 'sizes': [1, 2], 'footer': True,
        'steps': [['on'], ['field', 'value', 12]],
    },
    'a_joint_set_by_hand': {
        'screens': [wall()], 'sizes': [1],
        'steps': [['field', 'value', 20], ['on'], ['joint', 3, 2.5]],
    },
    'a_build_picked_by_hand': {
        'screens': [wall()], 'sizes': [1, 2],
        'steps': [['on'], ['pick', 1]],
    },
}

STEP_JS = """([step, ids]) => {
    const app = window.app;
    app.setSelectedLayersByIds(ids, ids[0]);
    app.refreshRiggingPanel();
    const [what, ...args] = step;
    if (what === 'on') app.setRiggingCurveOn(true);
    else if (what === 'field') app.setRiggingCurveField(args[0], args[1]);
    else if (what === 'corner') app.addRiggingCorner();
    else if (what === 'joint') app.setRiggingCurveJoint(args[0], args[1]);
    else if (what === 'pick') {
        const out = app.riggingCurveCached(app.project.layers.find(l => l.id === ids[0]));
        const other = out.result.options.filter(o => o.id !== out.result.chosen_option_id)[args[0] - 1];
        app.setRiggingCurveField('pick', other.id);
    }
}"""

READ_JS = """(ids) => ids.map(id => {
    const l = window.app.project.layers.find(x => x.id === id);
    const t = (l.stage3d && l.stage3d.jointsCol) || {};
    const joints = [];
    for (let j = 0; j < (Number(l.columns) || 0) - 1; j++) joints.push(t[String(j)] ?? null);
    return {
        bars: l.riggingBars || [], starts: l.riggingBarStarts || null,
        footerBars: l.riggingFooterBars || [], footerStarts: l.riggingFooterBarStarts || null,
        joints,
    };
})"""


def run_case(page, case):
    ids = reset(page, case['screens'])
    if case.get('group'):
        group_two(page, ids)
    open_rigging(page)
    page.evaluate("""([ids, sizes, footer]) => {
        const app = window.app;
        app.project.layers.filter(l => ids.includes(l.id)).forEach(l => { l.riggingSizes = [...sizes]; });
        app.setSelectedLayersByIds(ids, ids[0]);
        if (footer) document.querySelector('#rigging-mode-picker [data-mode="footer"]').click();
        app.refreshRiggingPanel();
    }""", [ids, case['sizes'], bool(case.get('footer'))])
    idle(page)
    for step in case['steps']:
        act(page, lambda: page.evaluate(STEP_JS, [step, ids]))
    return page.evaluate(READ_JS, ids)


def test_the_same_settings_lay_the_same_bars_and_angles(page):
    got = {name: run_case(page, case) for name, case in CASES.items()}
    out = os.environ.get('LRD_CURVE_GOLDEN_WRITE')
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(got, f, indent=1, sort_keys=True)
    for name, want in GOLDEN.items():
        assert got[name] == want, (name, got[name], want)
    # every case curved something (a case that lays nothing proves nothing)
    for name, screens in got.items():
        assert any(a for s in screens for a in s['joints']), name
    assert page.errors == []


GOLDEN = {
    'a_build_picked_by_hand': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [2.5, 5, 5, 5, 5, 2.5, 5, 5, 5, 2.5, 5, 5, 5, 5, 2.5]},
    ],
    'a_corner': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'starts': [0, 1, 2, 3, 4, 7, 8, 9, 10, 11], 'footerBars': [], 'footerStarts': None, 'joints': [5, 5, 5, 5, 5, 0, 5, 5, 5, 5, 5]},
    ],
    'a_footer': [
        {'bars': [], 'starts': None, 'footerBars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'footerStarts': None, 'joints': [5, 5, 2.5, 5, 5, 5, 2.5, 5, 5]},
    ],
    'a_joint_set_by_hand': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [0, 7.5, 7.5, 2.5, 0, 7.5, 7.5, 0, 7.5, 7.5, 0, 2.5, 7.5, 7.5, 0]},
    ],
    'a_stacked_group': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [0, 5, 5, 5, 5, 5, 0]},
        {'bars': [], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [5, 5, 5]},
    ],
    'a_three_screen_group_from_the_right': [
        {'bars': [1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [5, 5, 5]},
        {'bars': [1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [5, 5, 5]},
        {'bars': [1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [2.5, 5, 5]},
    ],
    'convex_from_the_left_even': [
        {'bars': [2, 2, 2, 2, 2, 2, 2], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [0, -7.5, 0, -7.5, 0, -7.5, 0, -7.5, 0, -7.5, 0, -7.5, 0]},
    ],
    'plain_20_percent': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [7.5, 0, 7.5, 0, 7.5, 7.5, 0, 7.5, 0, 7.5, 7.5, 0, 7.5, 0, 7.5]},
    ],
    'tightest_from_a_joint': [
        {'bars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [7.5, 5, 5, 7.5, 5, 7.5, 5, 5, 7.5, 5, 7.5]},
    ],
    'two_sizes_72_degrees': [
        {'bars': [1, 2, 2, 1, 2, 2, 1, 2, 2, 1], 'starts': None, 'footerBars': [], 'footerStarts': None, 'joints': [7.5, 0, 7.5, 0, 7.5, 7.5, 0, 7.5, 0, 7.5, 7.5, 0, 7.5, 0, 7.5]},
    ],
}
