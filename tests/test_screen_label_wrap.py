"""The screen label wraps instead of running off the screen.

Owner, 2026-09-23, with a rendered example: "in the example where the
screen label runs off the screen we need to double stack it or more aka
wrap it". The example is a 7 x 8 wall of 256 px cabinets (1792 px wide)
whose Data and Power screen-name size is 150: the port line "7 Mains, 7
Backups | 14 Ports" and the circuit line "8 Multi, 16 Circuits | 30.21A 1φ
/ 17.46A 3φ" were drawn as ONE line about two and a half times the wall's
width, off both edges - on the canvas, in the exports and on the binder's
maps, which all go through the one renderer.

canvas-labels.js now wraps every line of the label that is wider than the
screen's drawn width (less the plate's pad each side) without shrinking
the type: first at " | ", then at ", " and " · ", then at spaces, each
level filling greedily; a single word wider than the screen stays on its
own line. The screen name (or the group's name) stays centred on its own
line(s) at the top with the info line(s) centred beneath it - "honestly
the screen name should be centered and then 7 mains and backups should be
under it anyways" - and a label that fits is drawn exactly as before.

These tests read the text the renderer actually draws (every fillText of
one render, with its font and position) rather than pixels, so they hold
the label to its geometry: line widths against the wall, the lines' common
centre x, their order top to bottom, and the drag hit rect around the name.

Run locally:
    python3 -m pytest tests/test_screen_label_wrap.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import _SHOW_JSON  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The owner's wall: 7 x 8 of 256 px cabinets, 1792 px across.
COLS, ROWS, CAB = 7, 8, 256
WALL_W = COLS * CAB
# canvas-labels.js: the plate's pad, the line height's lead over the size
PAD = 6
LEAD = 4
# the owner's label size, and one that fits on one line
BIG, SMALL = 150, 30
# a name wider than the wall at BIG, so the NAME wraps too (at its spaces)
LONG_NAME = 'UPSTAGE CENTER VIDEO WALL SECTION'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# One screen, the owner's shape, on a NovaStar H9 with one 16-port card and
# its ports placed, so the Data view has a port count to print; 208 V 10 A
# circuits at 200 W a cabinet so the Power view has circuits.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'BIG', columns: %d, rows: %d,
               cabinet_width: %d, cabinet_height: %d, offset_x: 100, offset_y: 100,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-v',
               processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    const p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('label_wrap_seed');
    const l = app.project.layers.find(l => l.name === 'BIG');
    app.selectLayer(l);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                 {layerId: String(l.id), cardId});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    l.showDataFlowPortInfo = true;
    l.showPowerCircuitInfo = true;
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Label Wrap Seed');
    return { id: l.id, panels: l.panels.length, ports: app.getLayerPortsRequired(l),
             circuits: app.screenCircuitCount(l) };
}""" % (COLS, ROWS, CAB, CAB)

# One render of the working view (or of an export, when `exportMode`) with
# the label size, the name toggle and the name set as asked, every fillText
# recorded with its font, its position and its measured width. Restores
# the layer and the renderer afterwards.
DRAW_JS = """([view, size, showName, name, exportMode]) => {
    const r = window.canvasRenderer, app = window.app;
    const l = app.project.layers.find(l => l.name === 'BIG' || l.name === %r);
    const keep = { name: l.name, sizeD: l.screenNameSizeDataFlow, sizeP: l.screenNameSizePower,
                   sizeC: l.screenNameSizeCabinet, font: l.labelsFontSize,
                   nameD: l.showLabelNameDataFlow, nameP: l.showLabelNamePower,
                   nameC: l.showLabelNameCabinet, nameAll: l.showLabelName,
                   view: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
                   canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode };
    l.name = name;
    l.screenNameSizeDataFlow = size; l.screenNameSizePower = size;
    l.screenNameSizeCabinet = size;
    // Pixel Map's one slider sizes its name and its lines; on every other
    // view the Pixel Map slider stays at its default, so a line height
    // taken from the wrong slider shows up as lines drawn on top of each
    // other.
    if (view === 'pixel-map') l.labelsFontSize = size;
    l.showLabelNameDataFlow = showName; l.showLabelNamePower = showName;
    l.showLabelNameCabinet = showName; l.showLabelName = showName;
    r.viewMode = view;
    if (exportMode) {
        const ex = document.createElement('canvas');
        ex.width = 4096; ex.height = 4096;
        r.canvas = ex; r.ctx = ex.getContext('2d');
        r.exportMode = true; r.zoom = 1; r.panX = 0; r.panY = 0;
    }
    // Only the text renderLayerLabels itself draws: the port run labels and
    // cabinet ids share the label's font at some sizes.
    const ctx = r.ctx, orig = ctx.fillText, texts = [];
    const origLabels = r.renderLayerLabels;
    let inLabels = 0;
    r.renderLayerLabels = function (...a) {
        inLabels++;
        try { return origLabels.apply(this, a); } finally { inLabels--; }
    };
    ctx.fillText = function (t, x, y, w) {
        if (inLabels > 0) {
            texts.push({ t: String(t), x, y, font: ctx.font, w: ctx.measureText(String(t)).width });
        }
        return orig.call(ctx, t, x, y, w);
    };
    let bounds, rect;
    try {
        r.render();
        bounds = r.getLayerBounds(l);
        rect = l._screenNameHitRect ? Object.assign({}, l._screenNameHitRect) : null;
    } finally {
        ctx.fillText = orig;
        delete r.renderLayerLabels;
        l.name = keep.name;
        l.screenNameSizeDataFlow = keep.sizeD; l.screenNameSizePower = keep.sizeP;
        l.screenNameSizeCabinet = keep.sizeC; l.labelsFontSize = keep.font;
        l.showLabelNameDataFlow = keep.nameD; l.showLabelNamePower = keep.nameP;
        l.showLabelNameCabinet = keep.nameC; l.showLabelName = keep.nameAll;
        r.viewMode = keep.view;
        if (exportMode) {
            r.exportMode = keep.exportMode; r.canvas = keep.canvas; r.ctx = keep.ctx;
            r.zoom = keep.zoom; r.panX = keep.panX; r.panY = keep.panY;
        }
        r.render();
    }
    return { texts, bounds, rect, ports: app.getLayerPortsRequired(l),
             circuits: app.screenCircuitCount(l) };
}""" % LONG_NAME

# The helper on its own, at a bold 30 px font: the widths of the pieces it
# may break the owner's line into, and what it returns at a given room.
WRAP_JS = """([text, room]) => {
    const r = window.canvasRenderer, ctx = r.ctx;
    const keep = ctx.font;
    ctx.font = 'bold 30px Arial';
    try {
        const w = (t) => ctx.measureText(t).width;
        const widths = {};
        for (const t of ['7 Mains, 7 Backups | 14 Ports', '7 Mains, 7 Backups', '14 Ports',
                         '7 Mains,', '7 Backups', 'Supercalifragilisticexpialidocious']) widths[t] = w(t);
        const maxWidth = typeof room === 'string' ? widths[room] : room;
        return { lines: r._wrapLabelLine(text, maxWidth), widths, maxWidth };
    } finally { ctx.font = keep; }
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    seed = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert seed['panels'] == COLS * ROWS, seed
    assert seed['ports'] > 0, ('the seeded wall needs no ports - the label has no port line', seed)
    assert seed['circuits'] > 0, ('the seeded wall needs no circuits - the label has no circuit line', seed)
    seed['errors'] = errors
    yield pg, seed
    context.close()


def _label_texts(out, size):
    """The label's own lines: the bold text at the label's size, in draw
    order. Port discs and circuit labels are drawn at other sizes."""
    tag = 'bold %dpx' % size
    return [t for t in out['texts'] if t['font'].startswith(tag)]


def _info_line(view, out):
    """The one line the label would carry unwrapped."""
    if view == 'data-flow':
        n = out['ports']
        return '%d Mains, %d Backups | %d Ports' % (n, n, 2 * n)
    return None


def _pieces(line):
    return [p.strip() for bar in line.split(' | ') for p in bar.split(', ')]


def _check_wrapped(view, out, size, name):
    """The label as drawn: the name line(s) first, then the info line(s);
    every line inside the wall's inner width (a single word excepted);
    every line on one centre x; the lines stacked top to bottom; and the
    info lines rejoin to the unwrapped line."""
    lines = _label_texts(out, size)
    assert lines, [t['t'] for t in out['texts']][:40]
    inner = out['bounds']['width'] - 2 * PAD
    for t in lines:
        if ' ' in t['t']:
            assert t['w'] <= inner + 0.5, ('a label line wider than the wall', t, inner)
    xs = set(round(t['x'], 1) for t in lines)
    assert len(xs) == 1, ('the label lines are not on one centre', [(t['t'], t['x']) for t in lines])
    ys = [t['y'] for t in lines]
    assert ys == sorted(ys), ('the label lines are not stacked in draw order', [(t['t'], t['y']) for t in lines])
    assert len(set(ys)) == len(ys), ('two label lines on one y', [(t['t'], t['y']) for t in lines])
    # the name's lines: the leading lines that rejoin, in order, to the name
    name_lines = []
    if name:
        for t in lines:
            joined = ' '.join(x['t'] for x in name_lines + [t])
            if name == joined or name.startswith(joined + ' '):
                name_lines.append(t)
            if joined == name:
                break
        assert ' '.join(t['t'] for t in name_lines) == name, ('no name line drawn at the top', [t['t'] for t in lines])
    info_lines = [t for t in lines if t not in name_lines]
    if name:
        # the name sits ABOVE every info line, its lines contiguous at the top
        assert lines[:len(name_lines)] == name_lines, [t['t'] for t in lines]
        if info_lines:
            assert max(t['y'] for t in name_lines) < min(t['y'] for t in info_lines)
    else:
        assert not name_lines, [t['t'] for t in lines]
    return name_lines, info_lines


# ---- the owner's example ----------------------------------------------------

def test_the_data_port_line_wraps_at_the_bar_on_the_owners_wall(page):
    """7 x 8 at 256 px, size 150, Data view: "N Mains, N Backups | 2N
    Ports" is drawn on two (or more) lines, none wider than the wall, one
    centre x, the name centred above them. The hit rect around the name is
    the name's own plate, inside the wall."""
    pg, seed = page
    out = pg.evaluate(DRAW_JS, ['data-flow', BIG, True, 'BIG', False])
    name_lines, info = _check_wrapped('data-flow', out, BIG, 'BIG')
    line = _info_line('data-flow', out)
    assert [t['t'] for t in info] != [line], 'the port line was not wrapped'
    assert len(info) >= 2, [t['t'] for t in info]
    assert ' '.join(t['t'] for t in info) == line.replace(' | ', ' '), [t['t'] for t in info]
    assert not any(' | ' in t['t'] for t in info), [t['t'] for t in info]
    # the greedy fill: at 150 px the two bar clauses are each one line
    assert [t['t'] for t in info] == ['%d Mains, %d Backups' % (out['ports'], out['ports']),
                                      '%d Ports' % (2 * out['ports'])]
    # two line heights of info, stacked
    assert info[-1]['y'] - info[0]['y'] == pytest.approx((len(info) - 1) * (BIG + LEAD), abs=1.5)
    rect = out['rect']
    assert rect and rect['viewMode'] == 'data-flow', rect
    assert rect['x2'] - rect['x1'] <= out['bounds']['width'] + 2 * PAD
    assert rect['y2'] - rect['y1'] == pytest.approx(BIG + LEAD + 2 * PAD, abs=0.01)
    assert seed['errors'] == []


def test_the_power_circuit_line_wraps_on_the_owners_wall(page):
    """The same wall on the Power view: "M Multi, C Circuits | xxA 1φ /
    yyA 3φ" wraps the same way, name above, nothing past the wall."""
    pg, seed = page
    out = pg.evaluate(DRAW_JS, ['power', BIG, True, 'BIG', False])
    _name_lines, info = _check_wrapped('power', out, BIG, 'BIG')
    assert len(info) >= 2, [t['t'] for t in info]
    joined = ' '.join(t['t'] for t in info)
    assert 'Multi' in joined, joined
    assert '%d Circuits' % out['circuits'] in joined, joined
    assert '1φ' in joined and '3φ' in joined, joined
    assert not any(' | ' in t['t'] for t in info), [t['t'] for t in info]
    rect = out['rect']
    assert rect and rect['viewMode'] == 'power', rect
    assert rect['y2'] - rect['y1'] == pytest.approx(BIG + LEAD + 2 * PAD, abs=0.01)
    assert seed['errors'] == []


def test_a_label_that_fits_is_drawn_as_before(page):
    """At size 30 the port line fits the wall: one line, the bar kept, and
    the name's hit rect is the single-line plate of the old geometry - its
    height one line plus the pad, its width the name plus the pad, centred
    on the wall."""
    pg, seed = page
    out = pg.evaluate(DRAW_JS, ['data-flow', SMALL, True, 'BIG', False])
    _name_lines, info = _check_wrapped('data-flow', out, SMALL, 'BIG')
    assert [t['t'] for t in info] == [_info_line('data-flow', out)], [t['t'] for t in info]
    rect = out['rect']
    b = out['bounds']
    name_w = next(t['w'] for t in _label_texts(out, SMALL) if t['t'] == 'BIG')
    assert rect['y2'] - rect['y1'] == pytest.approx(SMALL + LEAD + 2 * PAD, abs=0.01)
    assert rect['x2'] - rect['x1'] == pytest.approx(name_w + 2 * PAD, abs=0.01)
    # centred on the wall (world coords; the wall sits at 100, 100 on canvas 1)
    assert abs((rect['x1'] + rect['x2']) / 2 - (b['x'] + b['width'] / 2)) <= 1.0, (rect, b)
    assert abs((rect['y1'] + rect['y2']) / 2 - (b['y'] + b['height'] / 2)) <= 1.0, (rect, b)
    # the info line hangs under the plate, 5 px clear of it
    assert info[0]['y'] > rect['y2']
    assert seed['errors'] == []


def test_a_long_name_wraps_and_the_hit_rect_covers_every_line(page):
    """A screen name wider than the wall at 150 px wraps at its spaces; the
    plate - and the drag hit rect - is as tall as all of its lines and no
    wider than the wall, and the port line still sits beneath the last of
    them."""
    pg, seed = page
    out = pg.evaluate(DRAW_JS, ['data-flow', BIG, True, LONG_NAME, False])
    name_lines, info = _check_wrapped('data-flow', out, BIG, LONG_NAME)
    assert len(name_lines) >= 2, [t['t'] for t in name_lines]
    rect = out['rect']
    assert rect['y2'] - rect['y1'] == pytest.approx(len(name_lines) * (BIG + LEAD) + 2 * PAD, abs=0.01)
    assert rect['x2'] - rect['x1'] <= out['bounds']['width'] + 0.5, (rect, out['bounds'])
    widest = max(t['w'] for t in name_lines)
    assert rect['x2'] - rect['x1'] == pytest.approx(widest + 2 * PAD, abs=0.01)
    # every name line inside the plate, the info lines below it
    for t in name_lines:
        assert rect['y1'] < t['y'] < rect['y2'], (t, rect)
    assert info and min(t['y'] for t in info) > rect['y2']
    assert seed['errors'] == []


def test_with_the_name_off_the_info_lines_stand_centred_on_their_own(page):
    """Name toggle off: no name line, and the wrapped info lines are centred
    on the wall by themselves - the block's middle on the wall's middle."""
    pg, seed = page
    out = pg.evaluate(DRAW_JS, ['data-flow', BIG, False, 'BIG', False])
    name_lines, info = _check_wrapped('data-flow', out, BIG, '')
    assert not name_lines and len(info) >= 2, [t['t'] for t in info]
    assert out['rect'] is None
    b = out['bounds']
    mid = (info[0]['y'] + info[-1]['y']) / 2
    assert abs(mid - (b['y'] + b['height'] / 2)) <= 1.0, (mid, b)
    assert seed['errors'] == []


@pytest.mark.parametrize('view', ['data-flow', 'power', 'cabinet-id', 'pixel-map'])
def test_every_view_and_the_export_wrap_the_same_way(page, view):
    """The one renderer serves the canvas and the export: on every view the
    label's lines fit the wall on screen and in exportMode alike, and the
    two draw the same lines."""
    pg, seed = page
    screen = pg.evaluate(DRAW_JS, [view, BIG, True, LONG_NAME, False])
    export = pg.evaluate(DRAW_JS, [view, BIG, True, LONG_NAME, True])
    on_screen = _check_wrapped(view, screen, BIG, LONG_NAME)
    exported = _check_wrapped(view, export, BIG, LONG_NAME)
    assert [t['t'] for t in on_screen[0] + on_screen[1]] == [t['t'] for t in exported[0] + exported[1]]
    assert len(on_screen[0]) >= 2
    assert export['rect'] is None, 'an export caches no hit rect'
    assert seed['errors'] == []


def test_the_binders_map_wraps_the_port_line_too(page):
    """The binder paints its map with the same renderer (hideScreenNames
    on: the title block names the screen), so its Data sheet carries the
    port line wrapped and never the one-line form."""
    pg, seed = page
    keep = pg.evaluate("""() => {
        const l = window.app.project.layers.find(l => l.name === 'BIG');
        const keep = [l.screenNameSizeDataFlow, l.screenNameSizePower];
        l.screenNameSizeDataFlow = %d; l.screenNameSizePower = %d;
        return keep;
    }""" % (BIG, BIG))
    try:
        out = pg.evaluate("""(opts) => {
            const app = window.app;
            const plan = app.planBinder(opts);
            const idx = plan.findIndex(p => p.title === 'BIG - Data - Front View');
            if (idx < 0) return { missing: plan.map(p => p.title) };
            return { mapTexts: app.renderBinderPage(opts, idx).mapTexts,
                     ports: app.getLayerPortsRequired(app.project.layers.find(l => l.name === 'BIG')) };
        }""", json.loads(_SHOW_JSON))
    finally:
        pg.evaluate("""(keep) => {
            const l = window.app.project.layers.find(l => l.name === 'BIG');
            l.screenNameSizeDataFlow = keep[0]; l.screenNameSizePower = keep[1];
            window.canvasRenderer.render();
        }""", keep)
    assert 'missing' not in out, out
    n = out['ports']
    texts = out['mapTexts']
    assert '%d Mains, %d Backups | %d Ports' % (n, n, 2 * n) not in texts, texts
    assert '%d Mains, %d Backups' % (n, n) in texts, texts
    assert '%d Ports' % (2 * n) in texts, texts
    assert 'BIG' not in texts, texts
    assert seed['errors'] == []


# ---- the helper on its own ---------------------------------------------------

def test_the_helper_breaks_at_the_bar_first(page):
    pg, _seed = page
    out = pg.evaluate(WRAP_JS, ['7 Mains, 7 Backups | 14 Ports', '7 Mains, 7 Backups'])
    assert out['maxWidth'] < out['widths']['7 Mains, 7 Backups | 14 Ports']
    assert out['lines'] == ['7 Mains, 7 Backups', '14 Ports']


def test_the_helper_then_breaks_at_the_comma_keeping_it(page):
    pg, _seed = page
    out = pg.evaluate(WRAP_JS, ['7 Mains, 7 Backups | 14 Ports', 0])
    w = out['widths']
    room = max(w['7 Mains,'], w['7 Backups'], w['14 Ports']) + 1
    assert room < w['7 Mains, 7 Backups']
    out = pg.evaluate(WRAP_JS, ['7 Mains, 7 Backups | 14 Ports', room])
    assert out['lines'] == ['7 Mains,', '7 Backups', '14 Ports']


def test_the_helper_returns_a_fitting_line_unchanged(page):
    pg, _seed = page
    out = pg.evaluate(WRAP_JS, ['7 Mains, 7 Backups | 14 Ports', '7 Mains, 7 Backups | 14 Ports'])
    assert out['lines'] == ['7 Mains, 7 Backups | 14 Ports']
    out = pg.evaluate(WRAP_JS, ['7 Mains, 7 Backups | 14 Ports', 1e9])
    assert out['lines'] == ['7 Mains, 7 Backups | 14 Ports']


def test_the_helper_leaves_a_single_over_wide_word_alone(page):
    pg, _seed = page
    out = pg.evaluate(WRAP_JS, ['Supercalifragilisticexpialidocious', 10])
    assert out['lines'] == ['Supercalifragilisticexpialidocious']
    # and a line of such words: each on its own line, none dropped
    out = pg.evaluate(WRAP_JS, ['Supercalifragilisticexpialidocious Supercalifragilisticexpialidocious', 10])
    assert out['lines'] == ['Supercalifragilisticexpialidocious', 'Supercalifragilisticexpialidocious']


def test_the_helper_greedily_fills_at_the_dot_and_the_space(page):
    pg, _seed = page
    out = pg.evaluate("""() => {
        const r = window.canvasRenderer, ctx = r.ctx, keep = ctx.font;
        ctx.font = 'bold 30px Arial';
        try {
            const w = (t) => ctx.measureText(t).width;
            return {
                dot: r._wrapLabelLine('aa · bb · cc · dd', w('aa · bb') + 1),
                space: r._wrapLabelLine('one two three four', w('one two three') + 1),
                // a comma clause too wide for its room falls through to spaces
                deep: r._wrapLabelLine('aa, bb cc dd', w('bb cc') + 1),
            };
        } finally { ctx.font = keep; }
    }""")
    assert out['dot'] == ['aa · bb', 'cc · dd']
    assert out['space'] == ['one two three', 'four']
    assert out['deep'] == ['aa,', 'bb cc', 'dd']
