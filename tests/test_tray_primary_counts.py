"""The processor tray counts primaries only where backups ride on their own.

The owner, 2026-11-04, off a beta.5 screenshot of five SX40s set to "Loops
A to B, C to D": "in examples where processors or breakout boxes are
grouped, we do not need to account for the backups in the 18 out of 20, 12
out of 20, 10 out of 20s that show here. They can still account for them in
other places, but on this screen we're drawing in the primaries and the
backups are automatic, so we don't need to count the backups."

His rulings:

* a looped pair counts primaries out of the ports that can carry one, one
  box's worth: "XD CL A <-> CL B 18/20" (9 primaries and their 9 automatic
  backups) reads 9/10, read off the real split, never a halving;
* the unit's header follows the same rule: "SX40 36/40" reads 18/20;
* every shape where the backups ride automatically does the same (SX40
  loops, sequential, halves, 1:1 partners, a copy OPT set to Backup); a
  return picked by hand (per-port manual) is not automatic and stays
  counted, and a whole backup processor never had sockets on the tray;
* ONLY the tray changes: the binder's Processor table, the processor gear
  and the server's summary keep counting every socket taken
  (socketsTaken, test_socket_counts).

Run locally:
    PYTHONIOENCODING=utf-8 <venv python> -m pytest \
        tests/test_tray_primary_counts.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SRC = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Every rig on one project, each on its own processor and its own wall(s):
#   LOOPS  SX40, A to B and C to D: one wall, 6 primaries on A, 5 on C (the owner's
#          "12/20" and "10/20" rows, and his 22/40 header)
#   ODD    SX40, A to B and C to D: 9 primaries on A ("18/20")
#   PAIRA  SX40, A to B only: 12 primaries, A 1-10 then C 1-2
#   PLAIN  SX40 with redundancy off: 11 primaries
#   MAIN / PART  MX20 1:1 to a second MX20: 3 primaries
#   SEQ    MX20 sequential: 2 primaries
#   MAN    MX20 per-port manual, port 1 backed up on port 4: 2 primaries
#   WHOLE  MX20 with a backup processor: 3 primaries
#   COPY   H9, H_4xfiber in Backup, CVT4K-S on OPT 1-2 + its backup on
#          OPT 3-4: 9 primaries
#   NONE   MX20 with redundancy off: 3 primaries
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    const send = async (url, method, body) => {
        const r = await fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)});
        const data = await r.json();
        if (!r.ok) throw new Error(`${method} ${url}: ${JSON.stringify(data)}`);
        return data;
    };
    const walls = {};
    let oy = 0;
    const wall = async (name, platform) => {
        const r = await send('/api/layer/add', 'POST', {name, columns: 12,
            rows: 30, cabinet_width: 200, cabinet_height: 200,
            offset_x: 0, offset_y: oy});
        oy += 7000;
        await send(`/api/layer/${r.id}`, 'PUT', {processorType: platform});
        walls[name] = r.id;
    };
    for (const n of ['L1', 'O1', 'P1', 'X1']) await wall(n, 'brompton');
    for (const n of ['M1', 'S1', 'N1', 'W1', 'Z1']) await wall(n, 'novastar-coex-1g');
    await wall('C1', 'novastar-armor');
    const units = {};
    const unit = async (name, deviceId, body) => {
        const added = await send('/api/processors', 'POST', {deviceId});
        const proc = added.resolved[added.resolved.length - 1];
        await send(`/api/processors/${proc.id}`, 'PUT', Object.assign({name}, body || {}));
        const card = proc.slots.map(s => s.card).find(Boolean);
        units[name] = {procId: proc.id, cardId: card ? card.id : null};
        return units[name];
    };
    await unit('LOOPS', 'brompton-sx40', {redundancy: true, redundancyPairs: ['A', 'C']});
    await unit('ODD', 'brompton-sx40', {redundancy: true, redundancyPairs: ['A', 'C']});
    await unit('PAIRA', 'brompton-sx40', {redundancy: true, redundancyPairs: ['A']});
    await unit('PLAIN', 'brompton-sx40', {redundancy: false});
    const main = await unit('MAIN', 'novastar-mx20', {redundancy: true});
    const part = await unit('PART', 'novastar-mx20', {redundancy: false});
    await send(`/api/processors/${main.procId}/cards/${main.cardId}`, 'PUT',
               {backupCardId: part.cardId});
    const seq = await unit('SEQ', 'novastar-mx20', {redundancy: true});
    await send(`/api/processors/${seq.procId}/cards/${seq.cardId}`, 'PUT',
               {redundancyMode: 'sequential'});
    const man = await unit('MAN', 'novastar-mx20', {redundancy: true});
    await send(`/api/processors/${man.procId}/cards/${man.cardId}`, 'PUT',
               {redundancyMode: 'manual'});
    await send(`/api/processors/${man.procId}/cards/${man.cardId}/ports/1`, 'PUT',
               {backup: {cardId: man.cardId, port: 4}});
    await unit('WHOLE', 'novastar-mx20', {backupUnit: {name: 'WHOLE BU'}});
    const h9 = await unit('COPY', 'novastar-h9', {});
    let st = await send(`/api/processors/${h9.procId}/slots/0`, 'PUT',
                        {deviceId: 'novastar-card-h-4xfiber'});
    const h4 = st.resolved.find(p => p.id === h9.procId).slots[0].card.id;
    units.COPY.cardId = h4;
    await send(`/api/processors/${h9.procId}/cards/${h4}`, 'PUT', {mode: 'backup'});
    await send(`/api/processors/${h9.procId}/cards/${h4}/cvts`, 'POST',
               {deviceId: 'novastar-cvt4k-s'});
    await unit('NONE', 'novastar-mx20', {redundancy: false});
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
    const place = async (name, cardId, body) => {
        const before = JSON.stringify(app._assignment && app._assignment.occupancy);
        await app._assignmentRequest('/api/port-assignments/place-overflow',
            'POST', Object.assign({layerId: String(walls[name]), cardId}, body));
        if (JSON.stringify(app._assignment && app._assignment.occupancy) === before) {
            throw new Error(`placing ${name} changed nothing: ${app._assignmentError || ''}`);
        }
    };
    await place('L1', units.LOOPS.cardId, {lastIndex: 5});
    // the same wall's next five ports onto C (one wall: one canvas span)
    await place('L1', units.LOOPS.cardId, {firstPort: 21, lastPort: 30, lastIndex: 10});
    await place('O1', units.ODD.cardId, {lastIndex: 8});
    await place('P1', units.PAIRA.cardId, {lastIndex: 11});
    await place('X1', units.PLAIN.cardId, {lastIndex: 10});
    await place('M1', units.MAIN.cardId, {lastIndex: 2});
    await place('S1', units.SEQ.cardId, {lastIndex: 1});
    await place('N1', units.MAN.cardId, {lastIndex: 1});
    await place('W1', units.WHOLE.cardId, {lastIndex: 2});
    await place('C1', units.COPY.cardId, {lastIndex: 8});
    await place('Z1', units.NONE.cardId, {lastIndex: 2});
    app.resetHistory('Tray Count Seed');
    // the boxes, by unit, in card order
    const tree = app._processorsResolved;
    for (const u of Object.values(units)) {
        const proc = tree.find(p => p.id === u.procId);
        const card = proc.slots.map(s => s.card).find(c => c && c.id === u.cardId);
        u.boxes = ((card && card.cvts) || []).map(b => b.id);
    }
    const need = {};
    for (const l of app.project.layers) need[l.name] = app.getLayerPortsRequired(l);
    return {walls, units, need};
}"""

# A header's glance by its dock key: the n/N text, its tooltip and the fill
# line's width; null text where the header draws no count.
GLANCE_JS = """(key) => {
    const head = document.querySelector(`[data-hwdock="${key}"]`);
    if (!head) return null;
    const use = head.querySelector(':scope > .hw-dock-unit-use');
    const bar = head.querySelector(':scope > .hw-dock-headbar > i');
    return {text: use ? use.textContent : null,
            title: use ? use.title : null,
            barW: bar ? parseFloat(bar.style.width) : null,
            over: !!(bar && bar.classList.contains('hw-dock-bar-over'))};
}"""

# What the server counts (every socket taken, returns included) for a card
# or one box - the binder's number, unchanged.
SOCKETS_JS = """([cardId, boxId]) => window.app.socketsTaken(cardId, boxId || undefined)"""

# The binder's Processor/Cards table cells and the processor gear's text for
# one processor - the readers that must NOT follow the tray.
READERS_JS = """(procId) => {
    const app = window.app;
    const proc = (app._processorsResolved || []).find(p => p.id === procId);
    const cards = (proc.slots || []).filter(s => s && s.card)
        .map(s => ({slot: s.index, card: s.card}));
    const seen = [];
    app._bTableLines = (book, spec) => { seen.push(spec); return []; };
    app._bKvLines = () => [];
    app._bPullLines = () => [];
    try {
        app._bProcessorBlocks({list: {hardware: []}}, proc, cards);
    } finally {
        delete app._bTableLines;
        delete app._bKvLines;
        delete app._bPullLines;
    }
    const tables = seen.map(s => ({title: s.title,
        rows: (s.rows || []).map(r => (r.cells || []).map(c => String(c)))}));
    const gear = app._buildProcGearContent(proc);
    const need = {};
    for (const l of app.project.layers) need[l.name] = app.getLayerPortsRequired(l);
    return {tables, gear: gear ? gear.textContent : null, need,
            issues: JSON.stringify((app._assignment || {}).issues || [])};
}"""


@pytest.fixture(scope="module")
def tray(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    # Real Windows dialogs would pop on the desktop: answer them cancelled.
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"ok": false, "cancelled": true, "unavailable": false}'))
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true",
                         timeout=20000)
    pg.wait_for_timeout(800)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(800)
    yield pg, ids, errors
    context.close()


def glance(page, key):
    return page.evaluate(GLANCE_JS, key)


def card_glance(page, ids, name):
    return glance(page, f"card-{ids['units'][name]['cardId']}")


def box(ids, name, i):
    return ids['units'][name]['boxes'][i]


def assert_bar(g, taken, of):
    assert g and g['text'] == f'{taken}/{of}', g
    assert abs(g['barW'] - 100 * taken / of) < 0.5, g
    assert not g['over'], g


# ── SX40 loops ────────────────────────────────────────────────────────────

def test_the_owners_sx40_reads_its_primaries_over_twenty(tray):
    """6 on A and 5 on C with both loops: the header read 22/40 and reads
    11/20; the strips read 6/10 and 5/10 (were 12/20 and 10/20)."""
    page, ids, _ = tray
    assert ids['need']['L1'] >= 11, ids['need']
    head = card_glance(page, ids, 'LOOPS')
    assert_bar(head, 11, 20)
    assert head['title'] == ('11 of 20 primary ports used; the 20 backup '
                             'sockets fill on their own and are not counted here.'), head
    a_b = glance(page, f"loop-{box(ids, 'LOOPS', 0)}")
    c_d = glance(page, f"loop-{box(ids, 'LOOPS', 2)}")
    assert_bar(a_b, 6, 10)
    assert_bar(c_d, 5, 10)
    assert a_b['title'].startswith('6 of 10 primary ports used; backups ride on '), a_b
    assert 'B' in a_b['title'].split('ride on ')[1], a_b


def test_an_odd_count_reads_exactly_not_a_halving(tray):
    """9 primaries on A: the owner's "18/20" strip reads 9/10, C to D 0/10,
    the unit 9/20."""
    page, ids, _ = tray
    assert ids['need']['O1'] >= 9, ids['need']
    assert_bar(card_glance(page, ids, 'ODD'), 9, 20)
    assert_bar(glance(page, f"loop-{box(ids, 'ODD', 0)}"), 9, 10)
    assert_bar(glance(page, f"loop-{box(ids, 'ODD', 2)}"), 0, 10)


def test_the_rows_inside_a_loop_strip(tray):
    """Open, the near box's row counts its primaries; the far box carries
    nothing but automatic backups, so its row draws no count."""
    page, ids, _ = tray
    near = glance(page, f"box-{box(ids, 'ODD', 0)}")
    far = glance(page, f"box-{box(ids, 'ODD', 1)}")
    assert_bar(near, 9, 10)
    assert near['title'].startswith('9 of 10 primary ports used; backups ride on '), near
    assert far and far['text'] is None and far['barW'] is None, far


def test_an_unlooped_trunk_is_a_plain_primary(tray):
    """A to B only: B is the backup, C and D carry primaries. 12 primaries
    land on A 1-10 and C 1-2 - 12 of the 30 sockets that can carry one."""
    page, ids, _ = tray
    assert ids['need']['P1'] >= 12, ids['need']
    assert_bar(card_glance(page, ids, 'PAIRA'), 12, 30)
    assert_bar(glance(page, f"loop-{box(ids, 'PAIRA', 0)}"), 10, 10)
    assert_bar(glance(page, f"box-{box(ids, 'PAIRA', 2)}"), 2, 10)
    assert_bar(glance(page, f"box-{box(ids, 'PAIRA', 3)}"), 0, 10)


def test_the_server_count_under_the_tray_is_unchanged(tray):
    """socketsTaken - what the binder prints - still counts the returns."""
    page, ids, _ = tray
    loops = ids['units']['LOOPS']
    assert page.evaluate(SOCKETS_JS, [loops['cardId'], None]) == \
        {'taken': 22, 'of': 40}
    assert page.evaluate(SOCKETS_JS, [loops['cardId'], loops['boxes'][1]]) == \
        {'taken': 6, 'of': 10}


# ── NovaStar shapes ───────────────────────────────────────────────────────

def test_a_1to1_partner_draws_no_count_and_the_main_is_unchanged(tray):
    page, ids, _ = tray
    assert_bar(card_glance(page, ids, 'MAIN'), 3, 6)
    part = card_glance(page, ids, 'PART')
    assert part and part['text'] is None and part['barW'] is None, part
    # the server still counts the partner's three lit returns
    assert page.evaluate(SOCKETS_JS, [ids['units']['PART']['cardId'], None]) == \
        {'taken': 3, 'of': 6}


def test_sequential_counts_the_odd_ports(tray):
    page, ids, _ = tray
    g = card_glance(page, ids, 'SEQ')
    assert_bar(g, 2, 3)
    assert 'the 3 backup sockets fill on their own' in g['title'], g


def test_a_hand_picked_backup_keeps_todays_count(tray):
    """Per-port manual: the return on 4 is the user's pick, not automatic,
    so the header reads exactly what socketsTaken reads (3/6)."""
    page, ids, _ = tray
    man = ids['units']['MAN']
    assert page.evaluate(SOCKETS_JS, [man['cardId'], None]) == {'taken': 3, 'of': 6}
    g = card_glance(page, ids, 'MAN')
    assert_bar(g, 3, 6)
    assert g['title'] == '3 of 6 ports used.', g


def test_a_backup_processor_adds_no_socket_to_count(tray):
    page, ids, _ = tray
    assert_bar(card_glance(page, ids, 'WHOLE'), 3, 6)


def test_a_copy_opt_backup_box_counts_one_box(tray):
    """H_4xfiber in Backup: the CVT4K-S on OPT 3-4 backs up the one on OPT
    1-2. Nine primaries: the strip read 18/32, it reads 9/16; the far row
    draws no count; the card header (which never held the backup box's
    sockets) is unchanged."""
    page, ids, _ = tray
    assert ids['need']['C1'] >= 9, ids['need']
    copy = ids['units']['COPY']
    assert len(copy['boxes']) == 2, copy
    server = page.evaluate(SOCKETS_JS, [copy['cardId'], None])
    head = card_glance(page, ids, 'COPY')
    assert head['text'] == f"{server['taken']}/{server['of']}", (head, server)
    assert server['taken'] == 9, server
    assert_bar(glance(page, f"loop-{copy['boxes'][0]}"), 9, 16)
    far = glance(page, f"box-{copy['boxes'][1]}")
    assert far and far['text'] is None, far


# ── no redundancy: nothing changes ────────────────────────────────────────

def test_no_redundancy_reads_what_it_always_read(tray):
    page, ids, _ = tray
    plain = ids['units']['PLAIN']
    assert_bar(card_glance(page, ids, 'PLAIN'), 11, 40)
    texts = [glance(page, f'box-{b}')['text'] for b in plain['boxes']]
    assert texts == ['10/10', '1/10', '0/10', '0/10'], texts
    for b in [None] + plain['boxes']:
        s = page.evaluate(SOCKETS_JS, [plain['cardId'], b])
        g = glance(page, f'box-{b}' if b else f"card-{plain['cardId']}")
        assert g['text'] == f"{s['taken']}/{s['of']}", (b, g, s)
        assert g['title'] == f"{s['taken']} of {s['of']} ports used.", g
    assert_bar(card_glance(page, ids, 'NONE'), 3, 6)


# ── only the tray reads the new count ─────────────────────────────────────

def test_the_binder_gear_and_readouts_do_not_follow_the_tray(tray):
    """The binder's tables, the processor gear, the Ports required readout
    and the assignment issues come out the same with the tray's count
    swapped for nonsense - none of them read it - and the binder still
    prints the redundant SX40 as every socket taken."""
    page, ids, errors = tray
    before = {n: page.evaluate(READERS_JS, u['procId'])
              for n, u in ids['units'].items()}
    page.evaluate("""() => {
        window.__trayCount = window.app.trayPrimaryCount;
        window.app.trayPrimaryCount = () => ({taken: 99, of: 999, backups: 7});
    }""")
    try:
        after = {n: page.evaluate(READERS_JS, u['procId'])
                 for n, u in ids['units'].items()}
    finally:
        page.evaluate("() => { window.app.trayPrimaryCount = window.__trayCount; }")
    assert before == after
    procs = [t for t in before['LOOPS']['tables'] if t['title'] == 'Processor']
    assert procs and any('22 / 40' in cell for row in procs[0]['rows']
                         for cell in row), procs
    assert not errors, errors


def test_a_loop_strip_whose_near_box_has_no_model_draws(tray):
    """A loop pair whose near box carries no deviceName still draws its
    strip: the header falls back to the far box's model, then to "Box"
    (the strip's builder once read a `far` that no longer existed and
    threw, taking the whole tray with it)."""
    page, ids, errors = tray
    out = page.evaluate("""([procId, nearId, farId]) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === procId);
        const boxes = proc.slots.flatMap(s => (s.card && s.card.cvts) || []);
        const near = boxes.find(b => b.id === nearId);
        const far = boxes.find(b => b.id === farId);
        const saved = [near.deviceName, far.deviceName];
        const read = () => {
            let thrown = null;
            try { app.renderHardwareDock(); } catch (e) { thrown = String(e); }
            const head = document.querySelector(`[data-lrd-sec="hwdock-box-${nearId}"]`);
            const name = head && head.querySelector('.hw-dock-unit-name');
            return { thrown, strip: !!(head && head.parentElement.classList.contains('hw-dock-loop')),
                     model: name ? name.textContent : null };
        };
        try {
            near.deviceName = '';
            const farOnly = read();
            far.deviceName = '';
            const neither = read();
            return { saved, farOnly, neither };
        } finally {
            [near.deviceName, far.deviceName] = saved;
            app.renderHardwareDock();
        }
    }""", [ids['units']['ODD']['procId'], box(ids, 'ODD', 0), box(ids, 'ODD', 1)])
    assert out['saved'][1], out
    assert out['farOnly'] == {'thrown': None, 'strip': True, 'model': out['saved'][1]}, out
    assert out['neither'] == {'thrown': None, 'strip': True, 'model': 'Box'}, out
    assert not errors, errors


def test_only_the_tray_calls_the_primary_count():
    """The binder, gear, pull list and warnings keep socketsTaken: the new
    count is read in app-dock.js alone."""
    callers = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith('.js') or name == 'app-port-assignment.js':
            continue
        with open(os.path.join(SRC, name), encoding='utf-8') as fh:
            if 'trayPrimaryCount(' in fh.read():
                callers.append(name)
    assert callers == ['app-dock.js'], callers
