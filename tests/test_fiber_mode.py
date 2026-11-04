"""Single mode and multimode NovaStar breakout boxes.

Owner, 2026-11-04: "We need to add single mode and multi mode for the
fiber. so 10-s and 10-m same with the pro models and 4k ones. if the M
variants are selected then the fiber will be multimode yes". His rulings:

  - the CVT10, CVT10 Pro and CVT4K each come as a single mode (-S) and a
    multimode (-M) model, named as NovaStar's sheets name them (CVT10-S /
    CVT10-M, CVT10 Pro-S / CVT10 Pro-M, CVT4K-S / CVT4K-M); the CVT8-5G and
    every other vendor's boxes are not split;
  - the box picker lists every single mode box, then every multimode one;
  - an -M behaves exactly like its -S twin but for the fiber's mode;
  - a show saved with a CVT10 or CVT10 Pro opens as the single mode box
    (the ids novastar-cvt10 / novastar-cvt10-pro stay, as the -S);
  - the box says "Single mode" or "Multimode" on its tray header, its gear
    and its sheet; fiber cable labels name the mode on the pull list, the
    binder's Fiber page and the box's sheet;
  - a single mode box and a multimode box never share a fiber cable: the
    server refuses it, and the client refuses it in the same words before
    anything is sent;
  - the show's cable stock keeps a single mode fiber list and a multimode
    one, and the pull sheet makes each fiber run from its own mode's list.

Run locally (each session takes its own free port):
    python -m pytest tests/test_fiber_mode.py -q
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

CATALOG_JSON = os.path.join(os.path.dirname(__file__), '..', 'src', 'static',
                            'data', 'processor_catalog.json')

TWINS = [('novastar-cvt10', 'novastar-cvt10-m', 'CVT10-S', 'CVT10-M'),
         ('novastar-cvt10-pro', 'novastar-cvt10-pro-m', 'CVT10 Pro-S', 'CVT10 Pro-M'),
         ('novastar-cvt4k-s', 'novastar-cvt4k-m', 'CVT4K-S', 'CVT4K-M')]
SINGLES = [s for s, _m, _sn, _mn in TWINS]
MULTIS = [m for _s, m, _sn, _mn in TWINS]
# What only the mode (and the sheet it is read from) may change.
MODE_KEYS = {'id', 'name', 'fiberMode', 'fiberModeNote', 'fiberModeSource'}
H9 = 'novastar-h9'
H4 = 'novastar-card-h-4xfiber'


def _ok(resp, code=None):
    assert resp.status_code in ((code,) if code else (200, 201)), resp.get_data(as_text=True)[:300]
    return resp.get_json()


def _cvt_entries():
    with open(CATALOG_JSON, encoding='utf-8') as f:
        return [d for d in json.load(f)['devices'] if d.get('kind') == 'cvt']


# ── the catalog ──────────────────────────────────────────────────────────

def test_the_six_boxes_carry_novastars_names_their_mode_and_its_source():
    by_id = {d['id']: d for d in _cvt_entries()}
    for s, m, s_name, m_name in TWINS:
        assert (by_id[s]['name'], by_id[s]['fiberMode']) == (s_name, 'single')
        assert (by_id[m]['name'], by_id[m]['fiberMode']) == (m_name, 'multi')
        for d in (by_id[s], by_id[m]):
            assert d['vendor'] == 'NovaStar'
            assert d['fiberModeSource'].startswith('https://oss.novastar.tech/'), d['id']
            assert d['fiberModeNote'].strip(), d['id']
            assert '—' not in d['name'] and '–' not in d['name']
    # nothing else states a mode: not the CVT8-5G, no other vendor's box
    stated = sorted(d['id'] for d in _cvt_entries() if 'fiberMode' in d)
    assert stated == sorted(SINGLES + MULTIS)
    assert 'fiberMode' not in by_id['novastar-cvt8-5g']


def test_the_single_mode_boxes_come_first_in_the_catalog_then_the_multimode():
    order = [d['id'] for d in _cvt_entries() if d.get('fiberMode')]
    assert order == ['novastar-cvt4k-s', 'novastar-cvt10', 'novastar-cvt10-pro',
                     'novastar-cvt4k-m', 'novastar-cvt10-m', 'novastar-cvt10-pro-m'], order


def test_each_multimode_box_equals_its_single_mode_twin_but_for_the_mode():
    by_id = {d['id']: d for d in _cvt_entries()}
    for s, m, _sn, _mn in TWINS:
        a, b = by_id[s], by_id[m]
        behave = lambda d: {k: v for k, v in d.items()  # noqa: E731
                            if k not in MODE_KEYS and not k.endswith(('Note', 'Source')) and k != 'note'}
        assert behave(a) == behave(b), (s, m)
        assert set(a) == set(b), (s, m, set(a) ^ set(b))
        # the catalog's own readers agree
        assert catalog.trunks_in(a) == catalog.trunks_in(b)
        assert catalog.input_outputs(a) == catalog.input_outputs(b)
        assert catalog.box_backup_ports(a) == catalog.box_backup_ports(b)
        assert catalog.box_fiber_mode(a) == 'single' and catalog.box_fiber_mode(b) == 'multi'


def _h9(client, mode=None, card=H4):
    st = _ok(client.post('/api/processors', json={'deviceId': H9}))
    pid = st['resolved'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': card}))
    cid = st['resolved'][-1]['slots'][0]['card']['id']
    if mode:
        _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))
    return pid, cid


def _add(client, pid, cid, device, pair=False):
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': device, 'pair': pair}), 201)
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    return card['cvts']


def _resolved_card(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']


@pytest.mark.parametrize('single,multi', [(s, m) for s, m, _a, _b in TWINS])
@pytest.mark.parametrize('card_mode', [None, 'backup'])
def test_a_multimode_box_resolves_exactly_as_its_twin_on_the_same_card(client, single, multi, card_mode):
    """The same card, the same gesture (the default pair, the card's mode):
    every resolved field but the box's id, model and mode is the same."""
    out = []
    for device in (single, multi):
        pid, cid = _h9(client, card_mode)
        boxes = _add(client, pid, cid, device, pair=True)
        card = _resolved_card(client, pid)
        out.append((card, boxes))
    (card_s, boxes_s), (card_m, boxes_m) = out
    assert len(boxes_s) == len(boxes_m)
    # ids (each card is on its own processor), titles and model names
    # carry the model; everything else is behavior
    ignore = {'id', 'fiberMode', 'backupOf', 'duplicateOf', 'backedUpBy', 'copyOf'}

    def plain(v):
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()
                    if k not in ignore and not k.endswith(('Id', 'Title', 'Name'))}
        if isinstance(v, list):
            return [plain(x) for x in v]
        return v

    for bs, bm in zip(boxes_s, boxes_m):
        assert bs['fiberMode'] == 'single' and bm['fiberMode'] == 'multi'
        assert plain(bs) == plain(bm), (single, multi)
    for key in ('defined', 'ceiling', 'trunksUsed', 'trunksFree', 'backupCount'):
        assert card_s.get(key) == card_m.get(key), key


def test_a_show_saved_with_a_cvt10_opens_with_the_single_mode_box(client):
    """The ids novastar-cvt10 and novastar-cvt10-pro stay, as the -S
    entries: a saved show's box record reads CVT10-S / CVT10 Pro-S and
    single mode with nothing migrated, and the record is stored as it came."""
    pid, cid = _h9(client)
    _add(client, pid, cid, 'novastar-cvt10')
    _add(client, pid, cid, 'novastar-cvt10-pro')
    saved = client.get('/api/project').get_json()
    raw = [b['deviceId'] for b in next(p for p in saved['processors'] if p['id'] == pid)
           ['slots'][0]['card']['cvts']]
    assert raw == ['novastar-cvt10', 'novastar-cvt10-pro']
    _ok(client.put('/api/project', json=saved))
    boxes = _resolved_card(client, pid)['cvts']
    assert [(b['deviceId'], b['deviceName'], b['fiberMode']) for b in boxes] == [
        ('novastar-cvt10', 'CVT10-S', 'single'), ('novastar-cvt10-pro', 'CVT10 Pro-S', 'single')]
    again = client.get('/api/project').get_json()
    assert [b['deviceId'] for b in next(p for p in again['processors'] if p['id'] == pid)
            ['slots'][0]['card']['cvts']] == raw


# ── the refusal, on the server ───────────────────────────────────────────

def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}', json=body)


def _tac(client, link=None, **kw):
    body = dict(kind='tac', strands=12, **kw)
    if link:
        body['link'] = link
    return _ok(client.post('/api/fiber-cables', json=body), 201)['fiberCables'][-1]


def _raw_links(client, pid, box_id):
    st = client.get('/api/processors').get_json()
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return next(b for b in card['cvts'] if b['id'] == box_id).get('fiberLinks')


def test_a_multimode_box_cannot_take_a_cable_a_single_mode_box_is_on(client):
    pid, cid = _h9(client)
    s = _add(client, pid, cid, 'novastar-cvt10')[-1]
    m = _add(client, pid, cid, 'novastar-cvt10-m')[-1]
    tac = _tac(client, ft=1000, connector='ST', link={'boxId': s['id'], 'key': 'p1'})
    resp = _link(client, pid, m['id'], 'p1', {'cable': tac['id']})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == (
        f"{tac['name']} carries single mode fiber to {s['displayTitle']}, and "
        f"{m['displayTitle']} is a multimode box. Single mode and multimode never "
        'share a fiber cable.')
    assert _raw_links(client, pid, m['id']) is None
    # given strands, refused the same way; nothing is stored
    resp = _link(client, pid, m['id'], 'p1', {'cable': tac['id'], 'strands': [5, 6]})
    assert resp.status_code == 400 and 'never share a fiber cable' in resp.get_json()['error']
    assert _raw_links(client, pid, m['id']) is None
    # the other way round too, and an opticalCON is the same
    tac_m = _tac(client, link={'boxId': m['id'], 'key': 'p1'})
    resp = _link(client, pid, s['id'], 'p1', {'cable': tac_m['id']})
    assert resp.status_code == 400
    assert resp.get_json()['error'].startswith(f"{tac_m['name']} carries multimode fiber to ")
    quad = _ok(client.post('/api/fiber-cables', json={
        'kind': 'opticalcon-quad', 'link': {'boxId': s['id'], 'key': 'p1'}}), 201)['fiberCables'][-1]
    resp = _link(client, pid, m['id'], 'p1', {'cable': quad['id']})
    assert resp.status_code == 400 and 'never share a fiber cable' in resp.get_json()['error']
    # two boxes of one mode still share by strand
    s2 = _add(client, pid, cid, 'novastar-cvt10')[-1]
    _ok(_link(client, pid, s2['id'], 'p1', {'cable': quad['id']}))
    assert _raw_links(client, pid, s2['id'])['p1']['cable'] == quad['id']


def test_a_backup_box_of_the_other_mode_cannot_share_the_main_boxs_tac(client):
    """NovaStar's default pair on a Backup card: the multimode pair's
    backup box asked onto the TAC a single mode box is on is refused, and a
    backup link sent with no cable (it follows its primary's) is checked
    on the cable it would follow."""
    pid, cid = _h9(client, 'backup')
    s = _add(client, pid, cid, 'novastar-cvt10', pair=False)[-1]
    boxes = _add(client, pid, cid, 'novastar-cvt10-m', pair=True)
    m_backup = next((b for b in boxes if b.get('backupOf')), None)
    assert m_backup and m_backup['fiberMode'] == 'multi', boxes
    tac = _tac(client, link={'boxId': s['id'], 'key': 'p1'})
    resp = _link(client, pid, m_backup['id'], 'p1', {'cable': tac['id']})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == (
        f"{tac['name']} carries single mode fiber to {s['displayTitle']}, and "
        f"{m_backup['displayTitle']} is a multimode box. Single mode and multimode "
        'never share a fiber cable.')


def test_the_refusal_and_the_labels_on_the_server_name_the_mode():
    assert catalog.fiber_mode_word('single') == 'Single mode'
    assert catalog.fiber_mode_word('multi') == 'Multimode'
    assert catalog.fiber_mode_word('multi', lower=True) == 'multimode'
    assert catalog.fiber_mode_word(None) == ''
    tac = {'kind': 'tac', 'strands': 12, 'connector': 'ST'}
    assert catalog.fiber_cable_type_text(tac) == 'TAC 12 · ST'
    assert catalog.fiber_cable_type_text(tac, 'single') == 'TAC 12 · ST · Single mode'
    assert catalog.fiber_cable_type_text({'kind': 'mtp', 'strands': 24}, 'multi') == 'MTP 24 · Multimode'
    assert catalog.fiber_cable_type_text({'kind': 'opticalcon-duo'}, 'multi') == 'opticalCON DUO · Multimode'


# ── the cable stock, on the server ───────────────────────────────────────

def test_the_stock_keeps_a_single_mode_and_a_multimode_fiber_list():
    import routes_cable_stock as rcs
    s = rcs.normalize_stock({'perKind': False, 'ft': {'all': [100], 'fiberSingle': [500, 250],
                                                       'fiberMulti': [300]}})
    assert s['ft']['fiberSingle'] == [250, 500] and s['ft']['fiberMulti'] == [300]
    assert s['m']['fiberSingle'] == [] and s['m']['fiberMulti'] == []
    # a stock saved before them has none: its fiber is written as typed
    old = rcs.normalize_stock({'perKind': True, 'ft': {'multi': [25]}})
    assert old['ft']['fiberSingle'] == [] and old['ft']['fiberMulti'] == []
    assert rcs.normalize_stock({'ft': {'fiberMulti': ['x']}}) is None


# ── the app ──────────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables; delete proj.snakes;
    proj.cableStock = null;
    await j('PUT', '/api/project', proj);
    for (const name of ['W1', 'W2']) {
        await j('POST', '/api/layer/add', {name, columns: 4, rows: 4, cabinet_width: 200,
                                           cabinet_height: 200, processorType: 'novastar-armor'});
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    for (const deviceId of ['novastar-cvt10', 'novastar-cvt10-m']) {
        st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, {deviceId, pair: false});
    }
    const [s, m] = st.processors[0].slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 1000, connector: 'ST',
                                               link: {boxId: s, key: 'p1'}});
    const tacS = st.fiberCables[st.fiberCables.length - 1].id;
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 600, connector: 'ST',
                                               link: {boxId: m, key: 'p1'}});
    const tacM = st.fiberCables[st.fiberCables.length - 1].id;
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_mode_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    // one screen on each box, so both are in use
    const card = app._processorsResolved.find(p => p.id === pid).slots[0].card;
    for (const [i, id] of [s, m].entries()) {
        const first = card.cvts.find(b => b.id === id).ports[0].number;
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(app.project.layers[i].id), cardId: cid, firstPort: first, lastPort: first + 3});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Mode Seed');
    return {pid, cid, s, m, tacS, tacM};
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = JSON.parse(JSON.stringify(app.buildPullList()));
    return out.totals.map(r => [r.type, r.length, r.qty, r.label]);
}"""


def _route_dialogs(context):
    """Never a real Save or folder dialog on the desktop."""
    for path in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{path}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({'ok': False, 'cancelled': True})))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    _route_dialogs(context)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true")
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_function("(id) => !!document.querySelector(`[data-lrd-field=\"box-fiber-mode-${id}\"]`)",
                         arg=ids['m'])
    ids['errors'] = errors
    yield pg, ids
    context.close()


def test_the_picker_lists_the_single_mode_boxes_then_the_multimode(page):
    pg, ids = page
    out = pg.evaluate("""(cid) => {
        const app = window.app;
        const card = app._processorsResolved.flatMap(p => p.slots).map(s => s.card)
            .find(c => c && c.id === cid);
        return app._cardBoxFits(card).map(d => [d.id, d.name, d.fiberMode || null]);
    }""", ids['cid'])
    moded = [x for x in out if x[2]]
    assert [x[2] for x in moded] == ['single'] * 3 + ['multi'] * 3, out
    assert [x[1] for x in moded] == ['CVT4K-S', 'CVT10-S', 'CVT10 Pro-S',
                                     'CVT4K-M', 'CVT10-M', 'CVT10 Pro-M'], out
    # the gear's picker reads that list as it stands
    pg.evaluate("(cid) => document.querySelector(`[data-hwpop=\"card-${cid}\"]`).click()", ids['cid'])
    pg.wait_for_selector(f'[data-lrd-field="processor-cvt-add-{ids["cid"]}"]')
    shown = pg.evaluate("""(cid) => [...document.querySelector(
        `[data-lrd-field="processor-cvt-add-${cid}"]`).options].filter(o => o.value).map(o => o.textContent)""",
                        ids['cid'])
    assert [t for t in shown if t.startswith('CVT1') or t.startswith('CVT4')] == [x[1] for x in moded], shown
    # for the owner's look: the list opened out in place
    box = pg.evaluate("""(cid) => {
        const sel = document.querySelector(`[data-lrd-field="processor-cvt-add-${cid}"]`);
        sel.size = sel.options.length;
        const r = document.getElementById('hw-gear-popover').getBoundingClientRect();
        return {x: r.left, y: Math.max(0, r.top - 60), width: r.width, height: r.height + 260};
    }""", ids['cid'])
    pg.screenshot(path=_shot('picker.png'), clip=box)
    pg.evaluate("(cid) => { document.querySelector(`[data-lrd-field=\"processor-cvt-add-${cid}\"]`).size = 0; }",
                ids['cid'])
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    assert ids['errors'] == []


def _shot(name):
    """Where a screenshot for the owner lands, when asked for (LRD_SHOTS)."""
    root = os.environ.get('LRD_SHOTS')
    if not root:
        import tempfile
        root = tempfile.gettempdir()
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, name)


def test_the_box_card_its_gear_and_its_sheet_say_the_mode(page):
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const tag = (id) => document.querySelector(`[data-lrd-field="box-fiber-mode-${id}"]`);
        const head = (id) => document.querySelector(`[data-hwdock="box-${id}"]`);
        return { s: tag(ids.s).textContent, m: tag(ids.m).textContent,
                 sHead: head(ids.s) && head(ids.s).contains(tag(ids.s)),
                 tip: tag(ids.m).title };
    }""", ids)
    assert (out['s'], out['m']) == ('Single mode', 'Multimode'), out
    assert out['sHead'], out
    assert out['tip'] == ('CVT10-M is a multimode box: its fiber is multimode. Single mode and '
                          'multimode never share a fiber cable.'), out
    head = pg.locator(f'[data-hwdock="box-{ids["m"]}"]')
    head.scroll_into_view_if_needed()
    dock = pg.evaluate("() => { const r = document.getElementById('hardware-dock-body').getBoundingClientRect();"
                       " return {x: r.left, y: r.top, width: Math.min(r.width, 900), height: r.height}; }")
    pg.screenshot(path=_shot('box-card.png'), clip=dock)
    # the gear
    pg.evaluate("(id) => document.querySelector(`[data-hwpop=\"box-${id}\"]`).click()", ids['m'])
    pg.wait_for_selector(f'[data-lrd-field="processor-cvt-mode-{ids["m"]}"]')
    line = pg.evaluate("(id) => document.querySelector(`[data-lrd-field=\"processor-cvt-mode-${id}\"]`).textContent",
                       ids['m'])
    assert line == 'CVT10-M · Multimode fiber', line
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    # the sheet's Fiber section
    pg.locator(f'[data-lrd-field="data-cable-sheet-{ids["m"]}"]').first.click()
    pg.wait_for_selector(f'[data-lrd-field="fiber-mode-{ids["m"]}"]')
    sec = pg.evaluate("""(id) => ({
        mode: document.querySelector(`[data-lrd-field="fiber-mode-${id}"]`).textContent,
        options: [...document.querySelector(`[data-lrd-field="fiber-link-cable-${id}-p1"]`).options]
            .map(o => o.textContent),
    })""", ids['m'])
    assert sec['mode'] == 'Multimode', sec
    assert "TAC B · 12 · 600' · ST · Multimode" in sec['options'], sec
    assert "TAC A · 12 · 1000' · ST · Single mode" in sec['options'], sec
    pg.locator(f'[data-lrd-field="data-cable-sheet-{ids["m"]}"]').first.click()
    pg.wait_for_timeout(200)
    assert ids['errors'] == []


def test_the_pull_list_and_the_binder_name_the_mode(page):
    pg, ids = page
    rows = pg.evaluate(LIST_JS)
    tacs = sorted(r for r in rows if r[0].startswith('TAC'))
    assert tacs == [['TAC 12 · ST · Multimode', "600'", 1, 'TAC B'],
                    ['TAC 12 · ST · Single mode', "1000'", 1, 'TAC A']], rows
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const s = app.getFiberCable(ids.tacS), m = app.getFiberCable(ids.tacM);
        const proc = app._processorsResolved.find(p => p.id === ids.pid);
        const rows = app._bfPullRows(app.buildPullList()).map(r => r.type);
        return { mapS: app._bStrandMapTitle(s), mapM: app._bStrandMapTitle(m),
                 pullRows: rows.sort(),
                 maps: app._bStrandMaps(proc).map(x => x.title) };
    }""", ids)
    assert out['mapS'] == "Strand map · TAC A · TAC 12 · ST · Single mode · 1000'", out
    assert out['mapM'] == "Strand map · TAC B · TAC 12 · ST · Multimode · 600'", out
    assert out['pullRows'] == ['TAC 12 · ST · Multimode', 'TAC 12 · ST · Single mode'], out
    assert sorted(out['maps']) == sorted([out['mapS'], out['mapM']]), out
    assert ids['errors'] == []


def test_the_client_refuses_a_mixed_link_in_the_servers_words_and_sends_nothing(page):
    pg, ids = page
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const sent = [];
        const realFetch = window.fetch;
        window.fetch = (url, opts) => { if (String(url).includes('/fiber-links/')) sent.push(url);
                                        return realFetch(url, opts); };
        const toasts = [];
        const realToast = app._toast;
        app._toast = function (msg, isError) { toasts.push([msg, !!isError]); return realToast.apply(this, arguments); };
        const box = app.fiberBoxById(ids.m);
        await app.setFiberLink(box, 'p1', { cable: ids.tacS }, 'Set Fiber Link');
        window.fetch = realFetch;
        app._toast = realToast;
        // the server, asked straight, refuses the same words
        const r = await fetch(`/api/processors/${ids.pid}/cvts/${ids.m}/fiber-links/p1`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({cable: ids.tacS})});
        return { sent, toasts, status: r.status, server: (await r.json()).error,
                 link: (app.fiberBoxById(ids.m).fiberLinks || {}).p1 };
    }""", ids)
    assert out['sent'] == [], out
    assert out['status'] == 400, out
    assert out['toasts'] == [[out['server'], True]], out
    assert out['server'] == ('TAC A carries single mode fiber to CVT10-S A, and CVT10-M B is a '
                             'multimode box. Single mode and multimode never share a fiber cable.'), out
    assert out['link']['cable'] == ids['tacM'], out
    # picked in the sheet: refused, the select snaps back to what is stored
    pg.locator(f'[data-lrd-field="data-cable-sheet-{ids["m"]}"]').first.click()
    sel = f'[data-lrd-field="fiber-link-cable-{ids["m"]}-p1"]'
    pg.wait_for_selector(sel)
    pg.locator(sel).select_option(ids['tacS'])
    pg.wait_for_timeout(400)
    pg.screenshot(path=_shot('refusal.png'))
    assert pg.locator(sel).input_value() == ids['tacM']
    pg.locator(f'[data-lrd-field="data-cable-sheet-{ids["m"]}"]').first.click()
    pg.wait_for_timeout(200)
    assert ids['errors'] == []


def test_the_pull_sheet_pulls_each_fiber_from_its_own_modes_stock(page):
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const before = app.project.cableStock;
        app.project.cableStock = { perKind: false,
            ft: { all: [100], fiberSingle: [500], fiberMulti: [250] }, m: {} };
        const rows = JSON.parse(JSON.stringify(app.buildPullList())).totals
            .filter(r => r.type.startsWith('TAC')).map(r => [r.type, r.length, r.qty]).sort();
        const lists = [app.cableStockList('fiberSingle'), app.cableStockList('fiberMulti'),
                       app.cableStockList('data')];
        const kinds = [app.fiberStockKind(app.getFiberCable(ids.tacS)),
                       app.fiberStockKind(app.getFiberCable(ids.tacM))];
        app.project.cableStock = before;
        return { rows, lists, kinds };
    }""", ids)
    assert out['kinds'] == ['fiberSingle', 'fiberMulti'], out
    assert out['lists'] == [[500], [250], [100]], out
    # 600' of multimode from 250s is 250'+250'+250'... the least extra
    # length first, then the fewest pieces: three 250s (750'); 1000' of
    # single mode from 500s is two
    assert out['rows'] == [['TAC 12 · ST · Multimode', "250'", 3],
                           ['TAC 12 · ST · Single mode', "500'", 2]], out
    # Preferences > Cable stock: a row for each, shown whichever way the
    # per-kind switch is set, and a round trip through the fields
    prefs = pg.evaluate("""() => {
        const app = window.app;
        app.openPreferencesModal();
        app.showPreferencesTab && app.showPreferencesTab('stock');
        const vis = () => ['fiberSingle', 'fiberMulti'].map(k =>
            document.querySelector(`[data-cable-stock-fiber="${k}"]`).style.display !== 'none');
        const per = document.getElementById('pref-cable-stock-per-kind');
        per.checked = false; per.dispatchEvent(new Event('change'));
        const off = vis();
        per.checked = true; per.dispatchEvent(new Event('change'));
        const on = vis();
        app.fillCableStockUI({ perKind: true, ft: { fiberSingle: [500, 1000], fiberMulti: [300] }, m: {} });
        const read = app.readCableStockUI();
        const fields = [document.getElementById('pref-cable-stock-fiberSingle-ft').value,
                        document.getElementById('pref-cable-stock-fiberMulti-ft').value];
        return { off, on, fields, single: read.ft.fiberSingle, multi: read.ft.fiberMulti };
    }""")
    pg.wait_for_timeout(200)
    pg.screenshot(path=_shot('cable-stock.png'))
    pg.evaluate("() => { document.getElementById('preferences-modal').style.display = 'none'; }")
    assert prefs['off'] == [True, True] and prefs['on'] == [True, True], prefs
    assert (prefs['single'], prefs['multi']) == ([500, 1000], [300]), prefs
    assert ids['errors'] == []


def test_the_binders_short_band_brackets_the_mode_as_sm_or_mm(page):
    """Owner, 2026-11-04: the binder processor pages' short band reads
    "(TAC 24 SM)" / "(TAC 24 MM)" - the mode in short beside the cable's
    kind, joined with a space as the band joins its words - on the one-line
    band and on the grouped band / Breakout boxes table alike. A box with
    no stated mode reads as before (tests/test_fiber_extensions.py,
    tests/test_shared_opticalcon.py: "(MTP 12)", "(opticalCON QUAD)")."""
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const box = (id) => app._dockFindCvt(id).cvt;
        const sub = (id) => (app._bBoxInputGroups(box(id)) || []).map(g => g.sub || g.text);
        return { s: app._bBoxFiberText(box(ids.s)), m: app._bBoxFiberText(box(ids.m)),
                 band: app._bBoxBandText(box(ids.s)), sSub: sub(ids.s), mSub: sub(ids.m) };
    }""", ids)
    assert out['s'] == 'OPT 1 TAC A (TAC 12 SM) 1-2', out
    assert out['m'] == 'OPT 1 TAC B (TAC 12 MM) 1-2', out
    assert out['band'].startswith('CVT10-S A · ') and out['band'].endswith(' · OPT 1 TAC A (TAC 12 SM) 1-2'), out
    assert out['sSub'] == ['TAC A (TAC 12 SM)'], out
    assert out['mSub'] == ['TAC B (TAC 12 MM)'], out
    assert ids['errors'] == []
