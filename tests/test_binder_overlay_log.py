"""Each binder map sheet logs what its map drew (owner, 2026-11-20).

A thin grey line with ticks turned up under a wall on a Power sheet and
the log said nothing about it. Every sheet that paints a map now writes
ONE info line, "Binder 2.3 UPSTAGE · POWER · REAR: runs 11 (power), cable
tags 5 (showPowerCableTags), ...", naming every overlay its map drew with
the count and the setting or source that put it there, and one debug line
with each overlay's boxes in sheet units (app-binder-overlays.js).

Held here, on a seeded show's Power, Data, Header/Footer, Wiring, Simple
and Overview sheets:
  * every overlay listed has ink: boxes on the sheet, on the map;
  * nothing on the map goes unexplained: no "other ink" on any sheet;
  * an overlay that is off is not listed, and one turned on is, counted
    as the map draws it (the multi brackets and their bands, cable tags);
  * the two lines reach the log at their levels.

Run locally:
    python -m pytest tests/test_binder_overlay_log.py -n 4 --dist loadfile --browser chromium
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder_sheet_bounds import WALLS_JS, _opts, page  # noqa: E402,F401


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


MAP_KINDS = ('overview', 'power', 'data', 'rigging', 'wiring')

# Every map sheet of the set painted on its own: its plan entry and what
# its log line said (renderBinderPage's `overlays`), with the map's rect.
SHEETS_JS = r"""([opts, only]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    plan.forEach((p, i) => {
        if (!%s.includes(p.kind)) return;
        if (only && !(p.kind === only.kind && String(p.sheetTitle).startsWith(only.title))) return;
        const r = app.renderBinderPage(opts, i);
        out.push({ number: p.number, kind: p.kind, sheetTitle: p.sheetTitle,
                   overlays: r.overlays, width: r.sheet ? null : null,
                   record: r.record ? { width: r.record.width, height: r.record.height } : null });
    });
    return out;
}""" % repr(list(MAP_KINDS)).replace("'", '"')


def _sheets(pg, only=None, **kw):
    return pg.evaluate(SHEETS_JS, [_opts(**kw), only])


def _kinds(summary):
    return [o['kind'] for o in summary['overlays']]


def _walls(pg):
    out = pg.evaluate(WALLS_JS)
    assert out['layers'] == 4 and all(out['circuits']) and all(out['ports']), out


def test_every_map_sheet_says_what_it_drew_and_nothing_goes_unexplained(page):
    pg, errors = page
    _walls(pg)
    seen = set()
    for mode in ('full', 'simple'):
        sheets = _sheets(pg, mode=mode, sheet='tabloid')
        assert sheets, mode
        for s in sheets:
            o = s['overlays']
            if s['sheetTitle'].endswith('(CONT.)'):
                # a sheet of tables run on from the one before: no map, no line
                assert o is None, (s['number'], o)
                continue
            assert o, (mode, s['number'], s['kind'], 'no overlay line')
            seen.add(s['kind'])
            # one line, named by the sheet's number and title
            assert o['msg'].startswith(f"Binder {s['number']} {s['sheetTitle']}: "), o['msg']
            assert '—' not in o['msg'] and '–' not in o['msg'], o['msg']
            kinds = _kinds(o)
            # every map shows its cabinets
            assert 'cabinets' in kinds, (s['number'], o['msg'])
            # nothing on the map unexplained
            assert not [k for k in kinds if 'other' in k], (s['number'], o['msg'], o['boxes'].get('other ink'))
            W, H = s['record']['width'], s['record']['height']
            for item in o['overlays']:
                # a listed overlay has ink, on the sheet
                box = o['boxes'].get(item['kind'])
                assert box and box['at'], (s['number'], item, o['msg'])
                x1, y1, x2, y2 = box['union']
                assert x2 > x1 - 1 and y2 > y1 - 1 and x1 > -5 and y1 > -5 and x2 < W + 5 and y2 < H + 5, \
                    (s['number'], item['kind'], box['union'], (W, H))
                assert item['n'] >= 1, item
    assert seen >= set(MAP_KINDS), seen


def _power_sheet(pg, name, **kw):
    """The Power sheet of screen `name`, painted alone."""
    sheets = _sheets(pg, only={'kind': 'power', 'title': name.upper() + ' ·'},
                     sides={'power': True, 'data': False}, **kw)
    assert len(sheets) == 1, [(s['number'], s['sheetTitle']) for s in sheets]
    return sheets[0]


SET_JS = r"""async ([name, fields]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === name) || app.project.layers.find(x => x.type !== 'image');
    Object.assign(l, fields);
    await fetch(`/api/layer/${l.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                       body: JSON.stringify(l)});
    window.canvasRenderer.render();
    return l.name;
}"""


def test_an_overlay_that_is_off_is_not_listed_and_one_on_is(page):
    pg, errors = page
    _walls(pg)
    first = pg.evaluate("() => window.app.project.layers.find(l => (l.type || 'screen') === 'screen').name")
    try:
        pg.evaluate(SET_JS, [first, {'showSocaBrackets': False, 'showPowerCableTags': False}])
        off = _power_sheet(pg, first)
        kinds = _kinds(off['overlays'])
        assert 'multi brackets' not in kinds and 'leg ticks' not in kinds, off['overlays']['msg']
        assert 'cable tags' not in kinds, off['overlays']['msg']
        assert 'runs' in kinds and 'rulers' in kinds, off['overlays']['msg']
        runs = next(o for o in off['overlays']['overlays'] if o['kind'] == 'runs')
        assert runs.get('why') == 'power', runs

        pg.evaluate(SET_JS, [first, {'showSocaBrackets': True, 'showPowerCableTags': True}])
        on = _power_sheet(pg, first)
        kinds = _kinds(on['overlays'])
        assert 'multi brackets' in kinds, on['overlays']['msg']
        brackets = next(o for o in on['overlays']['overlays'] if o['kind'] == 'multi brackets')
        assert brackets.get('why') == 'showSocaBrackets', brackets
        # the multis the screen's power is on, one bracket each
        multis = pg.evaluate("""(name) => {
            const l = window.app.project.layers.find(x => x.name === name);
            return window.app.getSocaPlan(l).length; }""", first)
        assert brackets['n'] == multis, (brackets, multis)
        rulers = next(o for o in on['overlays']['overlays'] if o['kind'] == 'rulers')
        assert re.fullmatch(r'(top|bottom|left|right)(/(top|bottom|left|right))*', rulers.get('detail') or ''), rulers
    finally:
        pg.evaluate(SET_JS, [first, {'showSocaBrackets': False, 'showPowerCableTags': True}])


CAPTURE_JS = r"""() => {
    window.__ovl = [];
    if (!window.__ovlHooked) {
        window.__ovlHooked = true;
        const send = navigator.sendBeacon.bind(navigator);
        navigator.sendBeacon = (u, b) => {
            try { b.text().then(t => { const j = JSON.parse(t);
                if (String(j.action).startsWith('binder_sheet_overlay')) window.__ovl.push(j); }); } catch (e) {}
            return send(u, b);
        };
    }
}"""


def test_the_lines_reach_the_log_at_their_levels(page):
    pg, errors = page
    _walls(pg)
    first = pg.evaluate("() => window.app.project.layers.find(l => (l.type || 'screen') === 'screen').name")
    pg.evaluate(CAPTURE_JS)
    sheet = _power_sheet(pg, first)
    pg.wait_for_function("() => (window.__ovl || []).length >= 2", timeout=5000)
    got = pg.evaluate("() => window.__ovl")
    info = [j for j in got if j['action'] == 'binder_sheet_overlays']
    debug = [j for j in got if j['action'] == 'binder_sheet_overlay_boxes']
    assert len(info) == 1 and len(debug) == 1, got
    d = info[0]['details']
    assert d['_lvl'] == 'info' and d['_area'] == 'binder', d
    assert d['_msg'] == sheet['overlays']['msg'], (d['_msg'], sheet['overlays']['msg'])
    assert 'boxes' not in d, d
    b = debug[0]['details']
    assert b['_lvl'] == 'debug' and b['boxes'], b
    assert not errors, errors
