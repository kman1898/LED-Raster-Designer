"""The binder's map bitmaps: 300 px/in, each sent whichever way is smaller.

A gradient show's binder posted 253 MB of PNG maps at 400 px/in (owner,
2026-11-03, "auto at 300 dpi"). Every map bitmap now prints at 300 px/in
(app-binder.js MAP_DPI; an ARCH sheet keeps its own 200) and goes either
as one lossless PNG or as a SPLIT PAIR at the same rect - the cabinet
fills alone as a JPEG, everything drawn over them (borders, runs, discs,
tags, names) as a transparent PNG laid on top - whichever is smaller.
A gradient's fills are where PNG costs a dozen times a JPEG; a flat
show's PNG stays the smaller and goes as before.

The pair is tried only where painting every fill first cannot change
what the map shows (_bMapSplitBlocker, _bInkUnderMap): an image or text
layer under a screen, more than one screen on a Power or Data map, a
screen group or two overlapping screens on the show map, overlapping
cabinets, a hidden cabinet's ghost on an unclipped sheet, or ink already
on the page under the map all keep it one PNG.

The show here is synthetic: GRAD, 8 x 4 cabinets with a three-stop
gradient, and FLAT, the same wall in the plain checkerboard, side by side.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_binder_map_bitmaps.py -n 4 --dist loadfile
"""

import base64
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Page units are 200 per inch; the maps print at 300.
PX_PER_IN, MAP_DPI = 200, 300

SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const add = (name, offset_x) => j('POST', '/api/layer/add', {name, columns: 8, rows: 4,
        cabinet_width: 200, cabinet_height: 200, powerVoltage: 208, powerAmperage: 12.5, panelWatts: 200,
        powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h', processorType: 'novastar-armor',
        offset_x});
    await add('GRAD', 0);
    await add('FLAT', 2000);
    const p = await j('GET', '/api/project');
    Object.assign(p.layers.find(l => l.name === 'GRAD'), {
        gradientEnabled: true, gradientType: 'linear', gradientScope: 'screen', gradientAngle: 30,
        gradientOpacity: 1, gradientBlend: 'normal',
        gradientStops: [{pos: 0, color: '#ff0000'}, {pos: 0.5, color: '#00ff88'}, {pos: 1, color: '#2200ff'}] });
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('map_bitmaps');
    app.renderLayers();
    window.canvasRenderer.render();
    return app.project.layers.map(l => [l.name, app.screenCircuits(l).length]);
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': False},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': False, 'hardware': False, 'wiring': True,
        'titleBlock': True}

# Every sheet of the set: its title, its image ops with their bitmaps, and
# the map decisions its paint logged. `setup` runs first and `undo` after,
# both in the page, so a case can bend the project and put it back.
SHEETS_JS = """async ([opts, setup, undo, only]) => {
    const app = window.app;
    const L = (n) => app.project.layers.find(l => l.name === n);
    const ctx = {};
    if (setup) await (new Function('app', 'L', 'ctx', 'return (async () => {' + setup + '})()'))(app, L, ctx);
    try {
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => {
            if (only && !only.includes(p.title)) return;
            const r = app.renderBinderPage(opts, i);
            out.push({ title: p.title, kind: p.kind, mapBitmaps: r.mapBitmaps, wiring: r.wiring, map: r.map,
                       mapTexts: r.mapTexts,
                       images: r.record.ops.filter(o => o.op === 'image')
                           .map(o => ({ x: o.x, y: o.y, w: o.w, h: o.h, data: r.record.images[o.id] })) });
        });
        return out;
    } finally {
        if (undo) await (new Function('app', 'L', 'ctx', 'return (async () => {' + undo + '})()'))(app, L, ctx);
    }
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    seeded = pg.evaluate(SEED_JS)
    assert seeded == [['GRAD', 4], ['FLAT', 4]], seeded
    yield pg, errors
    context.close()


def _sheets(pg, opts=None, setup='', undo='', only=None):
    return pg.evaluate(SHEETS_JS, [opts or OPTS, setup, undo, only])


def _by_title(sheets):
    return {s['title']: s for s in sheets}


def _decode(data):
    from PIL import Image
    head, b64 = data.split(',', 1)
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    img.load()
    return head, img


GRAD_POWER, FLAT_POWER = 'GRAD - Power - Front View', 'FLAT - Power - Front View'
GRAD_WIRING = 'GRAD - Power Wiring'


def test_a_gradient_map_goes_as_a_split_pair_and_a_flat_map_as_one_png(page):
    """GRAD's maps - its power sheet, its wiring sheet, and the overview,
    which carries it - go as the split pair: a JPEG of the fills, then a
    PNG over it at the very same rect, together far smaller than the one
    PNG would be. FLAT's maps stay one PNG: there the PNG is the smaller,
    and nothing blocked the pair - it lost on size."""
    pg, errors = page
    sheets = _by_title(_sheets(pg))
    assert set(sheets) == {'Overview', GRAD_POWER, GRAD_WIRING, FLAT_POWER, 'FLAT - Power Wiring'}, list(sheets)
    for title in ('Overview', GRAD_POWER, GRAD_WIRING):
        s = sheets[title]
        assert len(s['images']) == 2, (title, [i['data'][:30] for i in s['images']])
        under, over = s['images']
        assert under['data'].startswith('data:image/jpeg;base64,'), title
        assert over['data'].startswith('data:image/png;base64,'), title
        assert {k: under[k] for k in 'xywh'} == {k: over[k] for k in 'xywh'}, (title, under, over)
        [log] = s['mapBitmaps']
        assert log['split'] and log['blocked'] is None, (title, log)
        assert log['pair'] == len(under['data']) + len(over['data']), (title, log)
        assert log['pair'] * 5 < log['png'], ('the pair should be far smaller', title, log)
        _h, jpg = _decode(under['data'])
        _h, png = _decode(over['data'])
        assert jpg.format == 'JPEG' and jpg.mode == 'RGB', (title, jpg.mode)
        assert png.format == 'PNG' and png.mode == 'RGBA', (title, png.mode)
        assert jpg.size == png.size, (title, jpg.size, png.size)
    for title in (FLAT_POWER, 'FLAT - Power Wiring'):
        s = sheets[title]
        assert len(s['images']) == 1 and s['images'][0]['data'].startswith('data:image/png;base64,'), title
        [log] = s['mapBitmaps']
        assert not log['split'] and log['blocked'] is None, (title, log)
        assert log['png'] == len(s['images'][0]['data']) and log['png'] <= log['pair'], (title, log)
    assert not errors, errors


def test_every_map_bitmap_prints_at_300_dpi_and_an_arch_sheet_at_its_own_200(page):
    """A map bitmap's pixels are its rect on the page at 300 px/in (one
    page unit is 1/200 in): the map sheets, the wiring sheets and the
    overview, PNG and JPEG alike. The rect itself is where it always was.
    On an ARCH D sheet - painted at 1x for its size - the maps stay at
    200 px/in rather than grow."""
    pg, _ = page
    for opts, dpi in ((OPTS, MAP_DPI), (dict(OPTS, sheet='archd'), PX_PER_IN)):
        for s in _sheets(pg, opts):
            assert s['images'], s['title']
            for im in s['images']:
                _h, img = _decode(im['data'])
                k = dpi / PX_PER_IN
                assert abs(img.size[0] - im['w'] * k) <= 1 and abs(img.size[1] - im['h'] * k) <= 1, \
                    (opts['sheet'], s['title'], img.size, im)


FORCE_ONE_PNG = "ctx.was = app._bMapSplitBlocker; app._bMapSplitBlocker = () => 'forced';"
UNFORCE = "delete app._bMapSplitBlocker;"


def test_the_split_pair_composites_back_to_the_map(page):
    """The JPEG with its PNG laid over it is the map the one PNG carries:
    the same sheet painted with the pair held back gives the PNG, and the
    two agree everywhere but a scatter of JPEG noise in the fills and the
    anti-aliased edges. A layer painted out of order would show as whole
    shapes off - discs, runs or tags missing or doubled."""
    from PIL import Image, ImageChops
    pg, _ = page
    split = _by_title(_sheets(pg, only=[GRAD_POWER, 'Overview']))
    single = _by_title(_sheets(pg, setup=FORCE_ONE_PNG, undo=UNFORCE, only=[GRAD_POWER, 'Overview']))
    for title, matte in ((GRAD_POWER, (255, 255, 255)), ('Overview', (244, 244, 244))):
        [log] = single[title]['mapBitmaps']
        assert log == {'split': False, 'blocked': 'forced', 'png': log['png'], 'pair': None}, log
        _h, ref = _decode(single[title]['images'][0]['data'])
        under, over = (_decode(i['data'])[1] for i in split[title]['images'])
        want = Image.new('RGB', ref.size, matte)
        want.paste(ref.convert('RGB'), (0, 0), ref)
        got = under.convert('RGB')
        got.paste(over.convert('RGB'), (0, 0), over)
        diff = ImageChops.difference(want, got).convert('L')
        hist = diff.histogram()
        n = ref.size[0] * ref.size[1]
        off = sum(hist[48:]) / n
        mean = sum(v * c for v, c in enumerate(hist)) / n
        assert off < 0.005 and mean < 2.0, (title, f'{off:.4%} of pixels off by 48+', f'mean {mean:.2f}')
        # and the overlay is not a second copy of the map: it leaves the
        # cabinets' insides clear
        alpha = over.getchannel('A').histogram()
        assert alpha[0] / n > 0.3, (title, alpha[0] / n)


def test_the_stage_passes_leave_what_the_sheet_read_off_the_map_alone(page):
    """The pair takes two more renders of the map. They are quiet: the
    wiring sheet's discs, the map's lettering and its place read the same
    whether the pair went or was held back, so a second paint of the discs
    never doubles the wiring sheet's seats or moves a run."""
    pg, _ = page
    split = _by_title(_sheets(pg, only=[GRAD_POWER, GRAD_WIRING]))
    single = _by_title(_sheets(pg, setup=FORCE_ONE_PNG, undo=UNFORCE, only=[GRAD_POWER, GRAD_WIRING]))
    for title in (GRAD_POWER, GRAD_WIRING):
        assert split[title]['mapBitmaps'][0]['split'] and not single[title]['mapBitmaps'][0]['split']
        for key in ('wiring', 'map', 'mapTexts'):
            assert split[title][key] == single[title][key], (title, key)
    assert split[GRAD_WIRING]['wiring'], 'the wiring sheet logs its discs'


def _blocked(sheets):
    return {s['title']: [(m['split'], m['blocked']) for m in s['mapBitmaps']] for s in sheets}


def test_a_text_layer_under_a_screen_keeps_the_overview_one_png(page):
    """A text layer painted before a screen sits under its cabinets. Split,
    every fill would go under it instead - so the overview stays one PNG.
    The same layer moved above every screen lets the pair go again."""
    pg, _ = page
    setup = """
        const t = await (await fetch('/api/layer/add-text', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'NOTE', textContent: 'UNDER', offset_x: 400, offset_y: 200,
                                  textWidth: 600, textHeight: 200})})).json();
        ctx.id = t.id;
        app.project.layers.unshift(t);
    """
    undo = """
        app.project.layers = app.project.layers.filter(l => l.id !== ctx.id);
        await fetch('/api/layer/' + ctx.id, {method: 'DELETE'});
    """
    under = _blocked(_sheets(pg, setup=setup, undo=undo, only=['Overview', GRAD_POWER]))
    assert under['Overview'] == [(False, 'an image or text layer under a screen')], under
    # the screen's own sheet shows the screen alone: nothing under it there
    assert under[GRAD_POWER] == [(True, None)], under
    over = _blocked(_sheets(pg, setup=setup.replace('layers.unshift(t)', 'layers.push(t)'), undo=undo,
                            only=['Overview']))
    assert over['Overview'] == [(True, None)], over


def test_overlapping_screens_keep_the_overview_one_png(page):
    """FLAT pulled over GRAD on the show: the upper screen's fills cover the
    lower one's borders and lettering, so the overview stays one PNG. Each
    screen's own sheet still splits as it would."""
    pg, _ = page
    out = _blocked(_sheets(pg, setup="L('FLAT').showOffsetX = 800;", undo="delete L('FLAT').showOffsetX;",
                           only=['Overview', GRAD_POWER]))
    assert out == {'Overview': [(False, 'two screens overlap')], GRAD_POWER: [(True, None)]}, out


def test_a_screen_group_keeps_its_sheets_and_the_overview_one_png(page):
    """GRAD and FLAT grouped: the group's own sheets carry two screens,
    whose runs, discs and tags are painted before the next member's fills,
    and the overview carries the group's one label across the wall - every
    one of those maps stays one PNG."""
    pg, _ = page
    setup = """
        app.project.groups = [{id: 'gT', name: 'PAIR', layer_ids: [L('GRAD').id, L('FLAT').id], routeDataAsOne: false}];
        L('GRAD').group_id = 'gT'; L('FLAT').group_id = 'gT';
    """
    undo = "app.project.groups = []; delete L('GRAD').group_id; delete L('FLAT').group_id;"
    out = _blocked(_sheets(pg, setup=setup, undo=undo))
    assert out['Overview'] == [(False, 'a screen group')], out
    maps = [m for t, ms in out.items() if t != 'Overview' for m in ms]
    assert maps and all(not split for split, _why in maps), out
    assert {why for _split, why in maps} <= {'more than one screen', 'a group member sheet'}, out


def test_a_hidden_cabinet_keeps_its_screens_sheets_one_png(page):
    """A hidden cabinet draws a dashed ghost on its edge. A screen's own
    sheets paint without the per-cabinet clip, so half that line falls on
    the neighbour painted next and is covered by its fill - split, it
    would not be. Those sheets stay one PNG; the overview, which clips
    every cabinet to itself, still splits."""
    pg, _ = page
    setup = "L('GRAD').panels[9].hidden = true;"
    undo = "delete L('GRAD').panels[9].hidden;"
    out = _blocked(_sheets(pg, setup=setup, undo=undo, only=['Overview', GRAD_POWER, GRAD_WIRING]))
    assert out == {'Overview': [(True, None)], GRAD_POWER: [(False, 'a hidden cabinet')],
                   GRAD_WIRING: [(False, 'a hidden cabinet')]}, out


def test_overlapping_cabinets_keep_the_map_one_png(page):
    """Two of GRAD's cabinets moved onto each other: the later one's fill
    covers the earlier one's border. Every map that carries GRAD stays one
    PNG; FLAT's own sheet is untouched by it."""
    pg, _ = page
    setup = "ctx.x = L('GRAD').panels[1].x; L('GRAD').panels[1].x -= 100;"
    undo = "L('GRAD').panels[1].x = ctx.x;"
    out = _blocked(_sheets(pg, setup=setup, undo=undo, only=['Overview', GRAD_POWER, FLAT_POWER]))
    assert out == {'Overview': [(False, 'two cabinets overlap')], GRAD_POWER: [(False, 'two cabinets overlap')],
                   FLAT_POWER: [(False, None)]}, out


def test_ink_already_under_the_map_keeps_it_one_png(page):
    """The JPEG is opaque. Anything the page carries under the map's rect
    before the map is laid - but a fill of the matte the JPEG is flattened
    onto, or what a later matte fill covers whole - would vanish under it,
    so _bInkUnderMap names it. A stroked rect is its edges, not its inside;
    text is measured."""
    pg, _ = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const book = { realCtx: { getTransform: () => ({ a: 2, b: 0, c: 0, d: 2, e: 0, f: 0 }) }, scale: 2 };
        const rect = [100, 100, 400, 200];
        const white = { op: 'rect', x: 0, y: 0, w: 3400, h: 2200, fill: '#ffffff' };
        const run = (ops, matte = '#ffffff', r = rect) => app._bInkUnderMap({ ...book, page: { ops } }, r, matte);
        const text = (t, x, y, align = 'left', rotate = 0) => ({ op: 'text', text: t, x, y, size: 24, weight: 400,
            align, baseline: 'alphabetic', color: '#111111', rotate });
        return {
            sheetWhite: run([white]),
            border: run([white, { op: 'rect', x: 50, y: 50, w: 3300, h: 2100, stroke: '#111111', width: 3 }]),
            edgeAcross: run([{ op: 'rect', x: 50, y: 150, w: 600, h: 400, stroke: '#111111', width: 3 }]),
            greyUnder: run([white, { op: 'rect', x: 150, y: 150, w: 20, h: 20, fill: '#cccccc' }]),
            coveredByMatte: run([{ op: 'rect', x: 150, y: 150, w: 20, h: 20, fill: '#cccccc' },
                                 { op: 'rect', x: 100, y: 100, w: 400, h: 200, fill: '#f4f4f4' }], '#f4f4f4'),
            whiteOnGreyMap: run([white], '#f4f4f4'),
            lineUnder: run([{ op: 'line', points: [[0, 120], [90, 120], [90, 400]], width: 30, dash: [], stroke: '#111111' }]),
            lineBeside: run([{ op: 'line', points: [[0, 120], [80, 120]], width: 4, dash: [], stroke: '#111111' }]),
            textBeside: run([text('REVISIONS', 520, 150)]),
            textRightAligned: run([text('REVISIONS', 560, 150, 'right')]),
            textTurned: run([text('K1', 90, 200, 'center', Math.PI / 2)]),
            imageUnder: run([{ op: 'image', id: 'img1', x: 300, y: 250, w: 400, h: 100 }]),
            scaledContext: app._bInkUnderMap({ realCtx: { getTransform: () => ({ a: 4, b: 0, c: 0, d: 4, e: 0, f: 0 }) },
                scale: 2, page: { ops: [{ op: 'rect', x: 700, y: 400, w: 10, h: 10, fill: '#cccccc' }] } }, rect, '#ffffff'),
            scaledContextMiss: run([{ op: 'rect', x: 700, y: 400, w: 10, h: 10, fill: '#cccccc' }]),
        };
    }""")
    hit = 'ink under the map'
    assert out == {'sheetWhite': None, 'border': None, 'edgeAcross': hit, 'greyUnder': hit,
                   'coveredByMatte': None, 'whiteOnGreyMap': hit, 'lineUnder': hit, 'lineBeside': None,
                   'textBeside': None, 'textRightAligned': hit, 'textTurned': hit, 'imageUnder': hit,
                   'scaledContext': hit, 'scaledContextMiss': None}, out


def test_a_gradient_show_binder_stays_small(page):
    """The size this is for: a gradient show's whole set - overview, power
    and wiring sheets - carries a fraction of what its maps cost as PNGs,
    and under a fixed budget. At 400 px/in as PNGs this show's maps were
    about 50 MB; as shipped here they are near 1.5 MB."""
    pg, _ = page
    sheets = _sheets(pg)
    total = sum(len(i['data']) for s in sheets for i in s['images'])
    as_png = sum(m['png'] for s in sheets for m in s['mapBitmaps'])
    assert total < 3_000_000, total
    assert total * 6 < as_png, (total, as_png)
