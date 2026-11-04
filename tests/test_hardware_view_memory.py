"""A new card or box starts with its cable sheet down and its section open.

The owner (beta.4): after removing an H9 and adding an MX6000 Pro, an
MX 4x10G and a CVT10, the new card and box came up with their data cable
sheets already open, "as if leftover from another system". Which face a
card or box shows, and whether its tray section is folded, is remembered in
localStorage under the record's id (lrd_data_cable_sheet_<kind>_<id>,
ledRasterPanelCollapsed_hwdock-card|box-<id>) - and ids come back: undo of
an add rewinds the server's counter, and every show numbers its hardware
from 1. Now (app-dock-cable-sheets.js _forgetHardwareViews):

* every tree the page adopts forgets the keys of cards and boxes not in it,
  so an add undone and made again comes up closed;
* opening another show or File > New forgets every card's and box's;
* a plain page reload keeps them - the record is the same record.

Run locally:
    python -m pytest tests/test_hardware_view_memory.py -q
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


MX40 = 'novastar-mx40-pro'
CVT10 = 'novastar-cvt10'

KEYS_JS = """() => {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k.startsWith('lrd_data_cable_sheet_')
                || k.startsWith('ledRasterPanelCollapsed_hwdock-card-')
                || k.startsWith('ledRasterPanelCollapsed_hwdock-box-')) {
            out[k] = localStorage.getItem(k);
        }
    }
    return out;
}"""

VIEW_JS = """(id) => {
    const btn = document.querySelector(`[data-lrd-field="data-cable-sheet-${id}"]`);
    const sec = document.querySelector(`[data-lrd-sec-id="hwdock-card-${id}"], [data-lrd-sec-id="hwdock-box-${id}"]`);
    return {btn: !!btn, open: !!(btn && btn.classList.contains('hw-dock-cablebtn-on')),
            folded: !!(sec && sec.classList.contains('lrd-sec-collapsed'))};
}"""

HW_JS = """() => (window.app._processorsResolved || []).map(p => ({
    id: p.id,
    cards: (p.slots || []).filter(s => s.card).map(s => ({
        id: s.card.id, boxes: (s.card.cvts || []).map(c => c.id)}))}))"""


@pytest.fixture()
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true")
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_function("() => window.app.project && !(window.app.project.processors || []).length"
                         " && !(window.app._processorsResolved || []).length")
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    yield pg
    context.close()


def _add_processor(pg, device_id):
    before = len(pg.evaluate(HW_JS))
    pg.evaluate("(d) => window.app._processorAddRequest('/api/processors', 'POST',"
                " {deviceId: d}, 'Add Processor')", device_id)
    pg.wait_for_function("(n) => (window.app._processorsResolved || []).length > n", arg=before)
    pg.wait_for_timeout(300)
    return pg.evaluate(HW_JS)[-1]


def _add_box(pg, proc_id, card_id):
    pg.evaluate("([p, c, d]) => window.app._processorRequest("
                "`/api/processors/${p}/cards/${c}/cvts`, 'POST', {deviceId: d},"
                " 'Add Breakout Box')", [proc_id, card_id, CVT10])
    pg.wait_for_function(
        "(c) => (window.app._processorsResolved || []).some(p => (p.slots || [])"
        ".some(s => s.card && s.card.id === c && (s.card.cvts || []).length))", arg=card_id)
    pg.wait_for_timeout(300)
    return pg.evaluate(HW_JS)[-1]['cards'][0]['boxes'][-1]


def _flip_sheet(pg, record_id):
    pg.locator(f'[data-lrd-field="data-cable-sheet-{record_id}"]').first.click()
    pg.wait_for_timeout(300)


def _fold(pg, kind, record_id):
    pg.locator(f'[data-lrd-sec-id="hwdock-{kind}-{record_id}"] .lrd-sec-arrow').first.click()
    pg.wait_for_timeout(300)


def _undo(pg):
    pg.keyboard.press('Control+z')
    pg.wait_for_timeout(1500)


def _view(pg, record_id):
    return pg.evaluate(VIEW_JS, record_id)


def test_an_add_undone_and_made_again_comes_up_closed(page):
    proc = _add_processor(page, MX40)
    card = proc['cards'][0]['id']
    _flip_sheet(page, card)
    assert _view(page, card)['open'] is True
    _undo(page)
    assert page.evaluate(HW_JS) == []
    again = _add_processor(page, MX40)
    assert again['cards'][0]['id'] == card, (
        'the counter did not rewind; the test no longer reuses the id')
    assert _view(page, card) == {'btn': True, 'open': False, 'folded': False}, (
        'the re-added card came up with the old one\'s sheet open')

    # the same for a box on it
    box = _add_box(page, again['id'], card)
    _flip_sheet(page, box)
    assert _view(page, box)['open'] is True
    _undo(page)
    assert _add_box(page, again['id'], card) == box
    assert _view(page, box)['open'] is False, (
        'the re-added box came up with the old one\'s sheet open')
    assert not [k for k in page.evaluate(KEYS_JS)
                if k.startswith('lrd_data_cable_sheet_')]


def test_a_new_show_forgets_the_old_ones_sheets_and_folds_a_reload_keeps_them(page):
    proc = _add_processor(page, MX40)
    card = proc['cards'][0]['id']
    _flip_sheet(page, card)
    _fold(page, 'card', card)
    assert _view(page, card) == {'btn': True, 'open': True, 'folded': True}

    # a reload is the same show and the same card: both are remembered
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete === true"
                           " && (window.app._processorsResolved || []).length === 1")
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(500)
    assert _view(page, card) == {'btn': True, 'open': True, 'folded': True}

    # File > New: card1 of the next show is another card
    page.evaluate("() => window.app.createNewProject()")
    page.wait_for_function("() => !(window.app._processorsResolved || []).length")
    page.wait_for_timeout(300)
    assert page.evaluate(KEYS_JS) == {}
    fresh = _add_processor(page, MX40)
    assert fresh['cards'][0]['id'] == card
    assert _view(page, card) == {'btn': True, 'open': False, 'folded': False}, (
        'the new show\'s card came up with the old show\'s sheet or fold')


def test_removing_a_processor_forgets_its_cards_views(page):
    proc = _add_processor(page, MX40)
    card = proc['cards'][0]['id']
    _flip_sheet(page, card)
    _fold(page, 'card', card)
    assert page.evaluate(KEYS_JS)
    page.locator(f'[data-lrd-field="hwgear-proc-{proc["id"]}"]').first.click()
    page.wait_for_timeout(300)
    page.locator('.hw-pop-remove', has_text='Remove processor').first.click()
    page.wait_for_function("() => !(window.app._processorsResolved || []).length")
    page.wait_for_timeout(300)
    assert page.evaluate(KEYS_JS) == {}
