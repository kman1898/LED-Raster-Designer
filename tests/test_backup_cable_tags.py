"""The return marker wears its own cable tag.

"also redundancy extensions and snakes arent showing their cable tags"
(2026-09-07). Until now the data pass hung a home-run tag beside the PRIMARY
marker only (app.dataPortCableForScreen - the primary socket's cable), so a
backup box's snake, or an extension on a backup socket, never reached the map
or the binder. Now the RETURN marker reads the backup end the same way:

  - app.dataPortBackupCableForScreen(layer, portNum): the pinned socket's
    resolved card port -> backedBy ({cardId, port}, via _pullBackedBy, the
    pull list's own walker) -> dataPortCable(bb.cardId, bb.port). Null with
    no backup, or a backup socket carrying nothing.
  - canvas.js draws that reading's `text` beside the return marker with the
    same drawer, colours and flip-inside rule the primary's tag uses, on
    screen and in exportMode alike (the binder reads through the renderer).

The fixture: card SR (H_16xRJ45+2xfiber, box A) carries WALL's six ports on
box A's sockets 1-6, backed Per card (1:1) by a second H_16 with its own box
B, so WALL's port n returns on box B's socket n. Box A's snake is "SR Primary"
over 1-6; box B's is "SR Backup" over 1-6 with a 25' extension on socket 1.
Everything here is read off the renderer with spies on drawCableTag,
ctx.fillText, ctx.arc and ctx.roundRect - the way test_data_snakes.py and
test_cable_tag_wrap.py read their tags.
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 8, rows: 12,
                                       cabinet_width: 200, cabinet_height: 200});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    st = await j('POST', `/api/processors/${pid}/cards/${cardId}/cvts`,
                 {deviceId: 'novastar-cvt10', pair: false});
    const boxA = st.processors[0].slots[0].card.cvts[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/1`,
                 {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const backupId = st.processors[0].slots[1].card.id;
    st = await j('POST', `/api/processors/${pid}/cards/${backupId}/cvts`,
                 {deviceId: 'novastar-cvt10', pair: false});
    const boxB = st.processors[0].slots[1].card.cvts[0].id;
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {backupCardId: backupId});
    const p1 = await j('GET', '/api/project');
    for (const l of p1.layers) {
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'novastar-armor'});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('backup_tags_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', {layerId: String(wall.id), cardId});
    const scr = app._assignment.screens.find(s => s.layerId === String(wall.id));
    const socks = scr.ports.map(pt => pt.port);
    const backs = scr.ports.map(pt => app._pullBackedBy(cardId, pt.port));
    await j('PUT', `/api/processors/${pid}/cvts/${boxA}`,
            {snakes: [{ports: socks, ft: 100, name: 'SR Primary'}]});
    await j('PUT', `/api/processors/${pid}/cvts/${boxB}`, {
        snakes: [{ports: backs.map(b => b.port), ft: 150, name: 'SR Backup'}],
        portCables: {[String(backs[0].port)]: {ft: 25}},
    });
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    app.resetHistory('Backup Tags Seed');
    return {
        id: wall.id, procId: pid, cardId, backupId, boxA, boxB,
        ports: scr.ports.map(pt => [pt.number, pt.cardId, pt.port]),
        backs: backs.map(b => b ? [b.cardId, b.port] : null),
    };
}"""

# One data-flow frame, interactively and in exportMode, read off the
# renderer: every drawCableTag call (text, the circle edge it hangs off,
# whether it flipped, the colours, the lines it wraps to) with the pill
# roundRect it drew; every fillText with its anchor; every arc. Plus the
# screen's bounds in the same (panel-local) frame, each port's primary and
# return label, and the two readings the tags come from. `opts.flag`
# stands in for Show Cable Tags for the frame only; `opts.pattern` for the
# flow pattern. Both are put back afterwards.
FRAME_JS = """([ids, opts]) => {
    const r = window.canvasRenderer, ctx = r.ctx, app = window.app;
    const l = app.project.layers.find(x => x.id === ids.id);
    const proto = Object.getPrototypeOf(r);
    const grab = () => {
        const texts = [], tags = [], arcs = [], pills = [];
        const oT = ctx.fillText, oA = ctx.arc, oR = ctx.roundRect;
        let inTag = false;
        ctx.fillText = function (t, x, y, w) {
            texts.push({t: String(t), x, y}); return oT.call(ctx, t, x, y, w);
        };
        ctx.arc = function (x, y, rad, ...rest) {
            arcs.push({x, y, r: rad}); return oA.call(ctx, x, y, rad, ...rest);
        };
        ctx.roundRect = function (x, y, w, h, c) {
            if (inTag) pills.push({left: x, right: x + w, top: y, bottom: y + h});
            return oR.call(ctx, x, y, w, h, c);
        };
        r.drawCableTag = function (text, x, y, labelSize, colors, o) {
            tags.push({text, x, y, flip: !!(o && o.flip), colors: colors || null,
                       w: r.cableTagWidth(text, labelSize),
                       lines: r.cableTagLayout(text, labelSize).lines});
            inTag = true;
            try { return proto.drawCableTag.call(r, text, x, y, labelSize, colors, o); }
            finally { inTag = false; }
        };
        try { r.render(); }
        finally { ctx.fillText = oT; ctx.arc = oA; ctx.roundRect = oR; delete r.drawCableTag; }
        return { texts, tags, arcs, pills };
    };
    const hadFlag = Object.prototype.hasOwnProperty.call(l, 'showDataCableTags');
    const prevFlag = l.showDataCableTags, prevPattern = l.flowPattern;
    const prevMode = r.viewMode, prevExport = r.exportMode;
    if (opts.flag !== undefined) l.showDataCableTags = opts.flag;
    if (opts.pattern) l.flowPattern = opts.pattern;
    let interactive, exported;
    try {
        r.viewMode = 'data-flow';
        r.exportMode = false;
        interactive = grab();
        r.exportMode = true;
        exported = grab();
    } finally {
        if (opts.flag !== undefined) {
            if (hadFlag) l.showDataCableTags = prevFlag; else delete l.showDataCableTags;
        }
        if (opts.pattern) l.flowPattern = prevPattern;
        r.exportMode = prevExport;
        r.viewMode = prevMode;
        r.render();
    }
    const b = r.getLayerBounds(l);
    const labels = {};
    for (const [n] of ids.ports) {
        labels[n] = {primary: app.getPortLabelText(l, n, 'primary'),
                     ret: app.getPortLabelText(l, n, 'return')};
    }
    const readings = ids.ports.map(([n]) => {
        const c = app.dataPortCableForScreen(l, n);
        const bk = app.dataPortBackupCableForScreen(l, n);
        return [n, c ? c.text : null, bk ? bk.text : null];
    });
    return { interactive, exported, labels, readings,
             bounds: {left: b.x, right: b.x + b.width, top: b.y, bottom: b.y + b.height} };
}"""

DATA_TAG_COLORS = {'fill': '#10202c', 'rim': '#8fd0ff', 'ink': '#cfeaff'}


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
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['ports'] == [[i, ids['cardId'], i] for i in range(1, 7)], (
        f'fixture: WALL must take card SR sockets 1-6 (box A\'s): {ids}')
    assert ids['backs'] == [[ids['backupId'], i] for i in range(1, 7)], (
        f'fixture: port n must return on the backup card\'s socket n (box B\'s): {ids}')
    assert errors == [], errors
    yield pg, ids
    context.close()


def _frame(pg, ids, **opts):
    return pg.evaluate(FRAME_JS, [ids, opts])


def _marker(frame_pass, label):
    """The centre a marker's label was painted at.

    A label with no space stacks at its seams since the 2026-09-07 rule -
    "SR-1R" is painted as "SR-" over "1R", two fillText calls at one x -
    so the pieces at a single x, read down the column, join back to the
    label and the block's centre is their mean y (_fillWrappedLabel spaces
    the lines symmetrically about it). A label that fits on one line is
    that same reading with one piece.
    """
    hits = [t for t in frame_pass['texts'] if t['t'] == label]
    if len(hits) == 1:
        return hits[0]
    assert not hits, (label, hits)
    columns = {}
    for t in frame_pass['texts']:
        columns.setdefault(round(t['x'], 6), []).append(t)
    for x, column in columns.items():
        column.sort(key=lambda t: t['y'])
        for i in range(len(column)):
            for j in range(i + 2, len(column) + 1):
                run = column[i:j]
                joined = ''.join(t['t'] for t in run)
                if joined == label:
                    return {'t': label, 'x': x,
                            'y': sum(t['y'] for t in run) / len(run)}
                if not label.startswith(joined):
                    break
    raise AssertionError(
        f'{label!r} was painted neither whole nor as a stack: '
        f'{sorted({t["t"] for t in frame_pass["texts"]})}')


def _disc_radius(frame_pass, x, y):
    """The radius of the disc drawn at a marker's centre."""
    rads = {a['r'] for a in frame_pass['arcs'] if abs(a['x'] - x) < 1e-6 and abs(a['y'] - y) < 1e-6}
    assert len(rads) == 1, (x, y, rads)
    return rads.pop()


def _tag_beside(frame_pass, text, x, y, radius):
    """The one drawCableTag call for `text` hanging off the circle at (x, y):
    its `x` is the circle's right edge, or its left edge when it flipped."""
    hits = [t for t in frame_pass['tags'] if t['text'] == text and abs(t['y'] - y) < 1e-6]
    assert len(hits) == 1, (text, (x, y), hits)
    tag = hits[0]
    edge = x - radius if tag['flip'] else x + radius
    assert abs(tag['x'] - edge) < 1e-6, (text, tag, x, radius)
    return tag


def _check_pass(frame, frame_pass):
    """Six primaries wear "SR Primary"; six returns wear "SR Backup", port 1's
    "SR Backup +25'" (its backup socket's extension). Each tag hangs off its
    own marker, in the data tag's colours, and every line it wraps to is
    painted."""
    labels = frame['labels']
    want = {'SR Primary': 6, 'SR Backup': 5, "SR Backup +25'": 1}
    got = {}
    for t in frame_pass['tags']:
        got[t['text']] = got.get(t['text'], 0) + 1
    assert got == want, got
    painted = [t['t'] for t in frame_pass['texts']]
    for n in range(1, 7):
        lab = labels[str(n)]
        p = _marker(frame_pass, lab['primary'])
        rt = _marker(frame_pass, lab['ret'])
        assert (p['x'], p['y']) != (rt['x'], rt['y']), (n, p, rt)
        prim = _tag_beside(frame_pass, 'SR Primary', p['x'], p['y'],
                           _disc_radius(frame_pass, p['x'], p['y']))
        back = _tag_beside(frame_pass, "SR Backup +25'" if n == 1 else 'SR Backup',
                           rt['x'], rt['y'], _disc_radius(frame_pass, rt['x'], rt['y']))
        for tag in (prim, back):
            assert tag['colors'] == DATA_TAG_COLORS, tag
            for line in tag['lines']:
                assert line in painted, (tag, painted)
    # the pills: one per tag, every one inside the screen
    assert len(frame_pass['pills']) == len(frame_pass['tags'])
    b = frame['bounds']
    for pill in frame_pass['pills']:
        assert pill['left'] >= b['left'] - 1e-6 and pill['right'] <= b['right'] + 1e-6, (pill, b)
        assert pill['top'] >= b['top'] - 1e-6 and pill['bottom'] <= b['bottom'] + 1e-6, (pill, b)


def test_the_readings_say_both_ends(page):
    """dataPortCableForScreen is the primary socket's cable; the new
    dataPortBackupCableForScreen is the BACKUP socket's - box B's snake, with
    the extension on port 1's return socket - exactly what _dataPortCableOn
    gives, no second string built."""
    pg, ids = page
    frame = _frame(pg, ids)
    assert frame['readings'] == [
        [1, 'SR Primary', "SR Backup +25'"]] + [[n, 'SR Primary', 'SR Backup'] for n in range(2, 7)], frame['readings']
    shape = pg.evaluate("""(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === ids.id);
        const b = app.dataPortBackupCableForScreen(l, 1);
        return [b.kind, b.snake.name, b.ext, b.owner.kind, b.owner.id, b.text,
                app.dataPortBackupCableForScreen(l, 99)];
    }""", ids)
    assert shape == ['snake', 'SR Backup', 25, 'cvt', ids['boxB'], "SR Backup +25'", None], shape


def test_both_markers_wear_their_tags_on_screen_and_in_export(page):
    """Off (the default): no tag on either marker, on screen or in
    exportMode. On: "SR Primary" beside every primary marker and "SR Backup"
    ("SR Backup +25'" on port 1) beside every RETURN marker, both passes
    alike."""
    pg, ids = page
    off = _frame(pg, ids)
    assert off['interactive']['tags'] == [] and off['exported']['tags'] == [], off
    assert not [t for t in off['interactive']['texts'] if t['t'].startswith('SR Primary') or t['t'].startswith('SR Backup')]
    on = _frame(pg, ids, flag=True)
    _check_pass(on, on['interactive'])
    _check_pass(on, on['exported'])
    # the export pass paints the same tags at the same places
    key = lambda t: (t['text'], round(t['x'], 3), round(t['y'], 3), t['flip'])
    assert sorted(map(key, on['exported']['tags'])) == sorted(map(key, on['interactive']['tags']))
    # and the flag left alone afterwards
    assert pg.evaluate("(ids) => window.app.project.layers.find(x => x.id === ids.id).showDataCableTags", ids) in (None, False)


def test_a_port_with_no_backup_draws_one_tag_only(page):
    """Redundancy off on the processor: no port has a backup, the reading is
    null, and each port draws its primary tag alone - unchanged from before.
    Back on, the return tags come back."""
    pg, ids = page
    pg.evaluate("""async (ids) => {
        const app = window.app;
        await fetch(`/api/processors/${ids.procId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({redundancy: false})});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
    }""", ids)
    pg.wait_for_timeout(600)
    try:
        frame = _frame(pg, ids, flag=True)
        assert frame['readings'] == [[n, 'SR Primary', None] for n in range(1, 7)], frame['readings']
        for frame_pass in (frame['interactive'], frame['exported']):
            assert [t['text'] for t in frame_pass['tags']] == ['SR Primary'] * 6, frame_pass['tags']
            for n in range(1, 7):
                p = _marker(frame_pass, frame['labels'][str(n)]['primary'])
                _tag_beside(frame_pass, 'SR Primary', p['x'], p['y'],
                            _disc_radius(frame_pass, p['x'], p['y']))
    finally:
        pg.evaluate("""async (ids) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({redundancy: true})});
            await app.refreshProcessors();
            await app.refreshPortAssignment();
            app.renderLayers();
        }""", ids)
        pg.wait_for_timeout(600)
    frame = _frame(pg, ids, flag=True)
    assert frame['readings'][0] == [1, 'SR Primary', "SR Backup +25'"], frame['readings']
    _check_pass(frame, frame['interactive'])


def _flip_expected(tag, x, radius, b):
    """The primary tag's rule, verbatim: flip when the tag would leave the
    screen on the right and fits on the left."""
    return (x + radius + tag['w'] > b['right']
            and x - radius - tag['w'] >= b['left'])


def test_a_return_marker_at_the_right_edge_hangs_its_tag_inside(page):
    """The flip rule, on the return marker: a top-right, row-first flow ends
    every port's run in the right-hand column, so its return marker sits
    there and its tag would leave the screen - it hangs off the LEFT edge
    instead, the pill left of the marker and inside the screen, while the
    primaries (in the left-hand column) keep theirs on the right. In the
    default flow (runs end in the left-hand column) no return tag flips.
    Same in exportMode."""
    pg, ids = page
    frame = _frame(pg, ids, flag=True, pattern='tr-h')
    for frame_pass in (frame['interactive'], frame['exported']):
        _check_pass(frame, frame_pass)
        b = frame['bounds']
        for n in range(1, 7):
            lab = frame['labels'][str(n)]
            rt = _marker(frame_pass, lab['ret'])
            rad = _disc_radius(frame_pass, rt['x'], rt['y'])
            tag = _tag_beside(frame_pass, "SR Backup +25'" if n == 1 else 'SR Backup',
                              rt['x'], rt['y'], rad)
            pill = frame_pass['pills'][frame_pass['tags'].index(tag)]
            # the run ends in the right-hand column and the tag would not fit
            assert rt['x'] + rad + tag['w'] > b['right'], (n, tag, rt, rad, b)
            assert _flip_expected(tag, rt['x'], rad, b) is True, (n, tag, rt, rad, b)
            assert tag['flip'] is True, (n, tag, rt, b)
            assert pill['right'] <= rt['x'] - rad + 1e-6, (n, pill, rt, rad)
            assert pill['left'] >= b['left'] - 1e-6, (n, pill, b)
            p = _marker(frame_pass, lab['primary'])
            prad = _disc_radius(frame_pass, p['x'], p['y'])
            prim = _tag_beside(frame_pass, 'SR Primary', p['x'], p['y'], prad)
            assert prim['flip'] is _flip_expected(prim, p['x'], prad, b), (n, prim, p, b)
    # the default flow: every return marker sits in the left-hand column,
    # nothing flips, and the rule agrees with what was drawn
    plain = _frame(pg, ids, flag=True)
    b = plain['bounds']
    for frame_pass in (plain['interactive'], plain['exported']):
        for n in range(1, 7):
            rt = _marker(frame_pass, plain['labels'][str(n)]['ret'])
            rad = _disc_radius(frame_pass, rt['x'], rt['y'])
            tag = _tag_beside(frame_pass, "SR Backup +25'" if n == 1 else 'SR Backup',
                              rt['x'], rt['y'], rad)
            assert tag['flip'] is False and _flip_expected(tag, rt['x'], rad, b) is False, (n, tag, rt, b)
    # the pattern was put back
    assert pg.evaluate("(ids) => window.app.project.layers.find(x => x.id === ids.id).flowPattern", ids) != 'tr-h'
