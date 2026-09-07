"""The binder: the show's power and data maps bound into one PDF.

Type A of binder-mock.html, as the user picked it (2026-09-06): the
screen's map across the top half of a landscape letter page, rulers around
it (numbering "2"), a bracket per BREAKOUT outside the wall with its home
run ("Breakout", never "Box", never "Multi" - 2026-09-07: "maybe we call
them breakouts?"; the home run said once per breakout, in a band row over
its circuits), then Circuits · Cables · Facts, and a Gangs table only when
the screen has 2fers / 3fers. Colour and Printer palettes - the renderer's
printerMode (canvas.js) draws greys, black runs told apart by a dash per
circuit, white discs. Pages: cover, a pull page per position, each screen's
power and data pages, a page per distro and per processor, the show-wide
pull list; a single screen exports alone from the canvas's right-click.

The beta.20 notes (2026-09-07): the map carries no screen-name plate (the
header names the screen, and the plate sat over the circuit labels); a
band never sits at the foot of a column without two of its rows, and a
band whose rows run on across a break is repeated with "(cont.)"; the data
page's BACKUP cell is the return end the tray states ("SR-1R · H9 slot 2 ·
1"), its Processor line names the unit once, and Redundancy reads the
bar's own words ("Per card"). The 2026-09-07 rulings: the Ports table
reads PORT · PRIMARY · BACKUP · PANELS · PX · HOME RUN, PRIMARY the sending
card the port lands on ("H9 SR · 1") - or, where a breakout box delivers
it, the BOX instead ("CVT4K-S SR · 3") under a band naming the box, its
trunk, its sockets and its fiber ("12 Tac Fiber 250'", else "no fiber
length"); the Facts say the port count alone ("we dont need port max");
the processor page lists every box with its fiber.

The pages are laid out on the client (app-binder.js) from buildPullList
and the canvas renderer's own drawing, so the assertions here read the
texts a page draws, the dashes its map sets and the pixels it leaves.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15797 python3 -m pytest tests/test_binder.py -v --browser chromium
"""

import base64
import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH_FIXTURE = os.environ.get('LRD_PULL_SMOKE_JSON') or os.path.join(
    '/private/tmp/claude-501',
    '-Users-mattknotts-Nextcloud-LED-LED-Wall-Tech-Raster-Software-LED-Raster-Designer',
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad', 'experts-only.json')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── served pieces and the route ───────────────────────────────────────────

def test_the_menu_items_the_format_option_and_the_section_are_served(client):
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'data-action="export-binder"[^>]*data-label="Export Binder"', html)
    assert re.search(r'class="menu-option screen-export-only" data-action="export-screen-binder"', html)
    assert '<option value="binder">Binder (PDF)</option>' in html
    assert 'id="export-binder-section"' in html
    for field in ('scope', 'colour', 'printer', 'side-power', 'side-data', 'side-both',
                  'cover', 'pull', 'hardware', 'engineer', 'rev'):
        assert f'id="export-binder-{field}"' in html, field
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-binder.js';" in main_js
    # the binder's own strings say circuits and breakout - never tails, never Multi
    binder_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-binder.js')).read()
    code = '\n'.join(l for l in binder_js.splitlines() if not l.strip().startswith('//'))
    literals = re.findall(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", code)
    assert not [l for l in literals if 'tails' in l], [l for l in literals if 'tails' in l]
    # "Multi" may name a CABLE (the GEAR LIST's word); it never names the breakout
    assert not [l for l in literals if 'Multi' in l], [l for l in literals if 'Multi' in l]


def _png(color=(255, 0, 0, 255), size=(20, 10)):
    from PIL import Image
    img = Image.new('RGBA', size, color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def test_the_pdf_route_takes_letter_pages_and_no_stamped_label(client_with_layer):
    """The binder asks for real letter-landscape pages in points and no view
    label on top (its pages carry their own headers); every other caller's
    request still comes out the way it always did."""
    resp = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Show', 'labels': False,
        'images': [{'name': f'p{i}', 'data': _png(), 'width': 2200, 'height': 1700,
                    'page_size': [792, 612]} for i in range(3)],
    })
    assert resp.status_code == 200 and resp.data[:5] == b'%PDF-'
    pdf = resp.data
    assert len(re.findall(rb'/Type\s*/Page[^s]', pdf)) == 3
    assert re.search(rb'/MediaBox\s*\[\s*0\s+0\s+792\s+612\s*\]', pdf)
    assert b'Helvetica-Bold' not in pdf
    # the old shape: page = image pixels, label stamped
    old = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Show',
        'images': [{'name': 'Pixel Map', 'data': _png(), 'width': 100, 'height': 100}],
    })
    assert old.status_code == 200
    assert re.search(rb'/MediaBox\s*\[\s*0\s+0\s+100\s+100\s*\]', old.data)
    assert b'Helvetica-Bold' in old.data


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Two positions: SR Beach (WALL-A and WALL-B, 4 x 3 of 200 px cabinets) and
# the loose CENTER (3 x 5 Edison wall that gangs its first two columns
# through a 2fer). One distro SR: WALL-A's box on number 1 at 125', WALL-B's
# on 2 at 100'. WALL-A's circuits 1 and 2 carry 10' cables and its cable
# tags are ON; WALL-B's circuit 1 carries 6' with the tags off. One H9 with
# a 16 x RJ45 card named SR holding every screen's port.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({name: 'WALL-A', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor'});
    await add({name: 'WALL-B', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 250,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 900});
    await add({name: 'CENTER', columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 110, powerAmperage: 15, panelWatts: 100,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               powerSplitters: {enabled: true, maxWays: 2, manual: {merge: [], split: []}},
               processorType: 'novastar-armor', offset_x: 1800});
    let p = await j('GET', '/api/project');
    const A = p.layers.find(l => l.name === 'WALL-A');
    const B = p.layers.find(l => l.name === 'WALL-B');
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [A.id, B.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('binder_setup');
    const a = app.project.layers.find(l => l.id === A.id);
    const b = app.project.layers.find(l => l.id === B.id);
    const c = app.project.layers.find(l => l.name === 'CENTER');
    app.selectLayer(a);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 1); app.setSocaLength(a, 1, '125');
    app.setSocaDistro(b, 1, d.id); app.setSocaNumber(b, 1, 2); app.setSocaLength(b, 1, '100');
    app.setCircuitCable(a, 1, {ft: 10, connector: null});
    app.setCircuitCable(a, 2, {ft: 10, connector: null});
    app.setCircuitCable(b, 1, {ft: 6, connector: null});
    a.showPowerCableTags = true;
    b.showPowerCableTags = false;
    await app.refreshProcessors();
    for (const l of [a, b, c]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Binder Seed');
    return { a: a.id, b: b.id, c: c.id, distroId: d.id, procId: pid, cardId,
             centerRunIds: app.screenCircuits(c).map(x => x.runIds || [x.num]),
             aCircuits: app.screenCircuits(a).length };
}"""

SHOW = """{ palette: 'colour', sides: {power: true, data: true}, scope: {kind: 'show'},
            cover: true, pull: true, hardware: true }"""


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
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['centerRunIds'] == [[1, 2], [3]], f'fixture: CENTER must gang columns 1+2: {ids}'
    assert ids['aCircuits'] == 2, f'fixture: WALL-A is two circuits: {ids}'
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _plan(pg, opts_js):
    return pg.evaluate("() => window.app.planBinder(%s).map(p => [p.kind, p.title])" % opts_js)


RENDER_JS = """([opts, title]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const r = app.renderBinderPage(opts, idx);
    const c = r.canvas, ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let coloured = 0, samples = 0;
    for (let i = 0; i < d.length; i += 4 * 61) {
        samples++;
        const R = d[i], G = d[i + 1], B = d[i + 2];
        if (Math.abs(R - G) > 10 || Math.abs(G - B) > 10 || Math.abs(R - B) > 10) coloured++;
    }
    return { texts: r.texts, textInfo: r.textInfo, mapTexts: r.mapTexts, dashes: r.dashes,
             coloured, samples, pages: r.pages, index: idx, width: c.width, height: c.height };
}"""


def _render(pg, opts_js, title):
    out = pg.evaluate("(t) => (%s)([%s, t])" % (RENDER_JS, opts_js), title)
    assert 'missing' not in out, out
    return out


def test_the_pages_come_in_order_on_two_positions(page):
    pg, ids = page
    plan = _plan(pg, SHOW)
    assert plan == [
        ['cover', 'Cover'],
        ['pull', 'SR Beach - Pull'],
        ['power', 'WALL-A - Power'], ['data', 'WALL-A - Data'],
        ['power', 'WALL-B - Power'], ['data', 'WALL-B - Data'],
        ['pull', 'CENTER - Pull'],
        ['power', 'CENTER - Power'], ['data', 'CENTER - Data'],
        ['distro', 'SR - Distro'],
        ['processor', 'H9 - Processor'],
        ['totals', 'Pull list - all positions'],
    ]
    assert ids['errors'] == []
    # power only, no extras: just the maps
    only = _plan(pg, SHOW.replace("data: true", "data: false")
                 .replace("cover: true, pull: true, hardware: true", "cover: false, pull: false, hardware: false"))
    assert only == [['power', 'WALL-A - Power'], ['power', 'WALL-B - Power'], ['power', 'CENTER - Power']]


def test_the_power_page_says_home_run_once_per_box_and_never_multi(page):
    pg, ids = page
    out = _render(pg, SHOW, 'WALL-A - Power')
    texts = out['texts']
    assert out['width'] == 2200 and out['height'] == 1700
    assert texts[0] == 'UNTITLED PROJECT · POWER' or texts[0].endswith('· POWER')
    assert texts[1] == 'WALL-A · SR Beach · page 3 of 12'
    bands = [t for t in texts if 'home run' in t]
    assert bands == ["SR1 · Soca 208 · 125' home run · 2 circuits"], texts
    # Multi is a cable row, never a heading and never the breakout's name
    assert not any(t.strip() == 'MULTI' for t in texts), [t for t in texts if t.strip() == 'MULTI']
    assert not any('Multi' in b for b in bands), bands
    assert not any('tails' in t.lower() for t in texts)
    # the bracket outside the wall carries the box and its home run once
    assert texts.count("SR1 · 125'") == 1
    # the circuit rows, the cable typed on each, the cables table, the facts
    assert 'SR1-1' in texts and 'SR1-2' in texts
    assert texts.count("10' True1") >= 2
    assert 'CABLES THIS SCREEN' in texts and 'FACTS' in texts
    assert 'Multi' in texts and "125'" in texts      # the breakout's cable, in the GEAR LIST's word
    assert 'Tru-1 Breakout' in texts
    assert 'GANGS' not in texts


def test_gangs_are_listed_only_where_a_screen_has_them(page):
    pg, ids = page
    plain = _render(pg, SHOW, 'WALL-B - Power')['texts']
    assert 'GANGS' not in plain and '2fer' not in plain
    ganged = _render(pg, SHOW, 'CENTER - Power')['texts']
    assert 'GANGS' in ganged
    i = ganged.index('GANGS')
    assert ganged[i:i + 7] == ['GANGS', 'CIRCUIT', 'GANG', 'AMPS', ganged[i + 4], '2fer', ganged[i + 6]]
    assert ganged[i + 4].endswith('1') or ganged[i + 4]   # the shared circuit's label
    assert 'Edison 2fer' in ganged


def test_the_rulers_number_every_fifth_column_and_the_ends_in_bold(page):
    pg, ids = page
    out = _render(pg, SHOW, 'CENTER - Power')
    rulers = [t for t in out['textInfo'] if t['size'] == 22 and t['weight'] == 700]
    assert [t['text'] for t in rulers] == ['1', '3', '1', '2', '3', '4', '5'], rulers
    assert all(t['weight'] == 700 for t in rulers)


def test_the_printer_page_has_no_colour_and_a_dash_per_circuit(page):
    pg, ids = page
    printer = SHOW.replace("palette: 'colour'", "palette: 'printer'")
    out = _render(pg, printer, 'WALL-A - Power')
    assert out['coloured'] == 0, f'{out["coloured"]} of {out["samples"]} samples carry colour'
    patterns = sorted({tuple(d) for d in out['dashes']})
    non_solid = [p for p in patterns if p]
    # two circuits: the first solid, the second its own dash
    assert len(non_solid) == 1 and non_solid[0][0] > 0, patterns
    assert () in patterns
    # the same page in colour: colour on the wall, every run solid
    colour = _render(pg, SHOW, 'WALL-A - Power')
    assert colour['coloured'] > 0
    assert not [d for d in colour['dashes'] if d]
    # the printer band is drawn as a rule, the text the same
    assert [t for t in out['texts'] if 'home run' in t] == [t for t in colour['texts'] if 'home run' in t]


def test_cable_tags_follow_the_screens_switch(page):
    pg, ids = page
    on = _render(pg, SHOW, 'WALL-A - Power')['mapTexts']
    assert "10' True1" in on and 'SR1-1' in on
    off = _render(pg, SHOW, 'WALL-B - Power')['mapTexts']
    assert 'SR2-1' in off and "6' True1" not in off
    # flip WALL-A off, and the tag leaves the map
    pg.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).showPowerCableTags = false; }", ids['a'])
    try:
        flipped = _render(pg, SHOW, 'WALL-A - Power')['mapTexts']
        assert "10' True1" not in flipped and 'SR1-1' in flipped
    finally:
        pg.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).showPowerCableTags = true; }", ids['a'])


def test_a_single_screen_scope_yields_only_that_screens_pages(page):
    pg, ids = page
    one = _plan(pg, """{ palette: 'colour', sides: {power: true, data: true},
                         scope: {kind: 'screen', layerId: '%s'}, cover: false, pull: false, hardware: false }""" % ids['b'])
    assert one == [['power', 'WALL-B - Power'], ['data', 'WALL-B - Data']]
    ticked = _plan(pg, """{ palette: 'colour', sides: {power: true, data: false},
                            scope: {kind: 'screen', layerId: '%s'}, cover: false, pull: true, hardware: false }""" % ids['b'])
    assert ticked == [['pull', 'SR Beach - Pull'], ['power', 'WALL-B - Power'], ['totals', 'Pull list - all positions']]
    # the dialog: the canvas's right-click presets the scope and unticks the extras
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        app.openScreenBinderExport(layer);
        const v = (i) => document.getElementById(i).value;
        const on = (i) => document.getElementById(i).checked;
        const vis = (i) => document.getElementById(i).style.display !== 'none';
        const out = { format: v('export-format'), scope: v('export-binder-scope'),
                      cover: on('export-binder-cover'), pull: on('export-binder-pull'), hardware: on('export-binder-hardware'),
                      section: vis('export-binder-section'), views: vis('export-views-section'),
                      canvases: vis('export-canvases-section'), preview: document.getElementById('export-preview').textContent,
                      opts: app.readBinderOptions() };
        document.getElementById('export-cancel').click();
        return out;
    }""", ids['b'])
    assert out['format'] == 'binder' and out['scope'] == f"screen:{ids['b']}"
    assert (out['cover'], out['pull'], out['hardware']) == (False, False, False)
    assert out['section'] and not out['views'] and not out['canvases']
    assert out['preview'].endswith('WALL-B - binder.pdf')
    assert out['opts']['scope'] == {'kind': 'screen', 'layerId': str(ids['b'])}
    # the menu item shows for a screen under the cursor / selected, never on the dock
    menu = pg.evaluate("""() => {
        const app = window.app;
        const cr = window.canvasRenderer;
        const r = cr.canvas.getBoundingClientRect();
        app.showContextMenu(r.left + r.width / 2, r.top + r.height / 2);
        const el = document.querySelector('.menu-option.screen-export-only');
        const shown = el.style.display !== 'none';
        app.hideContextMenu();
        return { shown, label: el.textContent, layer: app._binderMenuLayer && app._binderMenuLayer.name };
    }""")
    assert menu['shown'] and menu['label'].startswith('Export this screen')
    assert menu['layer'] in ('WALL-A', 'WALL-B', 'CENTER')


def test_the_pdf_route_receives_one_image_per_page(page):
    pg, ids = page
    out = pg.evaluate("""async (opts) => {
        const app = window.app;
        const realFetch = window.fetch;
        const saved = app.saveBlobWithPicker;
        const seen = { posts: [], saved: null };
        window.fetch = async (url, init) => {
            if (String(url).includes('/api/export/pdf-from-images')) {
                seen.posts.push(JSON.parse(init.body));
                return { ok: true, blob: async () => new Blob(['%PDF-fake'], {type: 'application/pdf'}) };
            }
            return realFetch(url, init);
        };
        app.saveBlobWithPicker = async (blob, filename, mime) => { seen.saved = { filename, mime, size: blob.size }; };
        // the dialog's state is what exportBinder reads
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        document.getElementById('export-binder-scope').value = 'show';
        document.getElementById('export-binder-scope').dispatchEvent(new Event('change'));
        document.getElementById('export-binder-printer').checked = true;
        try {
            const res = await app.exportBinder('Two Positions');
            const body = seen.posts[0];
            return { pages: res.pages, posts: seen.posts.length, n: body.images.length, labels: body.labels,
                     names: body.images.map(i => i.name), sizes: body.images.map(i => i.page_size),
                     dims: body.images.map(i => [i.width, i.height]),
                     png: body.images.every(i => i.data.startsWith('data:image/png;base64,')),
                     saved: seen.saved, plan: app.planBinder(app.readBinderOptions()).length };
        } finally {
            window.fetch = realFetch;
            app.saveBlobWithPicker = saved;
            document.getElementById('export-binder-colour').checked = true;
        }
    }""", None)
    assert out['posts'] == 1 and out['labels'] is False
    assert out['n'] == out['plan'] == out['pages'] == 12
    assert out['names'][0] == 'Cover' and out['names'][-1] == 'Pull list - all positions'
    assert out['sizes'] == [[792, 612]] * 12 and out['dims'] == [[2200, 1700]] * 12
    assert out['png']
    assert out['saved'] == {'filename': 'Two Positions - binder.pdf', 'mime': 'application/pdf', 'size': 9}


# The whole-show options as JSON, for evaluate() calls that take them as data.
_SHOW_JSON = ('{"palette": "colour", "sides": {"power": true, "data": true}, "scope": {"kind": "show"},'
              ' "cover": true, "pull": true, "hardware": true}')
BOX_WORD = re.compile(r'\b(box|boxes)\b', re.I)


def test_the_map_carries_no_screen_name_plate_but_the_export_still_does(page):
    """"the main label is over the circuits so that is bad": the binder's
    map draws no screen-name plate - the header names the screen - on the
    power and the data page alike, and the ordinary export (exportMode
    without the binder's flag) paints the name exactly as before."""
    pg, ids = page
    for title in ('WALL-A - Power', 'WALL-A - Data'):
        out = _render(pg, SHOW, title)
        assert 'WALL-A' not in out['mapTexts'], (title, out['mapTexts'])
        assert 'WALL-A' in out['texts'][1]                 # the header names it
        assert 'SR1-1' in out['mapTexts'] or 'SR-1' in out['mapTexts']
    # the same exportMode render with the binder's flag pinned off is the
    # ordinary export, and it paints the name
    export = pg.evaluate("""([opts, title]) => {
        const app = window.app, r = window.canvasRenderer;
        const idx = app.planBinder(opts).findIndex(p => p.title === title);
        Object.defineProperty(r, 'hideScreenNames', { get: () => false, set: () => {}, configurable: true });
        try {
            return { mapTexts: app.renderBinderPage(opts, idx).mapTexts };
        } finally {
            delete r.hideScreenNames;
            r.hideScreenNames = false;
        }
    }""", [json.loads(_SHOW_JSON), 'WALL-A - Power'])
    assert 'WALL-A' in export['mapTexts'], export['mapTexts'][:40]
    assert pg.evaluate("() => window.canvasRenderer.hideScreenNames") is False


def test_no_page_says_box(page):
    """The power side's word is breakout ("I dont like calling them boxes");
    no page text says box, save a data-side breakout box's own name."""
    pg, ids = page
    n = pg.evaluate("(o) => window.app.planBinder(o).length", json.loads(_SHOW_JSON))
    assert n == 12
    for idx in range(n):
        texts = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [json.loads(_SHOW_JSON), idx])
        boxy = [t for t in texts if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        assert not boxy, (idx, boxy)
    distro = _render(pg, SHOW, 'SR - Distro')['texts']
    i = distro.index('BREAKOUTS')
    assert distro[i + 1] == 'BREAKOUT' and 'SR 1' in distro and 'SR 2' in distro
    assert 'Breakouts' in distro and '2 breakouts' in distro


# The filler's line heights (app-binder.js): title, heading, band, row.
H4_H, TH_H, BAND_H, ROW_H = 46, 40, 46, 38


def test_a_band_never_ends_a_column_and_a_continued_band_says_cont(page):
    """"the first example the page gets cut off": the fixture's frame is
    exactly deep enough that the old filler laid BAND B at the foot of the
    first column with its rows in the next. Now a band moves with its first
    two rows, and the rows of BAND B that run past the second column's foot
    resume under "BAND B (cont.)"."""
    pg, ids = page
    bottom = H4_H + TH_H + BAND_H + 5 * ROW_H + BAND_H      # BAND B fits, alone, at the foot
    out = pg.evaluate("""(bottom) => {
        const app = window.app;
        const c = document.createElement('canvas'); c.width = 2200; c.height = 1700;
        const ctx = c.getContext('2d');
        const book = { ctx, measureCtx: ctx, meta: { palette: 'colour' }, page: { painting: true },
                       log: { texts: [], textInfo: [], mapTexts: [], dashes: [] } };
        const rows = [];
        const add = (name, n) => { rows.push({ band: name }); for (let i = 1; i <= n; i++) rows.push({ cells: [`${name}-${i}`, 'x'] }); };
        add('BAND A', 5); add('BAND B', 7); add('BAND C', 3);
        const lines = app._bTableLines(book, { title: 'T', cols: [{ title: 'a', w: 1 }, { title: 'b', w: 1 }], rows });
        const seen = [];
        let pageNo = 0;
        lines.forEach(l => {
            const d = l.draw;
            l.draw = (cx, x, y, w, cont) => {
                seen.push({ page: pageNo, x, y, h: l.h, band: !!l.band, head: !!l.head, cont: !!cont, text: book.log.texts.length });
                d(cx, x, y, w, cont);
            };
        });
        const cols = [{ x: 0, w: 600 }, { x: 700, w: 600 }];
        app._bFlow(book, [{ lines }], { top: 0, bottom, cols }, () => { pageNo++; return { top: 0, bottom, cols }; });
        return { seen, texts: book.log.texts, pages: pageNo + 1 };
    }""", bottom)
    texts = out['texts']
    for e in out['seen']:
        e['t'] = texts[e['text']]
        assert e['y'] + e['h'] <= bottom, e
    columns = {}
    for e in out['seen']:
        columns.setdefault((e['page'], e['x']), []).append(e)
    for key, col in columns.items():
        col.sort(key=lambda e: e['y'])
        assert not col[-1]['band'], (key, [e['t'] for e in col])
        # a band is followed by two of its rows in its own column (or all it has)
        for i, e in enumerate(col):
            if e['band'] and not e['cont']:
                rest = [x['t'] for x in col[i + 1:i + 3]]
                assert len(rest) == 2 and all(r.startswith(e['t'] + '-') for r in rest), (key, e['t'], rest)
    seq = lambda key: [e['t'] for e in columns[key]]
    assert seq((0, 0)) == ['T', 'A', 'BAND A', 'BAND A-1', 'BAND A-2', 'BAND A-3', 'BAND A-4', 'BAND A-5']
    assert seq((0, 700)) == ['T (CONT.)', 'A', 'BAND B'] + [f'BAND B-{i}' for i in range(1, 7)]
    assert seq((1, 0)) == ['T (CONT.)', 'A', 'BAND B (cont.)', 'BAND B-7', 'BAND C', 'BAND C-1', 'BAND C-2', 'BAND C-3']
    assert out['pages'] == 2
    assert texts.count('BAND B (cont.)') == 1 and texts.count('T (CONT.)') == 2


def test_the_data_page_prints_the_return_end_and_the_processor_once(page):
    """Card SR backed 1:1 by a second (unnamed) card: the BACKUP cell is the
    return end the tray states - the backup port's label and where it lands,
    "SR-1R · H9 slot 2 · 1" - never "slot 2 1"; the Processor line names the
    unit once ("H9", not "H9 · H9"); Redundancy reads the bar ("Per card")."""
    pg, ids = page
    backup_id = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        let st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const backupId = st.processors[0].slots[1].card.id;
        await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
        st = await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return backupId;
    }""", ids)
    try:
        out = _render(pg, SHOW, 'WALL-A - Data')
        texts = out['texts']
        i = texts.index('H9 SR · H_16xRJ45+2xfiber · 16 ports')
        assert texts[texts.index('PORTS') + 1:texts.index('PORTS') + 7] == \
            ['PORT', 'PRIMARY', 'BACKUP', 'PANELS', 'PX', 'HOME RUN']
        rows = []
        j = i + 1
        while j + 5 < len(texts) and re.fullmatch(r'SR-\d+', texts[j]):
            rows.append(texts[j:j + 6]); j += 6
        assert rows, texts[i:i + 20]
        for label, primary, backup, _panels, _px, _home in rows:
            # the sending card the primary lands on, and the one the backup does
            assert re.fullmatch(r'H9 SR · \d+', primary), (label, primary)
            socket = primary.rsplit(' · ', 1)[-1]
            assert backup == f'{label}R · H9 slot 2 · {socket}', (label, backup)
            assert f'{label}R' in out['mapTexts'], (label, out['mapTexts'])
        assert not [t for t in texts if t.startswith('slot ') or t.endswith('…')]
        # the Facts say how many ports, never a px-per-port ceiling
        assert texts[texts.index('Ports') + 1] == '1 port' and not [t for t in texts if 'px/port' in t]
        assert texts[texts.index('Processor') + 1] == 'H9' and 'H9 · H9' not in texts
        assert texts[texts.index('Redundancy') + 1] == 'Per card'
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        assert proc[proc.index('Redundancy') + 1] == 'Per card'
        assert not [t for t in proc if BOX_WORD.search(t)]
    finally:
        pg.evaluate("""async ([ids, backupId]) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
            await app.refreshProcessors();
            await app.refreshPortAssignment();
            app.renderLayers();
        }""", [ids, backup_id])
    assert ids['errors'] == []


def test_a_box_delivering_the_port_is_listed_instead_of_the_card(page):
    """"if cvt's are used then we will list those instead of sending card":
    a CVT4K-S on card SR (both OPTs, all 16 sockets again) delivers WALL-A's
    port, so PRIMARY reads the box and its own socket ("CVT4K-S SR · 1"),
    the band is the box's - its trunk as the card's face prints it, its
    sockets, its fiber ("12 Tac Fiber 250'") or "no fiber length" - the
    Cables table and the processor page carry the fiber, and the box's
    paper title is model + typed name ("CVT4K-S SR"), the way a card is
    "H9 SR"."""
    pg, ids = page
    box_id = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`,
                           {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[0].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxId}`, {fiberType: '12 Tac Fiber', fiberFt: 250});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return boxId;
    }""", ids)
    try:
        out = _render(pg, SHOW, 'WALL-A - Data')
        texts = out['texts']
        band = "CVT4K-S A-B · OPT 1-2 · 16 ports · 12 Tac Fiber 250'"
        assert band in texts, texts
        i = texts.index(band)
        assert texts[i + 1:i + 4] == ['SR-1', 'CVT4K-S A-B · 1', '—'], texts[i:i + 8]
        assert not [t for t in texts if t.startswith('H9 SR ·')], 'the card is not listed where the box delivers'
        k = texts.index('CABLES THIS SCREEN')
        assert texts[k + 4:k + 7] == ['12 Tac Fiber', "250'", '1'], texts[k:k + 12]
        assert not [t for t in texts if t.endswith('…') or 'px/port' in t]
        # the box named: model + name, as the card reads model + name
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: 'SR'})});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
        texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
        assert "CVT4K-S SR · OPT 1-2 · 16 ports · 12 Tac Fiber 250'" in texts, texts
        assert 'CVT4K-S SR · 1' in texts
        # the processor page: the box under its card, with its fiber
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        b = proc.index('BREAKOUT BOXES')
        assert proc[b + 1:b + 6] == ['BREAKOUT BOX', 'CARD', 'TRUNK', 'PORTS', 'FIBER']
        assert proc[b + 6:b + 11] == ['CVT4K-S SR', 'SR', 'OPT 1-2', '16', "12 Tac Fiber 250'"], proc[b:b + 12]
        assert ['12 Tac Fiber', "250'", '1', 'CVT4K-S SR'] == proc[proc.index('PULL LIST') + 5:proc.index('PULL LIST') + 9]
        # no page says box, save the breakout box's own table
        for t in texts + proc:
            assert not (BOX_WORD.search(t) and 'breakout box' not in t.lower()), t
        # no fiber length: the band says so, the Cables table has no fiber row
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberFt: null})});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
        texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
        assert 'CVT4K-S SR · OPT 1-2 · 16 ports · no fiber length' in texts, texts
        assert '12 Tac Fiber' not in texts
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        assert proc[proc.index('BREAKOUT BOXES') + 10] == 'no fiber length'
        # the backup end lands on a box the same way: the second card's own
        # CVT4K-S (named BK) carries WALL-A's return, so the return label is
        # that box's own ("BK-1" - the mapped port's label, the tray's rule)
        # and BACKUP names the box and its socket
        backup = pg.evaluate("""async (ids) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            let st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
            const backupId = st.processors[0].slots[1].card.id;
            st = await j('POST', `/api/processors/${ids.procId}/cards/${backupId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
            const backupBox = st.processors[0].slots[1].card.cvts[0].id;
            await j('PUT', `/api/processors/${ids.procId}/cvts/${backupBox}`, {name: 'BK'});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
            return {backupId, backupBox};
        }""", ids)
        try:
            texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
            i = texts.index('SR-1')
            assert texts[i:i + 3] == ['SR-1', 'CVT4K-S SR · 1', 'BK-1 · CVT4K-S BK · 1'], texts[i:i + 6]
            assert not [t for t in texts if t.endswith('…')]
        finally:
            pg.evaluate("""async ([ids, b]) => {
                const app = window.app;
                const j = (method, url, body) => fetch(url, {method,
                    headers: {'Content-Type': 'application/json'},
                    body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
                await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null});
                await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
                await j('DELETE', `/api/processors/${ids.procId}/cvts/${b.backupBox}`);
                await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
            }""", [ids, backup])
    finally:
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'DELETE'});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
    after = _render(pg, SHOW, 'WALL-A - Data')['texts']
    assert 'H9 SR · H_16xRJ45+2xfiber · 16 ports' in after and 'H9 SR · 1' in after
    assert ids['errors'] == []


# ── the smoke: the user's own show ───────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only.json smoke fixture not present')
def test_smoke_experts_only(page):
    """The real show: SR - MAIN's 22 custom circuits on four boxes, SR -
    Return's six on box 5 with five 2fers, SL mirroring SR. 17 pages."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    plan = pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('binder_smoke');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return app.planBinder(%s).map(p => p.title);
    }""" % SHOW, project)
    assert plan == [
        'Cover',
        'SR - MAIN - Pull', 'SR - MAIN - Power', 'SR - MAIN - Data',
        'SR - Return - Pull', 'SR - Return - Power', 'SR - Return - Data',
        'SL - MAIN - Pull', 'SL - MAIN - Power', 'SL - MAIN - Data',
        'SL - Return - Pull', 'SL - Return - Power', 'SL - Return - Data',
        'SR - Distro', 'SL - Distro', 'H9 - Processor',
        'Pull list - all positions',
    ]
    main = _render(pg, SHOW, 'SR - MAIN - Power')
    texts = main['texts']
    assert texts[:2] == ['2026 EXPERTS ONLY · POWER', 'SR - MAIN · page 3 of 17']
    bands = [t for t in texts if 'home run' in t]
    assert bands == [
        "SR1 · Soca 208 · 125' home run · 6 circuits",
        "SR2 · Soca 208 · 100' home run · 5 circuits",
        "SR3 · Soca 208 · 125' home run · 6 circuits",
        "SR4 · Soca 208 · 100' home run · 5 circuits",
    ]
    assert len([t for t in texts if re.fullmatch(r'SR[1-4]-\d', t)]) == 22
    assert 'FACTS' in texts and 'GANGS' not in texts
    assert not any(t.strip() == 'MULTI' for t in texts), [t for t in texts if t.strip() == 'MULTI']
    assert '22 at 208 V / 20 A · 14 panels each' in texts
    rulers = [t['text'] for t in main['textInfo'] if t['size'] == 22 and t['weight'] == 700]
    assert rulers[:7] == ['1', '5', '10', '15', '20', '25', '28'] and rulers[7:] == [str(i) for i in range(1, 12)]
    assert ["SR1 · 125'", "SR2 · 100'", "SR3 · 125'", "SR4 · 100'"] == [t for t in texts if re.fullmatch(r"SR\d · \d+'", t)]
    # the map: every label, and the typed cables as tags (the screen's switch is on);
    # no screen-name plate over them - the header names the screen
    assert 'SR1-1' in main['mapTexts'] and "10' True1" in main['mapTexts']
    assert 'SR - MAIN' not in main['mapTexts']
    # the band rule: SR3's band moved to the second column WITH its rows, so
    # every band is followed straight by its first circuit, none by a head
    for band in bands:
        assert texts[texts.index(band) + 1] == band.split(' ')[0] + '-' + ('2' if band.startswith('SR2') else '1'), \
            (band, texts[texts.index(band):texts.index(band) + 3])
    assert not [t for t in texts if t.endswith('(cont.)')]
    # printer: no colour, eleven distinct dashes across 22 circuits
    printer = _render(pg, SHOW.replace("palette: 'colour'", "palette: 'printer'"), 'SR - MAIN - Power')
    assert printer['coloured'] == 0
    assert len({tuple(d) for d in printer['dashes'] if d}) == 10    # ten dashed patterns + the solid one
    ret = _render(pg, SHOW, 'SR - Return - Power')['texts']
    assert 'GANGS' in ret
    i = ret.index('GANGS')
    assert ret[i + 4:i + 4 + 15:3] == ['SR5-1', 'SR5-2', 'SR5-3', 'SR5-4', 'SR5-5']
    assert ret.count('2fer') == 5
    assert "SR5 · Soca 208 · 125' home run · 6 circuits" in ret
    dpage = _render(pg, SHOW, 'SR - MAIN - Data')
    data = dpage['texts']
    assert 'SR - MAIN' not in dpage['mapTexts']
    assert 'H9 SR · H_16xRJ45+2xfiber · 16 ports' in data
    assert ['SR-1', 'SR-2', 'SR-3', 'SR-4'] == [t for t in data if re.fullmatch(r'SR-\d', t)]
    # the return end, whole: the backup port's label and where it lands
    assert [t for t in data if t.startswith('SR-') and 'R ·' in t] == [
        'SR-1R · H9 slot 2 · 1', 'SR-2R · H9 slot 2 · 2', 'SR-3R · H9 slot 2 · 3', 'SR-4R · H9 slot 2 · 4']
    assert not [t for t in data if t.startswith('slot ')]
    # the processor once, the redundancy in the bar's words
    assert data[data.index('Processor') + 1] == 'H9' and 'H9 · H9' not in data
    assert data[data.index('Redundancy') + 1] == 'Per card'
    # no page says box (the power side's word is breakout)
    for idx in range(len(plan)):
        texts_i = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [json.loads(_SHOW_JSON), idx])
        boxy = [t for t in texts_i if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        assert not boxy, (idx, boxy)
    distro = _render(pg, SHOW, 'SR - Distro')['texts']
    assert 'BREAKOUTS' in distro and 'BREAKOUT' in distro and 'Breakouts' in distro
    assert '5 breakouts' in distro
    assert ids['errors'] == []
