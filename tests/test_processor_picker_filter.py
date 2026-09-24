"""The Add-processor picker offers only the gear the project's screens can
land on (owner ruling, 2026-09-24: "if a raster only has Brompton
processing selected on the whole raster then when we add processors we need
to make sure that only Brompton shows up. same goes for all other
processors").

The rule is the platform wall the drop already enforces, and nothing else:
a unit is listed when accepted_platforms(unit) - or, for a chassis, the
union of accepted_platforms over the cards it takes - shares a value with
the Processing settings in use across EVERY screen layer of the project (all
canvases, layer.processorType folded through the resolve's alias table).
Mixed settings list the union; no screen on a setting lists every unit; a
device the matrix does not restrict is never hidden. Units already in the
tray are the tray's business, not the picker's. The chassis gear's slot-card
picker keeps the same wall over the cards the chassis accepts.

The wall is served, not copied: /api/processor-catalog carries `platforms`
(accepted_platforms), `slotPlatforms` and `platformAliases` per the tables in
port_assignment.py, and the JS holds none of those tables.

Run locally:
    python3 -m pytest tests/test_processor_picker_filter.py -q --browser chromium
"""

import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402
import processor_catalog as catalog  # noqa: E402

JS_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')


# ── the rule, computed from the server's tables ──────────────────────────

def wall(device):
    """The platforms a unit can carry a screen on, as the picker reads them
    off the catalog route - None when the matrix leaves it unrestricted."""
    accepted = assignment.accepted_platforms(device['id'])
    slots = assignment.slot_platforms(device['id'])
    if accepted is None and slots is None:
        return None
    return set(accepted or ()) | set(slots or ())


def expected_units(platforms, kind='processor', pool=None):
    """The ids the picker should list for screens on these platforms."""
    used = {assignment.platform_aliases().get(p, p) for p in platforms
            if isinstance(p, str) and p}
    out = []
    for device in (pool if pool is not None else catalog.devices(kind)):
        w = wall(device)
        if not used or w is None or (w & used):
            out.append(device['id'])
    return out


ALL_PROCESSORS = [d['id'] for d in catalog.devices('processor')]


# ── Flask: the route carries the wall ────────────────────────────────────

def test_the_catalog_route_carries_each_devices_accepted_platforms(client):
    """`platforms` per device IS accepted_platforms, sorted, None for an
    unrestricted device - the one list the drop refuses on."""
    data = client.get('/api/processor-catalog').get_json()
    assert data['devices'], 'the route lost the devices'
    for device in data['devices']:
        accepted = assignment.accepted_platforms(device['id'])
        want = sorted(accepted) if accepted is not None else None
        assert device['platforms'] == want, device['id']


def test_the_catalog_route_carries_a_chassis_cards_union(client):
    """A chassis has no ports of its own: `slotPlatforms` is the union of
    its acceptable cards' walls (the MX chassis takes a 1G card and the 5G
    fiber card, so it carries both), and a unit that takes no cards
    carries None."""
    data = client.get('/api/processor-catalog').get_json()
    by_id = {d['id']: d for d in data['devices']}
    for device in catalog.devices():
        slots = assignment.slot_platforms(device['id'])
        want = sorted(slots) if slots is not None else None
        assert by_id[device['id']]['slotPlatforms'] == want, device['id']
    assert by_id['novastar-mx6000-pro']['slotPlatforms'] == sorted(
        assignment.accepted_platforms('novastar-card-mx-4x10g')
        | assignment.accepted_platforms('novastar-card-mx-1x40g'))
    assert by_id['novastar-mx40-pro']['slotPlatforms'] is None
    assert by_id['brompton-sx40']['slotPlatforms'] is None


def test_the_catalog_route_carries_the_alias_table_and_the_whole_file(client):
    """The retired tokens fold through the served table, every device of the
    file is still there with its fields, and the cached catalog the server
    resolves from is not written to."""
    data = client.get('/api/processor-catalog').get_json()
    assert data['platformAliases'] == assignment.platform_aliases()
    assert data['platformAliases'], 'the alias table came back empty'
    file_devices = catalog.load_catalog()['devices']
    assert [d['id'] for d in data['devices']] == [d['id'] for d in file_devices]
    for served, on_file in zip(data['devices'], file_devices):
        for key, value in on_file.items():
            assert served[key] == value, (served['id'], key)
        assert 'platforms' not in on_file, 'the route wrote into the cache'
        assert 'slotPlatforms' not in on_file, 'the route wrote into the cache'
    assert 'platformAliases' not in catalog.load_catalog()


# ── drift: the client holds no copy of the tables ────────────────────────

def test_the_client_holds_no_copy_of_the_platform_tables():
    """The JS names no catalog family, no device the matrix rules past its
    family, and no table of port_assignment's - it reads `platforms` off
    the route. A family id in the JS would be the start of a second
    matrix."""
    # A family that is also a platform token ('brompton', 'megapixel')
    # is a legitimate dropdown value in the JS; the families that are
    # ONLY the matrix's (every NovaStar line) are what a copy would name.
    platforms = set(assignment.PLATFORM_FAMILIES)
    families = set()
    for fams in assignment.PLATFORM_FAMILIES.values():
        families |= set(fams)
    tokens = sorted(families - platforms) + sorted(assignment.DEVICE_PLATFORMS)
    assert len(tokens) >= 6, tokens
    forbidden = [f"{q}{t}{q}" for t in tokens for q in ("'", '"', '`')]
    forbidden += ['PLATFORM_FAMILIES', 'DEVICE_PLATFORMS', 'PLATFORM_LABELS',
                  'accepted_platforms(']
    offenders = []
    for path in sorted(glob.glob(os.path.join(JS_DIR, '*.js'))):
        if os.path.basename(path) == 'socket.io.min.js':
            continue
        text = open(path, encoding='utf-8').read()
        for needle in forbidden:
            if needle in text:
                offenders.append((os.path.basename(path), needle))
    assert not offenders, offenders


# ── browser: the picker follows the screens ──────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Screens with these Processing settings (null = none set), plus these
# units in the tray; then the page reloads so the project arrives the way a
# loaded file does.
SEED_JS = """async ({types, units}) => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    let i = 0;
    for (const t of types) {
        const r = await (await fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'WALL ' + (++i), columns: 4, rows: 3,
                                  cabinet_width: 200, cabinet_height: 200,
                                  offset_x: (i - 1) * 1000})})).json();
        const id = r.layer ? r.layer.id : r.id;
        await fetch(`/api/layer/${id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({processorType: t})});
    }
    for (const u of units) {
        await fetch('/api/processors', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: u})});
    }
    // The per-layer client props in localStorage override the server's
    // processorType by layer id on load; a layer id reused across seeds
    // would wear the previous scenario's setting.
    try { localStorage.removeItem('ledRasterClientProps'); } catch (e) {}
    const p = await (await fetch('/api/project')).json();
    return p.layers.map(l => ({id: l.id, processorType: l.processorType}));
}"""

PICKER_JS = """() => {
    const s = document.getElementById('processor-add-device');
    if (!s) return null;
    return {
        ids: Array.from(s.options).map(o => o.value).filter(Boolean),
        blank: s.options.length ? s.options[0].textContent : '',
        groups: Array.from(s.querySelectorAll('optgroup')).map(g => g.label),
        grouped: Array.from(s.querySelectorAll('optgroup')).map(g => [
            g.label, Array.from(g.querySelectorAll('option')).map(o => o.value)]),
    };
}"""

TRAY_JS = """() => (window.app._processorsResolved || [])
    .map(p => ({id: p.id, deviceId: p.deviceId}))"""

SLOT_PICKER_JS = """(procId) => {
    const pop = document.getElementById('hw-gear-popover');
    const sel = pop && pop.querySelector(
        `[data-lrd-field^="processor-slot-${procId}-"]`);
    if (!sel) return null;
    return Array.from(sel.options).map(o => o.value).filter(Boolean);
}"""


@pytest.fixture(scope="module")
def picker_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def seed(page, types, units=()):
    """Plant the screens and units, reload, open the Data view, and hand
    back the layers as the server holds them."""
    layers = page.evaluate(SEED_JS, {'types': list(types),
                                     'units': list(units)})
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(1800)
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#processor-add-device option')"
        ".length > 1")
    page.wait_for_timeout(300)
    return layers


def picker(page):
    return page.evaluate(PICKER_JS)


def wait_picker(page, want_ids):
    page.wait_for_function(
        """(want) => {
            const s = document.getElementById('processor-add-device');
            const ids = Array.from(s.options).map(o => o.value).filter(Boolean);
            return JSON.stringify(ids) === JSON.stringify(want);
        }""", arg=want_ids, timeout=5000)


def test_all_brompton_screens_list_only_brompton_units(picker_page):
    """Every screen on Brompton Tessera: the picker holds the Brompton
    processors and nothing of NovaStar's or Megapixel's."""
    seed(picker_page, ['brompton', 'brompton'])
    got = picker(picker_page)
    assert got['ids'] == expected_units(['brompton'])
    assert got['ids'], 'the picker emptied'
    assert all(i.startswith('brompton-') for i in got['ids']), got['ids']
    assert not any('novastar' in i or 'megapixel' in i for i in got['ids'])
    assert got['groups'] == ['Brompton']
    assert got['blank'] == 'Add a processor…'


def test_all_legacy_screens_list_only_what_the_drop_accepts_for_legacy(
        picker_page):
    """Every screen on NovaStar (Legacy): exactly the units whose cards the
    drop would accept a Legacy screen on - the VX, MCTRL, NovaPro and H
    lines - and no COEX, Brompton or Megapixel unit."""
    seed(picker_page, ['novastar-armor'])
    got = picker(picker_page)
    want = expected_units(['novastar-armor'])
    assert got['ids'] == want
    assert 'novastar-vx400' in got['ids']
    assert 'novastar-h9' in got['ids']
    assert 'novastar-mx40-pro' not in got['ids']
    assert 'novastar-cx40-pro' not in got['ids']
    assert 'novastar-ku20' not in got['ids']
    assert not any(i.startswith(('brompton-', 'megapixel-'))
                   for i in got['ids'])
    assert got['groups'] == ['NovaStar']
    # each listed unit really does accept the setting, per the server
    for device_id in got['ids']:
        w = wall(catalog.get_device(device_id))
        assert w is None or 'novastar-armor' in w, device_id


def test_a_five_g_project_keeps_the_chassis_whose_card_is_five_g(picker_page):
    """A chassis has no ports of its own, so its place in the list is its
    cards': the MX chassis stays for a 5G project because its 40G card is
    5G gear, while the MX40 Pro (1G COEX only) goes."""
    seed(picker_page, ['novastar-5g'])
    got = picker(picker_page)
    assert got['ids'] == expected_units(['novastar-5g'])
    assert 'novastar-mx6000-pro' in got['ids']
    assert 'novastar-mx2000-pro' in got['ids']
    assert 'novastar-cx40-pro' in got['ids']
    assert 'novastar-ku20' in got['ids']
    assert 'novastar-mx40-pro' not in got['ids']
    assert 'novastar-vx400' not in got['ids']


def test_mixed_screens_list_the_union(picker_page):
    """One Brompton screen and one Legacy screen: both lines, the vendor
    groups intact, and still no COEX or Megapixel unit."""
    seed(picker_page, ['brompton', 'novastar-armor', 'brompton'])
    got = picker(picker_page)
    want = expected_units(['brompton', 'novastar-armor'])
    assert got['ids'] == want
    assert 'brompton-sx40' in got['ids']
    assert 'novastar-vx400' in got['ids']
    assert 'novastar-mx40-pro' not in got['ids']
    assert not any(i.startswith('megapixel-') for i in got['ids'])
    assert got['groups'] == ['NovaStar', 'Brompton']
    for label, ids in got['grouped']:
        assert ids, label
        assert all(catalog.get_device(i)['vendor'] == label for i in ids)


def test_no_processing_setting_anywhere_lists_every_unit(picker_page):
    """Screens carrying no Processing setting leave the picker whole -
    every processor, in catalog order, grouped by vendor. (An empty
    project is not a reachable state: the app seeds a screen.)"""
    layers = seed(picker_page, [None, None])
    assert all(l['processorType'] is None for l in layers), layers
    got = picker(picker_page)
    assert got['ids'] == ALL_PROCESSORS
    assert got['groups'] == ['NovaStar', 'Brompton', 'Megapixel']


def test_changing_a_screens_processing_setting_refills_the_list(picker_page):
    """The picker moves with the screens: the Processing dropdown on a
    selected wall changes the set, and the picker refills - the same
    number of options being no reason to stand still (Brompton's six
    processors and Megapixel's three are different lists)."""
    layers = seed(picker_page, ['brompton'])
    assert picker(picker_page)['ids'] == expected_units(['brompton'])
    picker_page.evaluate("""(id) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(l => l.id === id));
    }""", layers[0]['id'])
    picker_page.wait_for_timeout(300)
    picker_page.select_option('#processor-type', 'megapixel-1g')
    picker_page.wait_for_function(
        "(id) => window.app.project.layers.find(l => l.id === id)"
        ".processorType === 'megapixel-1g'", arg=layers[0]['id'])
    wait_picker(picker_page, expected_units(['megapixel-1g']))
    got = picker(picker_page)
    assert all(i.startswith('megapixel-') for i in got['ids']), got['ids']

    # and back to a NovaStar line, with the same live path
    picker_page.select_option('#processor-type', 'novastar-coex-1g')
    wait_picker(picker_page, expected_units(['novastar-coex-1g']))
    got = picker(picker_page)
    assert 'novastar-mx40-pro' in got['ids']
    assert 'novastar-ku20' in got['ids']
    assert not any(i.startswith(('brompton-', 'megapixel-'))
                   for i in got['ids'])


def test_a_unit_already_in_the_tray_stays_when_the_screens_change(
        picker_page):
    """The picker is the picker; the tray is the tray. An MX40 Pro added
    while the screens were COEX stays in the tray - no removal, no warning
    row - after every screen moves to Brompton, and the picker alone
    stops offering it."""
    layers = seed(picker_page, ['novastar-coex-1g'],
                  units=['novastar-mx40-pro'])
    tray = picker_page.evaluate(TRAY_JS)
    assert [t['deviceId'] for t in tray] == ['novastar-mx40-pro']
    assert 'novastar-mx40-pro' in picker(picker_page)['ids']

    picker_page.evaluate("""(id) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(l => l.id === id));
    }""", layers[0]['id'])
    picker_page.wait_for_timeout(300)
    picker_page.select_option('#processor-type', 'brompton')
    wait_picker(picker_page, expected_units(['brompton']))
    assert 'novastar-mx40-pro' not in picker(picker_page)['ids']
    tray = picker_page.evaluate(TRAY_JS)
    assert [t['deviceId'] for t in tray] == ['novastar-mx40-pro']
    assert picker_page.locator(
        f'[data-hwdock="processor-{tray[0]["id"]}"]').count() == 1
    issues = picker_page.evaluate(
        "() => (document.getElementById('hw-dock-issues') || {})"
        ".textContent || ''")
    assert 'MX40' not in issues, issues


def _slot_cards(page, proc_id):
    page.locator(f'[data-hwpop="proc-{proc_id}"]').click()
    page.wait_for_timeout(300)
    got = page.evaluate(SLOT_PICKER_JS, proc_id)
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)
    return got


def test_the_chassis_slot_picker_lists_only_the_cards_that_match(
        picker_page):
    """The MX chassis's slot picker keeps the same wall over the cards it
    accepts: a 5G project offers the 40G card alone, a 1G COEX project the
    4x10G card alone, a Brompton project no MX card at all - and with no
    setting in play, both."""
    mx_cards = [d['id'] for d in catalog.cards_for(
        catalog.get_device('novastar-mx6000-pro'))]
    assert len(mx_cards) == 2, mx_cards

    seed(picker_page, ['novastar-5g'], units=['novastar-mx6000-pro'])
    proc_id = picker_page.evaluate(TRAY_JS)[0]['id']
    pool = [catalog.get_device(i) for i in mx_cards]
    got = _slot_cards(picker_page, proc_id)
    assert got == expected_units(['novastar-5g'], 'card', pool)
    assert got == ['novastar-card-mx-1x40g']

    seed(picker_page, ['novastar-coex-1g'], units=['novastar-mx6000-pro'])
    proc_id = picker_page.evaluate(TRAY_JS)[0]['id']
    got = _slot_cards(picker_page, proc_id)
    assert got == expected_units(['novastar-coex-1g'], 'card', pool)
    assert got == ['novastar-card-mx-4x10g']

    seed(picker_page, ['brompton'], units=['novastar-mx6000-pro'])
    proc_id = picker_page.evaluate(TRAY_JS)[0]['id']
    assert _slot_cards(picker_page, proc_id) == []

    seed(picker_page, [None], units=['novastar-mx6000-pro'])
    proc_id = picker_page.evaluate(TRAY_JS)[0]['id']
    assert _slot_cards(picker_page, proc_id) == mx_cards
