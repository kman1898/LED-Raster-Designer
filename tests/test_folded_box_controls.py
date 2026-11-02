"""A minimized breakout box still reaches its cable sheet and gear.

The owner, 2026-11-02, on an SX40 with XD boxes in redundancy loops: a
minimized loop row ("XD  A ↔ B  loop") hid the boxes' ≡ and ⚙, which only
sat on the open rows. His ruling on what a minimized row shows: "both boxes
when they are not paired. if backups then just the primary since they are
grouped". So:

  * a minimized loop strip (SX40 A to B, C to D; a NovaStar backup pair)
    carries ONE ≡ and ONE ⚙ on its header, the primary's, and they open the
    same sheet and the same gear content as that box's own row buttons
  * an unpaired box is its own section and its own header keeps its own
    ≡ and ⚙ while minimized
  * pressing them never folds or unfolds the row and never starts a drag
  * an open strip shows only the rows' buttons, never a second set

Synthetic hardware only: two SX40s (one in redundancy, one not) and an MX40
Pro in its 20-port mode with one CVT pair.
"""

import os
import sys

import pytest

from conftest import settled  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""

SEED_JS = """async () => {
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await send('/api/project', 'PUT', proj);
    await send('/api/layer/add', 'POST', { name: 'WALL', columns: 4,
        rows: 4, cabinet_width: 200, cabinet_height: 200 });
    const last = (st) => st.resolved[st.resolved.length - 1];
    // SX40 in redundancy: XD B closes A's loop, XD D closes C's.
    const red = last(await send('/api/processors', 'POST',
                                { deviceId: 'brompton-sx40' }));
    await send(`/api/processors/${red.id}`, 'PUT', { redundancy: true });
    // SX40 without: four boxes, none paired.
    const solo = last(await send('/api/processors', 'POST',
                                 { deviceId: 'brompton-sx40' }));
    // MX40 Pro in 20-port mode: one add is a CVT pair (backupOf).
    const mx = last(await send('/api/processors', 'POST',
                               { deviceId: 'novastar-mx40-pro' }));
    const mxCard = mx.slots[0].card.id;
    await send(`/api/processors/${mx.id}/cards/${mxCard}`, 'PUT',
               { mode: '20-port' });
    await send(`/api/processors/${mx.id}/cards/${mxCard}/cvts`, 'POST',
               { deviceId: 'novastar-cvt10' });
    await window.app.refreshProcessors();
    const boxes = (id) => window.app._processorsResolved
        .find(p => p.id === id).slots[0].card.cvts
        .map(c => ({ id: c.id, backupOf: c.backupOf || null }));
    return { red: boxes(red.id), solo: boxes(solo.id), mx: boxes(mx.id) };
}"""

# What a header looks like to a user: which of its ≡ / ⚙ are drawn, and
# whether its section is folded.
HEAD_JS = """(boxId) => {
    const sec = document.querySelector(
        `[data-lrd-sec-id="hwdock-box-${boxId}"]`);
    if (!sec) return null;
    const head = sec.querySelector(':scope > .lrd-sec-head');
    const shown = (el) => !!el && el.getClientRects().length > 0;
    const pick = (sel) => [...head.querySelectorAll(sel)].filter(shown);
    return {
        loop: sec.classList.contains('hw-dock-loop'),
        folded: sec.classList.contains('lrd-sec-collapsed'),
        gears: pick('.hw-dock-gear').map(g => g.dataset.hwpop),
        sheets: pick('.hw-dock-cablebtn-data').length,
        // every ⚙ drawn anywhere in the section: header and rows alike
        allGears: [...sec.querySelectorAll('.hw-dock-gear')].filter(shown)
            .map(g => g.dataset.hwpop),
    };
}"""

POPOVER_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop || pop.style.display === 'none') return null;
    const t = pop.querySelector('.hw-pop-title');
    return t ? t.textContent : '';
}"""


def landed(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


@pytest.fixture(scope="module")
def fold_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " === true && window.app._socketConnects >= 1")
    landed(pg)
    ids = pg.evaluate(SEED_JS)
    landed(pg)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function(
        "() => window.canvasRenderer.viewMode === 'data-flow'")
    landed(pg)
    yield pg, ids
    context.close()


def head(page, box_id):
    return page.evaluate(HEAD_JS, box_id)


def set_fold(page, box_id, folded):
    """Fold or open a box section with its own arrow, the user's gesture."""
    if head(page, box_id)['folded'] != folded:
        page.locator(f'[data-lrd-sec-id="hwdock-box-{box_id}"] > '
                     '.lrd-sec-head .lrd-sec-arrow').click()
        landed(page)
    assert head(page, box_id)['folded'] == folded


def gear_title(page, hwpop):
    """Open a ⚙ by a real click, read the popover's title, close it."""
    page.locator(f'[data-hwpop="{hwpop}"]').click()
    landed(page)
    title = settled(page, lambda: page.evaluate(POPOVER_JS),
                    lambda v: v is not None)
    page.keyboard.press('Escape')
    landed(page)
    return title


def pairs(boxes):
    """(near, far) for every loop on a card, near being the primary."""
    by_id = {b['id']: b for b in boxes}
    return [(by_id[b['backupOf']]['id'], b['id'])
            for b in boxes if b['backupOf'] in by_id]


def test_the_seed_has_the_loops_and_the_lone_boxes(fold_page):
    page, ids = fold_page
    assert len(pairs(ids['red'])) == 2, ids['red']
    assert pairs(ids['solo']) == [], ids['solo']
    assert len(pairs(ids['mx'])) == 1, ids['mx']
    for near, _far in pairs(ids['red']) + pairs(ids['mx']):
        assert head(page, near)['loop'], f'{near} is not drawn as a loop strip'


@pytest.mark.parametrize('which', ['red', 'mx'])
def test_a_folded_loop_shows_only_the_primarys_sheet_and_gear(fold_page,
                                                              which):
    page, ids = fold_page
    for near, far in pairs(ids[which]):
        set_fold(page, near, False)
        open_ = head(page, near)
        # Open: the header carries none; each row carries its own.
        assert open_['gears'] == [] and open_['sheets'] == 0, open_
        assert sorted(open_['allGears']) == sorted(
            [f'box-{near}', f'box-{far}']), open_
        row_title = gear_title(page, f'box-{near}')

        set_fold(page, near, True)
        shut = head(page, near)
        assert shut['gears'] == [f'boxfold-{near}'], (
            f'a folded loop must show the primary\'s gear only: {shut}')
        assert shut['sheets'] == 1, shut
        assert shut['allGears'] == [f'boxfold-{near}'], shut

        # The ⚙ opens the primary's own gear content, and the fold holds.
        assert gear_title(page, f'boxfold-{near}') == row_title
        assert head(page, near)['folded'], 'the ⚙ unfolded the strip'
        set_fold(page, near, False)


def test_the_folded_sheet_button_opens_the_primarys_sheet_in_place(
        fold_page):
    page, ids = fold_page
    near, far = pairs(ids['red'])[0]
    set_fold(page, near, True)
    sec = f'[data-lrd-sec-id="hwdock-box-{near}"]'
    page.locator(f'{sec} > .lrd-sec-head .hw-dock-cablebtn-data').click()
    landed(page)
    try:
        out = page.evaluate("""([sec, near, far]) => {
            const s = document.querySelector(sec);
            const sheet = s.querySelector(
                `[data-lrd-cable-sheet="cvt:${near}"]`);
            return {
                folded: s.classList.contains('lrd-sec-collapsed'),
                shown: !!sheet && sheet.getClientRects().length > 0,
                outsideFold: !!sheet && !sheet.closest('.lrd-sec-body'),
                farSheet: !!s.querySelector(
                    `[data-lrd-cable-sheet="cvt:${far}"]`),
                on: s.querySelector(':scope > .lrd-sec-head '
                    + '.hw-dock-cablebtn-data').classList
                    .contains('hw-dock-cablebtn-on'),
            };
        }""", [sec, near, far])
        assert out['folded'], f'the ≡ unfolded the strip: {out}'
        assert out['shown'] and out['outsideFold'], out
        assert out['on'] and not out['farSheet'], out

        # Opened, the sheet goes back into the primary's row, beside the
        # row's own ≡, and the header's set is hidden again.
        set_fold(page, near, False)
        out = settled(page, lambda: page.evaluate("""([sec, near]) => {
            const sheet = document.querySelector(sec).querySelector(
                `[data-lrd-cable-sheet="cvt:${near}"]`);
            return !!sheet && !!sheet.closest('.hw-dock-loop-row');
        }""", [sec, near]), lambda v: v)
        assert out, 'the open strip did not put the sheet back in its row'
        assert head(page, near)['sheets'] == 0
    finally:
        page.evaluate(
            """(id) => { localStorage.removeItem(
                window.app._dataCableSheetKey({ kind: 'cvt', id }));
                window.app.renderHardwareDock(); }""", near)
        landed(page)
        set_fold(page, near, False)


def test_the_folded_buttons_never_arm_a_drag(fold_page):
    page, ids = fold_page
    near, _far = pairs(ids['red'])[1]
    set_fold(page, near, True)
    for sel in ('.hw-dock-gear', '.hw-dock-cablebtn-data'):
        btn = page.locator(f'[data-lrd-sec-id="hwdock-box-{near}"] > '
                           f'.lrd-sec-head {sel}')
        box = btn.bounding_box()
        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 30, cy + 8, steps=4)
        mid = page.evaluate("""() => ({
            ghost: !!document.getElementById('hw-dock-ghost'),
            dragLive: !!window.app._dockDrag,
        })""")
        page.mouse.up()
        landed(page)
        assert not mid['ghost'] and not mid['dragLive'], (sel, mid)
        assert head(page, near)['folded'], f'{sel} press unfolded the strip'
    page.keyboard.press('Escape')
    set_fold(page, near, False)


def test_lone_boxes_keep_their_own_buttons_when_folded(fold_page):
    page, ids = fold_page
    solo = [b['id'] for b in ids['solo']]
    try:
        for box_id in solo:
            set_fold(page, box_id, True)
        for box_id in solo:
            out = head(page, box_id)
            assert not out['loop'], out
            assert out['gears'] == [f'box-{box_id}'], (
                f'a folded lone box must show its own gear: {out}')
            assert out['sheets'] == 1, out
        # The ⚙ of a folded lone box opens and leaves the fold alone.
        assert gear_title(page, f'box-{solo[2]}')
        assert head(page, solo[2])['folded']
    finally:
        for box_id in solo:
            set_fold(page, box_id, False)
