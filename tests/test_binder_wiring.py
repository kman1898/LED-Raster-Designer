"""The binder's SIGNAL + POWER sheet (app-binder-wiring.js) - a screen's
third sheet, after its Power and Data sheets (2026-09-08, on the last page
of the NACUBO packet: "he gave an example his binder and we could do this
for power and data drawing from a port to port … the last page is what i
was talking about").

The drawing area is split by a rule, SIGNAL over POWER (a screen with one
side draws that half alone). Each half: the wall (the same _bMap render,
rulers and brackets off), a STUB ROW on its bottom edge - a rounded tag per
port end under the column its run begins (primary, green) or ends (return,
red), per circuit under its first column (the power label orange) - a
WIRING BAND of orthogonal wires, and the DEVICE BLOCKS: schematic blocks,
one per device the screen's port ends land on (a box "CVT4K-S SR A · Card 1
· OPT 1-2", or the card itself "H9 SR · H_16xRJ45+2xfiber"; a backup box
its own block - "one per cvt including backups") with a numbered socket per
port (green / red / grey ring), one per multi the circuits are on - its
BREAKOUT ("there are no boxes... it is a breakout also known as a fan out"):
"SR1 · Multi 208 breakout · 125'", its slots as sockets, this screen's
orange, another screen's grey with that screen's name under it.

The wires: down from the stub to a LEVEL, across, down onto the socket;
levels allocated so no two horizontals overlap on one level and no
horizontal crosses another wire's drop (a stub's drop must stop above a
horizontal it would cross; a socket's drop must start below one). Tags
that would overlap spread along the row. The wall takes the zoom the half's
width allows and the height it needs; the type and the blocks scale into
what is left (1 to 2.4). One view per sheet, its bubble under the lower
half; the sheet numbers 2.n with the screen's others, the CONTENTS follows;
the export dialog's "Signal + Power" tick (default on) puts the sheets in.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15797 python3 -m pytest tests/test_binder_wiring.py -v --browser chromium
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import (  # noqa: E402
    SEED_JS, SHOW, _SHOW_JSON, PLAN, W, H, SCALE, DA, SCRATCH_FIXTURE,
    BOX_WORD, _generic_breakout, _title_block,
)

HERE = os.path.dirname(os.path.abspath(__file__))
pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# app-binder-wiring.js, in page px at 200 px/in
STUB_H, SOCKET_R, WIRE_W = 30, 12, 2
RETURN_DASH = [14, 8]
GREEN, RED, ORANGE, INK = '#00ff00', '#ff0000', '#d95000', '#111111'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    ids['errors'] = errors
    yield pg, ids
    context.close()


WIRING_JS = """([opts, title]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const r = app.renderBinderPage(opts, idx);
    const c = r.canvas, ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let coloured = 0;
    for (let i = 0; i < d.length; i += 4 * 61) {
        const R = d[i], G = d[i + 1], B = d[i + 2];
        if (Math.abs(R - G) > 10 || Math.abs(G - B) > 10 || Math.abs(R - B) > 10) coloured++;
    }
    return { texts: r.texts, wiring: r.wiring, bubble: r.bubble, page: r.page, plan: plan.map(p => [p.kind, p.number, p.title, p.view]),
             coloured, width: c.width, height: c.height,
             ops: r.record.ops.map(o => o.op === 'line' ? { op: 'line', n: o.points.length, width: o.width, dash: o.dash, stroke: o.stroke,
                                                              points: o.points }
                                    : o.op === 'image' ? { op: 'image', x: o.x, y: o.y, w: o.w, h: o.h } : { op: o.op }) };
}"""


def _sheet(pg, opts, title):
    out = pg.evaluate(WIRING_JS, [opts, title])
    assert 'missing' not in out, out
    return out


def _half(out, side):
    halves = [h for h in out['wiring']['halves'] if h['side'] == side]
    assert len(halves) == 1, out['wiring']
    return halves[0]


def _socket(block, n):
    return next(s for s in block['sockets'] if s['n'] == n)


def _check_wires(half):
    """Every wire ends at its socket's x on its block; a turning wire's
    horizontal lies in the band; no two horizontals on one level overlap;
    no horizontal crosses another wire's drop (a stub's drop stops above
    any horizontal it would meet, a socket's drop starts below one)."""
    blocks = {b['title']: b for b in half['blocks']}
    for w in half['wires']:
        b = blocks[w['device']]
        sk = _socket(b, w['socket'])
        assert abs(w['x2'] - sk['x']) < 0.01, (w, sk)
        assert abs(w['y2'] - (sk['y'] - SOCKET_R * half['scale'])) < 0.01, (w, sk)
        if w['level'] is not None:
            assert half['bandTop'] <= w['y'] <= half['bandTop'] + half['bandHeight'], (w, half['bandTop'], half['bandHeight'])
            assert w['y1'] < w['y'] < w['y2'], w
        else:
            assert abs(w['x1'] - w['x2']) < 0.5, w
    turning = [w for w in half['wires'] if w['level'] is not None]
    lo = lambda w: min(w['x1'], w['x2'])  # noqa: E731
    hi = lambda w: max(w['x1'], w['x2'])  # noqa: E731
    by_level = {}
    for w in turning:
        by_level.setdefault(w['level'], []).append(w)
    for level, ws in by_level.items():
        for i, a in enumerate(ws):
            for b in ws[i + 1:]:
                assert hi(a) < lo(b) or hi(b) < lo(a), ('two horizontals overlap on one level', level, a, b)
    inside = lambda x, w: lo(w) + 0.5 < x < hi(w) - 0.5  # noqa: E731
    # (over, under) pairs the picture demands; a pair demanded both ways is
    # a contradiction three-segment wires cannot route around (a wire whose
    # socket sits inside another's span while that one's socket sits inside
    # its own) - one crossing stands there and is not a fault
    over = set()
    for a in turning:
        for b in turning:
            if a is b:
                continue
            if inside(b['x1'], a):
                over.add((b['from'], a['from']))
            if inside(b['x2'], a):
                over.add((a['from'], b['from']))
    by_name = {w['from']: w for w in turning}
    crossings = []
    for hi_w, lo_w in over:
        if (lo_w, hi_w) in over:
            continue
        if not by_name[hi_w]['y'] < by_name[lo_w]['y']:
            crossings.append((hi_w, 'should sit over', lo_w))
    return crossings


def _inside(r, area):
    return r['x'] >= area['x'] - 0.01 and r['x'] + r['w'] <= area['x'] + area['w'] + 0.01 \
        and r['y'] >= area['y'] - 0.01 and r['y'] + r['h'] <= area['y'] + area['h'] + 0.01


def test_the_sheet_is_the_screens_third_and_wires_its_port_and_its_circuits(page):
    """WALL-A (4 x 3, one port on card SR's socket 1 - no box, no backup -
    two circuits on SR1 at 125'): sheet 2.3 "WALL-A · SIGNAL + POWER", view
    4, its bubble under the lower half. SIGNAL: one green stub "SR-1" on
    the wall's bottom edge under its first column, one CARD block "H9 SR ·
    H_16xRJ45+2xfiber" with 16 sockets - socket 1 green, the rest grey
    rings - and one wire from the stub onto socket 1. POWER: two orange
    stubs under each circuit's first column, one BREAKOUT block "SR1 ·
    Multi 208 breakout · 125'" with six sockets, 1 and 2 orange, and two
    wires. Both halves inside the drawing area, the signal half over the
    rule, the power half under it; the two walls are the two images; the
    printer sheet has no colour, its return wires would be dashed."""
    pg, ids = page
    out = _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')
    assert out['plan'][:4] == [['overview', '1.1', 'Overview', 1], ['power', '2.1', 'WALL-A - Power', 2],
                               ['data', '2.2', 'WALL-A - Data', 3], ['wiring', '2.3', 'WALL-A - Signal + Power', 4]]
    assert out['width'] == W * SCALE and out['height'] == H * SCALE
    texts = out['texts']
    _title_block(texts, 'WALL-A · SIGNAL + POWER', '2.3')
    assert out['page']['layout'] == 'wiring' and out['page']['cols'] == 2 and out['page']['view'] == 4
    assert out['page']['sides'] == {'power': True, 'data': True}
    assert [h['side'] for h in out['page']['halves']] == ['signal', 'power']
    assert out['bubble']['number'] == 4 and out['bubble']['name'] == 'WALL-A · SIGNAL + POWER'
    assert 'SIGNAL' in texts and 'POWER' in texts and texts.index('SIGNAL') < texts.index('POWER')
    halves = out['wiring']['halves']
    assert [h['side'] for h in halves] == ['signal', 'power']
    sig, pwr = halves
    # the signal half
    assert [(s['text'], s['kind']) for s in sig['stubs']] == [('SR-1', 'primary')]
    stub = sig['stubs'][0]
    m = sig['map']
    assert abs(stub['y'] - (m['y'] + m['h'] + 4 * sig['scale'])) < 0.01, (stub, m)     # on the wall's bottom edge
    assert abs(stub['h'] - STUB_H * sig['scale']) < 0.01
    assert m['x'] <= stub['col'] <= m['x'] + m['w'] / 4, (stub, m)                       # under the first column
    assert [b['title'] for b in sig['blocks']] == ['H9 SR · H_16xRJ45+2xfiber']
    card = sig['blocks'][0]
    assert [s['n'] for s in card['sockets']] == list(range(1, 17))
    assert [s['state'] for s in card['sockets']] == ['primary'] + ['free'] * 15
    assert [(w['from'], w['device'], w['socket'], w['kind']) for w in sig['wires']] == [('SR-1', 'H9 SR · H_16xRJ45+2xfiber', 1, 'primary')]
    assert _check_wires(sig) == []
    w = sig['wires'][0]
    assert w['x1'] == stub['cx'] and w['y1'] == stub['y'] + stub['h'] and w['colour'] == GREEN and w['dash'] == []
    # the block under the band, the band under the stubs, all in the half
    assert card['y'] >= sig['bandTop'] + sig['bandHeight'] and sig['bandTop'] >= stub['y'] + stub['h'], (card, sig['bandTop'], stub)
    # the power half
    assert [(s['text'], s['kind']) for s in pwr['stubs']] == [('SR1-1', 'power'), ('SR1-2', 'power')]
    assert [b['title'] for b in pwr['blocks']] == ["SR1 · Multi 208 breakout · 125'"]
    bk = pwr['blocks'][0]
    assert [(s['n'], s['state'], s['note']) for s in bk['sockets']] == \
        [(1, 'power', None), (2, 'power', None), (3, 'free', None), (4, 'free', None), (5, 'free', None), (6, 'free', None)]
    assert [(w['from'], w['socket']) for w in pwr['wires']] == [('SR1-1', 1), ('SR1-2', 2)]
    assert all(w['colour'] == INK and w['dash'] == [] for w in pwr['wires'])
    assert _check_wires(pwr) == []
    # the halves: the signal one wholly over the power one, both in the
    # drawing area, the walls the two images in that order
    sig_bottom = max(b['y'] + b['h'] for b in sig['blocks'])
    assert sig_bottom <= pwr['map']['area']['y'], (sig_bottom, pwr['map'])
    for h in halves:
        for r in h['stubs'] + h['blocks']:
            assert _inside(r, DA), (h['side'], r)
        assert _inside(h['map']['area'], DA), h['map']
    images = [o for o in out['ops'] if o['op'] == 'image']
    assert len(images) == 2
    assert (images[0]['x'], images[0]['y'], images[0]['w'], images[0]['h']) == tuple(sig['map']['area'][k] for k in 'xywh')
    assert (images[1]['x'], images[1]['y'], images[1]['w'], images[1]['h']) == tuple(pwr['map']['area'][k] for k in 'xywh')
    bubble = out['bubble']
    assert bubble['y'] - bubble['r'] >= max(b['y'] + b['h'] for b in pwr['blocks']) and bubble['y'] + bubble['r'] <= DA['y'] + DA['h'] + 1
    # the wire ops: 2 px, the colours as the discs wear them
    wires = [o for o in out['ops'] if o['op'] == 'line' and o['width'] == WIRE_W and o['stroke'] in (GREEN, INK) and 2 <= o['n'] <= 4]
    assert len(wires) >= 3, len(wires)
    # every socket a polyline circle, never the bubble's 37 points
    assert len([o for o in out['ops'] if o['op'] == 'line' and o['n'] == 37]) == 1
    # every text logged is an op; no sheet word is "box", "tail" or the
    # generic breakout
    assert not [t for t in texts if BOX_WORD.search(t) and 'breakout box' not in t.lower()], texts
    assert not _generic_breakout(texts), _generic_breakout(texts)
    assert not [t for t in texts if re.search(r'\btails?\b', t.lower())], texts
    # the printer sheet: no colour, black wires
    printer = _sheet(pg, {**json.loads(_SHOW_JSON), 'palette': 'printer'}, 'WALL-A - Signal + Power')
    assert printer['coloured'] == 0
    psig = _half(printer, 'signal')
    assert all(w['colour'] == INK for w in psig['wires'] + _half(printer, 'power')['wires'])
    assert ids['errors'] == []


def test_a_return_lands_on_its_own_block_and_a_box_replaces_the_card(page):
    """"one per cvt including backups": a CVT4K-S on card SR delivers WALL-A's
    port, a second card (its 1:1 partner) carries its return through its own
    CVT4K-S named BK. The signal half then has TWO stubs - the primary
    "SR-1" under the run's first column, the return "BK-1" (the mapped
    box's own label) under its last, red - and TWO blocks, "CVT4K-S SR · SR
    · OPT 1-2" with socket 1 green and "CVT4K-S BK · slot 2 · OPT 1-2" with
    socket 1 red, the rest grey; two wires, the return's red - dashed on the
    printer sheet, its socket a hollow ring there."""
    pg, ids = page
    setup = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        let st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[0].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxId}`, {name: 'SR'});
        st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const backupId = st.processors[0].slots[1].card.id;
        st = await j('POST', `/api/processors/${ids.procId}/cards/${backupId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const backupBox = st.processors[0].slots[1].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${backupBox}`, {name: 'BK'});
        await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
        await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
        await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        return { boxId, backupId, backupBox };
    }""", ids)
    try:
        out = _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')
        sig = _half(out, 'signal')
        assert [(s['text'], s['kind']) for s in sig['stubs']] == [('SR-1', 'primary'), ('BK-1', 'return')], sig['stubs']
        m = sig['map']
        first, last = sig['stubs']
        assert first['col'] < m['x'] + m['w'] / 4 and last['col'] > m['x'] + m['w'] * 3 / 4, (first, last, m)
        assert [b['title'] for b in sig['blocks']] == ['CVT4K-S SR · SR · OPT 1-2', 'CVT4K-S BK · slot 2 · OPT 1-2'], sig['blocks']
        a, b = sig['blocks']
        assert len(a['sockets']) == 16 and len(b['sockets']) == 16
        assert [s['state'] for s in a['sockets']] == ['primary'] + ['free'] * 15
        assert [s['state'] for s in b['sockets']] == ['return'] + ['free'] * 15
        assert [(w['from'], w['device'], w['socket'], w['kind'], w['colour'], w['dash']) for w in sig['wires']] == [
            ('SR-1', 'CVT4K-S SR · SR · OPT 1-2', 1, 'primary', GREEN, []),
            ('BK-1', 'CVT4K-S BK · slot 2 · OPT 1-2', 1, 'return', RED, [])]
        assert _check_wires(sig) == []
        # the blocks side by side under the wall, centred as a group, a gap between
        assert a['x'] + a['w'] < b['x'] and abs(a['y'] - b['y']) < 0.01
        centre = (a['x'] + b['x'] + b['w']) / 2
        assert abs(centre - (m['x'] + m['w'] / 2)) < 1, (centre, m)
        assert not [t for t in out['texts'] if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        printer = _sheet(pg, {**json.loads(_SHOW_JSON), 'palette': 'printer'}, 'WALL-A - Signal + Power')
        psig = _half(printer, 'signal')
        assert [(w['kind'], w['colour'], w['dash']) for w in psig['wires']] == [('primary', INK, []), ('return', INK, RETURN_DASH)]
        dashed = [o for o in printer['ops'] if o['op'] == 'line' and o['dash'] == RETURN_DASH]
        assert len(dashed) == 1 and dashed[0]['stroke'] == INK and dashed[0]['width'] == WIRE_W, dashed
        assert printer['coloured'] == 0
    finally:
        pg.evaluate("""async ([ids, s]) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
            await j('DELETE', `/api/processors/${ids.procId}/cvts/${s.backupBox}`);
            await j('DELETE', `/api/processors/${ids.procId}/cvts/${s.boxId}`);
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, setup])
    after = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'signal')
    assert [b['title'] for b in after['blocks']] == ['H9 SR · H_16xRJ45+2xfiber']
    assert ids['errors'] == []


def test_a_shared_multi_shows_the_other_screens_circuits_grey_with_its_name(page):
    """WALL-B's multi moved onto SR's number 1 - the multi WALL-A is on: on
    WALL-A's sheet the SR1 breakout shows WALL-B's circuits as grey sockets
    with "WALL-B" printed under them (the hover text, on paper), WALL-A's
    own orange; on WALL-B's sheet the mirror."""
    pg, ids = page
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setSocaNumber(b, 1, 1);
        app._circuitTailCache = null;
        app.renderLayers();
    }""", ids)
    try:
        a_side = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'power')
        assert len(a_side['blocks']) == 1 and a_side['blocks'][0]['title'].startswith('SR1 · Multi 208 breakout'), a_side['blocks']
        socks = a_side['blocks'][0]['sockets']
        mine = [s['n'] for s in socks if s['state'] == 'power']
        theirs = [(s['n'], s['note']) for s in socks if s['state'] == 'other']
        assert len(mine) == 2 and len(theirs) == 2 and all(n == 'WALL-B' for _k, n in theirs), socks
        assert not set(mine) & {k for k, _n in theirs}
        assert [s['n'] for s in socks if s['state'] == 'free'] == sorted(set(range(1, 7)) - set(mine) - {k for k, _n in theirs})
        assert 'WALL-B' in [t for t in _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')['texts']]
        b_side = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-B - Signal + Power'), 'power')
        bsocks = b_side['blocks'][0]['sockets']
        assert sorted(s['n'] for s in bsocks if s['state'] == 'power') == sorted(k for k, _n in theirs)
        assert [(s['n'], s['note']) for s in bsocks if s['state'] == 'other'] == [(n, 'WALL-A') for n in mine]
    finally:
        pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(l => l.id === ids.b);
            app.setSocaNumber(b, 1, 2);
            app._circuitTailCache = null;
            app.renderLayers();
        }""", ids)
    restored = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'power')
    assert [s['state'] for s in restored['blocks'][0]['sockets']] == ['power', 'power', 'free', 'free', 'free', 'free']
    assert ids['errors'] == []


def test_the_tick_takes_the_sheets_out_and_a_side_alone_draws_one_half(page):
    """The dialog's "Signal + Power" tick is on by default and stays on for
    a single-screen scope (it is that screen's sheet); off, no sheet is
    planned and the numbering closes up; the Maps radio on one side makes
    the sheet that half alone; the CONTENTS follows either way."""
    pg, ids = page
    out = pg.evaluate("""(o) => {
        const app = window.app;
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const tick = document.getElementById('export-binder-wiring');
        const dflt = { checked: tick.checked, read: app.readBinderOptions().wiring };
        tick.checked = false;
        const off = app.readBinderOptions().wiring;
        tick.checked = true;
        const scope = document.getElementById('export-binder-scope');
        scope.value = [...scope.options].find(x => x.value.startsWith('screen:')).value;
        scope.dispatchEvent(new Event('change'));
        const single = { wiring: document.getElementById('export-binder-wiring').checked,
                         cover: document.getElementById('export-binder-cover').checked };
        scope.value = 'show'; scope.dispatchEvent(new Event('change'));
        document.getElementById('export-cancel').click();
        const plan = (opts) => app.planBinder(opts).map(p => [p.kind, p.number, p.title, p.view]);
        const contents = (opts) => {
            const t = app.renderBinderPage(opts, 0).texts;
            const c = t.indexOf('CONTENTS');
            return t.slice(c + 3);
        };
        return { dflt, off, single,
                 without: plan({ ...o, wiring: false }), contentsWithout: contents({ ...o, wiring: false }),
                 power: plan({ ...o, sides: { power: true, data: false } }),
                 data: plan({ ...o, sides: { power: false, data: true }, cover: false, pull: false, hardware: false }),
                 sides: app.planBinder({ ...o, sides: { power: false, data: true } }).filter(p => p.kind === 'wiring').map(p => p.sides) };
    }""", json.loads(_SHOW_JSON))
    assert out['dflt'] == {'checked': True, 'read': True}
    assert out['off'] is False
    assert out['single'] == {'wiring': True, 'cover': False}
    assert out['without'] == [
        ['overview', '1.1', 'Overview', 1],
        ['power', '2.1', 'WALL-A - Power', 2], ['data', '2.2', 'WALL-A - Data', 3],
        ['power', '2.3', 'WALL-B - Power', 4], ['data', '2.4', 'WALL-B - Data', 5],
        ['power', '2.5', 'CENTER - Power', 6], ['data', '2.6', 'CENTER - Data', 7],
        ['pull', '3.1', 'Pull - SR Beach, CENTER', None], ['distro', '4.1', 'Distro - SR', None],
        ['processor', '4.2', 'Processor - H9 · Pull list', None]]
    listed = out['contentsWithout']
    assert listed[:6] == ['1.1', 'OVERVIEW', '2.1', 'WALL-A · POWER', '2.2', 'WALL-A · DATA'] and 'SIGNAL + POWER' not in ' '.join(listed)
    assert out['power'][1:5] == [['power', '2.1', 'WALL-A - Power', 2], ['wiring', '2.2', 'WALL-A - Signal + Power', 3],
                                 ['power', '2.3', 'WALL-B - Power', 4], ['wiring', '2.4', 'WALL-B - Signal + Power', 5]]
    assert out['data'][:2] == [['data', '2.1', 'WALL-A - Data', 1], ['wiring', '2.2', 'WALL-A - Signal + Power', 2]]
    assert out['sides'] == [{'power': False, 'data': True}] * 3
    # the one-sided sheet: the one half, no rule, the bubble still under it
    one = _sheet(pg, {**json.loads(_SHOW_JSON), 'sides': {'power': True, 'data': False}}, 'WALL-A - Signal + Power')
    assert [h['side'] for h in one['wiring']['halves']] == ['power'] and 'SIGNAL' not in one['texts']
    assert len([o for o in one['ops'] if o['op'] == 'image']) == 1
    pwr = one['wiring']['halves'][0]
    assert pwr['map']['h'] > _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'power')['map']['h'], 'the half alone has the height'
    assert one['bubble'] and one['bubble']['y'] - one['bubble']['r'] >= max(b['y'] + b['h'] for b in pwr['blocks'])
    assert ids['errors'] == []


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
def test_smoke_experts_only_sr_main(page):
    """The frozen Experts Only show, SR - MAIN's SIGNAL + POWER on Tabloid
    (2.9, view 10): four primary stubs SR A-1..4 and four return stubs SR
    B-1..4 (the runs go across: the primaries begin in column 1, the
    returns end in column 28, port 4's back in column 1 - the tags spread
    along the row); two signal
    blocks "CVT4K-S SR A · Card 1 · OPT 1-2" and "CVT4K-S SR B · Card 3 ·
    OPT 1-2" of 16 sockets, 1-4 green on A, 1-4 red on B, the rest grey
    (SR - Return's port 5 on box SR A is another screen's: grey); eight
    wires each onto its socket's x, no two horizontals overlapping on a
    level, no horizontal through another wire's drop. Power: 22 circuit
    stubs, four breakout blocks SR1..SR4 "Multi 208 breakout" with their
    lengths, 22 orange sockets; SR2's slot 1 and SR4's slot 3 are on no
    screen's plan - grey rings, no name. Sheets 2.7 / 2.8 / 2.9 and the
    CONTENTS follow; the printer sheet has no colour and dashed returns."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('wiring_smoke');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
    }""", project)
    out = _sheet(pg, json.loads(_SHOW_JSON), 'SR - MAIN - Signal + Power')
    plan = out['plan']
    assert [p[1:3] for p in plan if p[2].startswith('SR - MAIN')] == \
        [['2.7', 'SR - MAIN - Power'], ['2.8', 'SR - MAIN - Data'], ['2.9', 'SR - MAIN - Signal + Power']]
    assert len(plan) == 16 and [p[3] for p in plan][:13] == list(range(1, 14)) and [p[3] for p in plan][13:] == [None] * 3
    _title_block(out['texts'], 'SR - MAIN · SIGNAL + POWER', '2.9', show='2026 Experts Only')
    assert out['bubble']['number'] == 10 and out['bubble']['name'] == 'SR - MAIN · SIGNAL + POWER'
    sig, pwr = out['wiring']['halves']
    assert sig['side'] == 'signal' and pwr['side'] == 'power'
    # signal
    assert [s['text'] for s in sig['stubs'] if s['kind'] == 'primary'] == ['SR A-1', 'SR A-2', 'SR A-3', 'SR A-4']
    assert [s['text'] for s in sig['stubs'] if s['kind'] == 'return'] == ['SR B-1', 'SR B-2', 'SR B-3', 'SR B-4']
    m = sig['map']
    # the runs go across the 28 columns and snake: every primary begins in
    # column 1; ports 1-3 end in column 28, port 4 (an odd count of rows)
    # back in column 1 - the return stub sits under the column the run ENDS
    for s in sig['stubs']:
        if s['kind'] == 'primary' or s['text'] == 'SR B-4':
            assert s['col'] < m['x'] + m['w'] / 28 + 1, (s, m)
        else:
            assert s['col'] > m['x'] + m['w'] * 27 / 28 - 1, (s, m)
        assert abs(s['y'] - (m['y'] + m['h'] + 4 * sig['scale'])) < 0.01
    xs = sorted(sig['stubs'], key=lambda s: s['x'])
    assert all(a['x'] + a['w'] < b['x'] for a, b in zip(xs, xs[1:])), 'the tags spread, none overlapping'
    assert [b['title'] for b in sig['blocks']] == ['CVT4K-S SR A · Card 1 · OPT 1-2', 'CVT4K-S SR B · Card 3 · OPT 1-2']
    a, b = sig['blocks']
    assert [s['state'] for s in a['sockets']] == ['primary'] * 4 + ['free'] * 12
    assert [s['state'] for s in b['sockets']] == ['return'] * 4 + ['free'] * 12
    assert [(w['from'], w['socket'], w['kind']) for w in sig['wires']] == [
        ('SR A-1', 1, 'primary'), ('SR B-1', 1, 'return'), ('SR A-2', 2, 'primary'), ('SR B-2', 2, 'return'),
        ('SR A-3', 3, 'primary'), ('SR B-3', 3, 'return'), ('SR A-4', 4, 'primary'), ('SR B-4', 4, 'return')]
    assert _check_wires(sig) == []
    assert {w['colour'] for w in sig['wires'] if w['kind'] == 'primary'} == {GREEN}
    assert {w['colour'] for w in sig['wires'] if w['kind'] == 'return'} == {RED}
    # power
    assert len(pwr['stubs']) == 22 and all(s['kind'] == 'power' for s in pwr['stubs'])
    assert sorted(s['text'] for s in pwr['stubs']) == sorted(f'SR{k}-{n}' for k, ns in
                                                             ((1, range(1, 7)), (2, range(2, 7)), (3, range(1, 7)), (4, (1, 2, 4, 5, 6)))
                                                             for n in ns)
    assert [b['title'] for b in pwr['blocks']] == ["SR1 · Multi 208 breakout · 125'", "SR2 · Multi 208 breakout · 100'",
                                                   "SR3 · Multi 208 breakout · 125'", "SR4 · Multi 208 breakout · 100'"]
    states = {b['title'][:3]: [(s['n'], s['state'], s['note']) for s in b['sockets']] for b in pwr['blocks']}
    assert sum(1 for v in states.values() for _n, st, _note in v if st == 'power') == 22
    assert states['SR2'][0] == (1, 'free', None) and states['SR4'][2] == (3, 'free', None), states
    assert not [x for v in states.values() for x in v if x[1] == 'other']
    assert len(pwr['wires']) == 22 and _check_wires(pwr) == []
    assert all(w['colour'] == INK for w in pwr['wires'])
    # everything in the drawing area, the halves apart
    for h in (sig, pwr):
        for r in h['stubs'] + h['blocks']:
            assert _inside(r, DA), (h['side'], r)
    assert max(bl['y'] + bl['h'] for bl in sig['blocks']) <= pwr['map']['area']['y']
    # the CONTENTS
    ov = pg.evaluate("(o) => window.app.renderBinderPage(o, 0).texts", json.loads(_SHOW_JSON))
    c = ov.index('CONTENTS')
    listed = [(ov[c + 3 + 2 * n], ov[c + 4 + 2 * n]) for n in range(len(plan))]
    assert listed[7:10] == [('2.7', 'SR - MAIN · POWER'), ('2.8', 'SR - MAIN · DATA'), ('2.9', 'SR - MAIN · SIGNAL + POWER')]
    # the words
    assert not [t for t in out['texts'] if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
    assert not _generic_breakout(out['texts']) and not [t for t in out['texts'] if re.search(r'\btails?\b', t.lower())]
    # printer
    printer = _sheet(pg, {**json.loads(_SHOW_JSON), 'palette': 'printer'}, 'SR - MAIN - Signal + Power')
    assert printer['coloured'] == 0
    psig = _half(printer, 'signal')
    assert [w['dash'] for w in psig['wires'] if w['kind'] == 'return'] == [RETURN_DASH] * 4
    assert [w['dash'] for w in psig['wires'] if w['kind'] == 'primary'] == [[]] * 4
    assert len([o for o in printer['ops'] if o['op'] == 'line' and o['dash'] == RETURN_DASH]) == 4
    assert ids['errors'] == []
