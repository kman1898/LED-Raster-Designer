"""IP addresses on the processors, in the app and on the binder (owner,
2026-11-09: "add to the processors the ability to IP addresses and that
would be represented on the binder").

In the app: the processor's gear has a NETWORK block - the unit's IP,
subnet, gateway and note, its backup unit's under them, and the show's
subnet and gateway, which fill any unit's blank ones (in grey). Each field
is one request and one undo step. A bad entry is marked red with its reason
and stored as typed; two units on one IP are named in the gear, in the Data
tray's warning strip and by the header's IP turning red. They survive a
reload and a save and reopen.

On the binder: each processor's sheet has a NETWORK table, each screen's
Data sheet its processor's IP in FACTS, and a NETWORK page after the
processor sheets lists every unit in order - all only once a unit has an
IP, empty cells blank, never for a single screen or with the tick off.

Run locally:
    python -m pytest tests/test_processor_network.py -v --browser chromium
"""
import base64
import json
import os

import pytest

from conftest import open_app  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder import SEED_JS  # noqa: E402

SCRATCH = os.environ.get('LRD_NETWORK_SHOTS')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_BACKUP_JS = """async (pid) => {
    const app = window.app;
    await app._processorRequest(`/api/processors/${pid}`, 'PUT', { backupUnit: {} });
    app.resetHistory('Network Seed');
}"""

OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    const pop = document.getElementById('hw-gear-popover');
    const open = !!(pop && pop.style.display !== 'none'
        && window.app._hwPopover && window.app._hwPopover.id === popId);
    if (!open) gear.click();
    const after = document.getElementById('hw-gear-popover');
    return !!(after && after.style.display !== 'none');
}"""

STATE_JS = """(pid) => {
    const app = window.app;
    const raw = (app.project.processors || []).find(p => p.id === pid) || {};
    return { main: raw.network || null, bu: (raw.backupUnit || {}).network || null,
             show: app.project.network || null,
             action: (app.history[app.historyIndex] || {}).action || null,
             index: app.historyIndex };
}"""

SHOW = {"sheet": "tabloid", "palette": "colour", "sides": {"power": True, "data": True},
        "scope": {"kind": "show"}, "cover": True, "pull": True, "hardware": True,
        "fiber": True, "network": True, "titleBlock": True}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    body = json.dumps({'ok': False, 'cancelled': True})
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}',
                      lambda route: route.fulfill(status=200, content_type='application/json', body=body))
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    open_app(pg, e2e_server)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    pg.evaluate(SEED_BACKUP_JS, ids['procId'])
    pg.wait_for_timeout(400)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _shot(pg, locator, name):
    """A picture for the owner, only where a scratch folder is named."""
    if SCRATCH:
        os.makedirs(SCRATCH, exist_ok=True)
        locator.screenshot(path=os.path.join(SCRATCH, name))


def _gear(pg, pid):
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{pid}')
    pg.wait_for_selector(f'#hw-gear-popover [data-lrd-field="processor-network-{pid}"]')


def _type(pg, key, value):
    field = pg.locator(f'#hw-gear-popover [data-lrd-field="{key}"]')
    field.click()
    field.fill(value)
    pg.keyboard.press('Enter')


def _state(pg, pid):
    return pg.evaluate(STATE_JS, pid)


def _wait(pg, pid, js):
    pg.wait_for_function(f"""(pid) => {{
        const app = window.app;
        const raw = (app.project.processors || []).find(p => p.id === pid) || {{}};
        const main = raw.network || {{}}, bu = (raw.backupUnit || {{}}).network || {{}};
        const show = app.project.network || {{}};
        return {js};
    }}""", arg=pid, timeout=8000)
    pg.wait_for_timeout(150)


def _clear_all(pg, pid):
    """Every network field off, straight through the routes, the history reset."""
    pg.evaluate("""async (pid) => {
        const app = window.app;
        const blank = {ip: '', subnet: '', gateway: '', note: ''};
        await app._processorRequest(`/api/processors/${pid}`, 'PUT', {network: blank, backupNetwork: blank});
        await app._processorRequest('/api/processors/network', 'PUT', {subnet: '', gateway: ''});
        app.resetHistory('Network Clear');
    }""", pid)
    pg.wait_for_timeout(300)


# ── the processor's gear ────────────────────────────────────────────────

def test_main_and_backup_ips_are_typed_in_the_gear_one_undo_step_each(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    _gear(pg, pid)
    # both units have their four fields; the names say which is which
    names = pg.evaluate("""() => [...document.querySelectorAll('#hw-gear-popover .hw-pop-net-name')]
                           .map(e => e.textContent)""")
    assert names == ['H9', 'H9 BU (backup)', 'Every processor'], names
    start = _state(pg, pid)['index']
    _type(pg, f'processor-net-ip-{pid}', '10.0.0.10')
    _wait(pg, pid, "main.ip === '10.0.0.10'")
    _type(pg, f'processor-bu-net-ip-{pid}', '10.0.0.11')
    _wait(pg, pid, "bu.ip === '10.0.0.11'")
    _type(pg, f'processor-net-note-{pid}', 'control laptop port 2')
    _wait(pg, pid, "main.note === 'control laptop port 2'")
    st = _state(pg, pid)
    assert st['main'] == {'ip': '10.0.0.10', 'note': 'control laptop port 2'}, st
    assert st['bu'] == {'ip': '10.0.0.11'}, st
    assert st['index'] == start + 3 and st['action'] == 'Edit Processor Note', st
    actions = pg.evaluate("(n) => window.app.history.slice(-n).map(h => h.action)", 3)
    assert actions == ['Edit Processor IP', 'Edit Backup Processor IP', 'Edit Processor Note']
    # the same value again is no step
    _type(pg, f'processor-net-ip-{pid}', '10.0.0.10 ')
    pg.wait_for_timeout(600)
    assert _state(pg, pid)['index'] == start + 3
    # the header shows the IP
    assert pg.locator(f'[data-lrd-field="processor-ip-pill-{pid}"]').text_content() == '10.0.0.10'
    _shot(pg, pg.locator('#hw-gear-popover'), 'network-gear.png')
    # one undo per field, and the server follows
    pg.evaluate("() => window.app.undo()")
    _wait(pg, pid, "!main.note")
    st = _state(pg, pid)
    assert st['main'] == {'ip': '10.0.0.10'} and st['bu'] == {'ip': '10.0.0.11'}, st
    pg.evaluate("() => window.app.undo()")
    _wait(pg, pid, "!bu.ip")
    served = pg.evaluate("(pid) => fetch('/api/processors').then(r => r.json()).then(d => "
                         "d.processors.find(p => p.id === pid))", pid)
    assert served['network'] == {'ip': '10.0.0.10'} and 'network' not in served['backupUnit'], served
    pg.evaluate("() => window.app.redo()")
    _wait(pg, pid, "bu.ip === '10.0.0.11'")
    # the gear, opened again, reads the stored values
    _gear(pg, pid)
    assert pg.locator(f'[data-lrd-field="processor-bu-net-ip-{pid}"]').input_value() == '10.0.0.11'
    assert pg.locator(f'[data-lrd-field="processor-net-note-{pid}"]').input_value() == ''
    pg.keyboard.press('Escape')
    assert ids['errors'] == []


def test_the_shows_subnet_and_gateway_fill_blank_units_and_a_unit_can_override(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    _gear(pg, pid)
    _type(pg, 'show-net-subnet', '255.255.255.0')
    _wait(pg, pid, "show.subnet === '255.255.255.0'")
    _type(pg, 'show-net-gateway', '10.0.0.1')
    _wait(pg, pid, "show.gateway === '10.0.0.1'")
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Edit Show Gateway'
    # both units show the show's values in grey, their own boxes empty
    read = """(pid) => ['processor-net', 'processor-bu-net'].map(k => ['subnet', 'gateway'].map(f => {
        const el = document.querySelector(`#hw-gear-popover [data-lrd-field="${k}-${f}-${pid}"]`);
        return [el.value, el.placeholder, el.title.includes('prints')];
    }))"""
    assert pg.evaluate(read, pid) == [[['', '255.255.255.0', True], ['', '10.0.0.1', True]]] * 2
    # the backup overrides its subnet; the main still reads the show's
    _type(pg, f'processor-bu-net-subnet-{pid}', '255.255.0.0')
    _wait(pg, pid, "bu.subnet === '255.255.0.0'")
    units = pg.evaluate("() => window.app.networkUnits().map(u => [u.name, u.subnet, u.gateway])")
    assert units == [['H9', '255.255.255.0', '10.0.0.1'], ['H9 BU', '255.255.0.0', '10.0.0.1']], units
    # the show's change reaches every unit without its own
    _type(pg, 'show-net-subnet', '/24')
    _wait(pg, pid, "show.subnet === '/24'")
    units = pg.evaluate("() => window.app.networkUnits().map(u => u.subnet)")
    assert units == ['/24', '255.255.0.0'], units
    # undo puts the show's back
    pg.evaluate("() => window.app.undo()")
    _wait(pg, pid, "show.subnet === '255.255.255.0'")
    served = pg.evaluate("() => fetch('/api/processors').then(r => r.json()).then(d => d.network)")
    assert served == {'subnet': '255.255.255.0', 'gateway': '10.0.0.1'}, served
    pg.keyboard.press('Escape')
    assert ids['errors'] == []


def test_a_bad_entry_is_marked_red_with_a_plain_reason_and_stored_as_typed(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    _gear(pg, pid)
    key = f'processor-net-ip-{pid}'
    field = pg.locator(f'#hw-gear-popover [data-lrd-field="{key}"]')
    field.click()
    field.fill('10.0.0.300')
    # marked while it is typed, before it is committed
    assert 'hw-pop-net-bad' in field.get_attribute('class')
    pg.keyboard.press('Enter')
    _wait(pg, pid, "main.ip === '10.0.0.300'")
    field = pg.locator(f'#hw-gear-popover [data-lrd-field="{key}"]')
    mark = field.evaluate("""el => ({ bad: el.classList.contains('hw-pop-net-bad'),
                                      invalid: el.getAttribute('aria-invalid'), title: el.title,
                                      border: getComputedStyle(el).borderTopColor })""")
    assert mark['bad'] and mark['invalid'] == 'true', mark
    assert mark['title'].startswith('Not an IP address'), mark
    assert mark['border'] == 'rgb(208, 90, 82)', mark
    _type(pg, f'processor-net-subnet-{pid}', '255.0.255.0')
    _wait(pg, pid, "main.subnet === '255.0.255.0'")
    sub = pg.locator(f'#hw-gear-popover [data-lrd-field="processor-net-subnet-{pid}"]')
    assert sub.evaluate("el => el.classList.contains('hw-pop-net-bad')")
    assert sub.get_attribute('title').startswith('Not a subnet mask')
    # fixed, the mark goes
    _type(pg, key, '10.0.0.30')
    _wait(pg, pid, "main.ip === '10.0.0.30'")
    field = pg.locator(f'#hw-gear-popover [data-lrd-field="{key}"]')
    assert not field.evaluate("el => el.classList.contains('hw-pop-net-bad')")
    assert field.get_attribute('aria-invalid') == 'false'
    pg.keyboard.press('Escape')
    assert ids['errors'] == []


def test_two_units_on_one_ip_are_named_in_the_gear_the_strip_and_the_header(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    _gear(pg, pid)
    _type(pg, f'processor-net-ip-{pid}', '10.0.0.10')
    _wait(pg, pid, "main.ip === '10.0.0.10'")
    assert pg.locator('#hw-gear-popover .hw-pop-net-dup').count() == 0
    _type(pg, f'processor-bu-net-ip-{pid}', '10.0.0.10')
    _wait(pg, pid, "bu.ip === '10.0.0.10'")
    pg.wait_for_timeout(300)
    dups = pg.evaluate("() => [...document.querySelectorAll('#hw-gear-popover .hw-pop-net-dup')]"
                       ".map(e => e.textContent)")
    assert dups == ['Same IP as H9 BU.', 'Same IP as H9.'], dups
    strip = pg.evaluate("() => [...document.querySelectorAll('#hw-dock-issues .hw-dock-issue-net')]"
                        ".map(e => [e.querySelector('.hw-dock-issue-msg').textContent, e.className])")
    assert strip == [['H9 and H9 BU have the same IP, 10.0.0.10. Give each unit its own.',
                      'hw-dock-issue hw-dock-issue-net']], strip
    pill = pg.locator(f'[data-lrd-field="processor-ip-pill-{pid}"]')
    assert 'hw-dock-ippill-dup' in pill.get_attribute('class')
    _shot(pg, pg.locator('#hw-gear-popover'), 'network-gear-duplicate.png')
    # nothing is blocked: both are stored
    st = _state(pg, pid)
    assert st['main'] == {'ip': '10.0.0.10'} and st['bu'] == {'ip': '10.0.0.10'}, st
    # given its own, the warning goes everywhere
    _type(pg, f'processor-bu-net-ip-{pid}', '10.0.0.11')
    _wait(pg, pid, "bu.ip === '10.0.0.11'")
    pg.wait_for_timeout(300)
    assert pg.locator('#hw-gear-popover .hw-pop-net-dup').count() == 0
    assert pg.locator('#hw-dock-issues .hw-dock-issue-net').count() == 0
    assert 'hw-dock-ippill-dup' not in pg.locator(f'[data-lrd-field="processor-ip-pill-{pid}"]').get_attribute('class')
    pg.keyboard.press('Escape')
    assert ids['errors'] == []


def test_they_survive_a_reload_and_a_save_and_reopen(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    pg.evaluate("""async (pid) => {
        const app = window.app;
        await app.setUnitNetworkField(pid, 'main', 'ip', '10.0.0.10');
        await app.setUnitNetworkField(pid, 'bu', 'ip', '10.0.0.11');
        await app.setUnitNetworkField(pid, 'bu', 'note', 'VLAN 20');
        await app.setShowNetworkField('subnet', '255.255.255.0');
    }""", pid)
    want = {'main': {'ip': '10.0.0.10'}, 'bu': {'ip': '10.0.0.11', 'note': 'VLAN 20'},
            'show': {'subnet': '255.255.255.0'}}
    st = _state(pg, pid)
    assert {k: st[k] for k in want} == want, st
    text = pg.evaluate("() => window.app.serializeProjectForFile()")
    saved = json.loads(text)
    assert saved['network'] == want['show']
    assert next(p for p in saved['processors'] if p['id'] == pid)['backupUnit']['network'] == want['bu']
    # a reload: the server's copy
    open_app(pg)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    st = _state(pg, pid)
    assert {k: st[k] for k in want} == want, st
    _gear(pg, pid)
    assert pg.locator(f'[data-lrd-field="processor-bu-net-note-{pid}"]').input_value() == 'VLAN 20'
    assert pg.locator(f'[data-lrd-field="processor-net-subnet-{pid}"]').get_attribute('placeholder') == '255.255.255.0'
    pg.keyboard.press('Escape')
    # File > New has none; the saved file opens with them
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_function("() => window.app.project && !(window.app.project.processors || []).length", timeout=10000)
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.project.network === undefined")
    assert pg.evaluate("() => window.app.binderUsesNetwork()") is False
    pg.evaluate("async (text) => { await window.app._openProjectData(JSON.parse(text), { source: 'file' }); }", text)
    pg.wait_for_timeout(800)
    st = _state(pg, pid)
    assert {k: st[k] for k in want} == want, st
    assert pg.evaluate("() => window.app.networkUnits().map(u => [u.name, u.ip, u.subnet, u.note])") == [
        ['H9', '10.0.0.10', '255.255.255.0', ''], ['H9 BU', '10.0.0.11', '255.255.255.0', 'VLAN 20']]
    assert ids['errors'] == []


# ── the binder ──────────────────────────────────────────────────────────

def _plan(pg, opts=None):
    return pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.number, p.kind, p.sheetTitle])",
                       opts or SHOW)


def _texts(pg, index, opts=None):
    return pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [opts or SHOW, index])


def test_without_an_ip_the_binder_prints_as_it_always_did(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    # a show subnet alone prints nothing either
    pg.evaluate("() => window.app.setShowNetworkField('subnet', '255.255.255.0')")
    pg.wait_for_timeout(500)
    plan = _plan(pg)
    assert 'network' not in [k for _, k, _ in plan], plan
    assert pg.evaluate("() => window.app.binderUsesNetwork()") is False
    for i, (_, kind, _) in enumerate(plan):
        if kind in ('processor', 'data'):
            texts = _texts(pg, i)
            assert 'Network' not in texts and 'NETWORK' not in texts, (kind, texts)
            assert 'IP' not in texts and 'Backup IP' not in texts, (kind, texts)
    # the export dialog offers no Network tick
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(200)
    assert not pg.locator('#export-binder-network-label').is_visible()
    pg.locator('#export-cancel').click()
    assert ids['errors'] == []


def test_the_binder_prints_every_unit_on_the_network_page_the_processor_sheet_and_facts(page):
    pg, ids = page
    pid = ids['procId']
    _clear_all(pg, pid)
    pg.evaluate("""async (pid) => {
        const app = window.app;
        await app.setUnitNetworkField(pid, 'main', 'ip', '10.0.0.10');
        await app.setUnitNetworkField(pid, 'main', 'note', 'control laptop port 2');
        await app.setUnitNetworkField(pid, 'bu', 'ip', '10.0.0.11');
        await app.setShowNetworkField('subnet', '255.255.255.0');
    }""", pid)
    pg.wait_for_timeout(300)
    plan = _plan(pg)
    kinds = [k for _, k, _ in plan]
    assert kinds.count('network') == 1, plan
    at = kinds.index('network')
    # right after the processor sheets, the last of the hardware series
    assert kinds[at - 1] == 'processor' and at == len(kinds) - 1, plan
    series, n = plan[at][0].split('.')
    prev = plan[at - 1][0].split('.')
    assert series == prev[0] and int(n) == int(prev[1]) + 1, plan
    assert plan[at][2] == 'NETWORK'
    # the contents on the overview names it
    assert f"{plan[at][0]}" in ' '.join(_texts(pg, 0))
    texts = _texts(pg, at)
    head = texts.index('PROCESSOR')
    assert texts[head:head + 7] == ['PROCESSOR', 'MODEL', 'UNIT', 'IP', 'SUBNET', 'GATEWAY', 'NOTE'], texts
    rows = texts[head + 7:head + 7 + 14]
    # every unit in tray order, main then backup; empty cells blank, never a dash
    assert rows == ['H9', 'H9', 'Main', '10.0.0.10', '255.255.255.0', '', 'control laptop port 2',
                    'H9 BU', 'H9', 'Backup', '10.0.0.11', '255.255.255.0', '', ''], rows
    assert not any(t.strip() in ('-', '—', '–') for t in texts), texts
    if SCRATCH:
        os.makedirs(SCRATCH, exist_ok=True)
        url = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).canvas.toDataURL('image/png')",
                          [SHOW, at])
        with open(os.path.join(SCRATCH, 'network-page.png'), 'wb') as fh:
            fh.write(base64.b64decode(url.split(',', 1)[1]))
    # the processor's sheet: a NETWORK table with both units
    proc_i = next(i for i, (_, k, _) in enumerate(plan) if k == 'processor')
    texts = _texts(pg, proc_i)
    assert 'Network' in texts or 'NETWORK' in texts, texts
    i = texts.index('UNIT')
    assert texts[i:i + 5] == ['UNIT', 'IP', 'SUBNET', 'GATEWAY', 'NOTE'], texts
    assert texts[i + 5:i + 15] == ['H9', '10.0.0.10', '255.255.255.0', '', 'control laptop port 2',
                                   'H9 BU', '10.0.0.11', '255.255.255.0', '', ''], texts[i:i + 16]
    # each screen's Data sheet: its processor's IP and its backup unit's in FACTS
    data_i = [i for i, (_, k, _) in enumerate(plan) if k == 'data']
    assert data_i, plan
    for d in data_i:
        texts = _texts(pg, d)
        assert 'IP' in texts and texts[texts.index('IP') + 1] == '10.0.0.10', texts
        assert 'Backup IP' in texts and texts[texts.index('Backup IP') + 1] == '10.0.0.11', texts
    # one screen's binder has no Network page; nor has one with the tick off
    one = dict(SHOW, scope={'kind': 'screen', 'layerId': str(ids['a'])})
    assert 'network' not in [k for _, k, _ in _plan(pg, one)]
    assert 'network' not in [k for _, k, _ in _plan(pg, dict(SHOW, network=False))]
    # the dialog offers the tick, on
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(200)
    assert pg.locator('#export-binder-network-label').is_visible()
    assert pg.locator('#export-binder-network').is_checked()
    assert pg.evaluate("() => window.app.readBinderOptions().network") is True
    pg.locator('#export-cancel').click()
    assert ids['errors'] == []
