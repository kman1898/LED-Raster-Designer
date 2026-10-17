"""The distro's settings panel (the ⚙ popover) and the dock cards at narrow
widths (1.5).

A distro's gear opened in a narrow window used to cut the panel's contents
off on the right - "A per leç", "Follow the circuit voltage — Lir",
"Edison / True1 / powerCC" - and the selects read as text boxes, their
chevrons lost under a background shorthand. The panel now:

  - fits the window at any width, its fields wrapping instead of clipping
    (a select too narrow for its choice wraps the words), its body
    scrolling inside itself with the Remove footer always reachable;
  - has a title bar that stays put: drag it (past 4px) to move the panel,
    held inside the window; × closes it (Tab reaches it; Escape still
    closes from anywhere); a drag never ends as a click-away;
  - shows every select's chevron.

Every dock popover shares the shell (processor, card and box gears too),
so they get the same bar.

In a narrow tray the distro card's header wraps: the supply tag, Balance
and the gear drop to a second line together instead of being clipped or
pushed out of reach, and the processor cards' headers wrap the same way.

Run locally (Chromium and WebKit):
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_panel_fit.py -q --browser chromium
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_panel_fit.py -q --browser webkit
"""

import json
import os

import pytest

import app as app_module
import routes_distro_presets as rdp

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

DISTRO = {'id': 'd1', 'name': 'DISTRO 1', 'system': '120/208', 'voltage': 208, 'phase': 3,
          'ratingA': 400}
SAVED = {'name': 'Our rack',
         'distro': {'system': '120/208', 'input': 'cam200', 'ratingA': 200,
                    'rows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                              'breakerA': 20, 'pairedWith': None}]}}
HEIGHT = 800


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def presets_file(tmp_path_factory):
    """One saved preset, so the gear's "Delete a saved preset…" shows."""
    before = rdp.DISTRO_PRESETS_FILE
    rdp.DISTRO_PRESETS_FILE = str(tmp_path_factory.mktemp('fit_presets') / 'distro_presets.json')
    os.makedirs(os.path.dirname(rdp.DISTRO_PRESETS_FILE), exist_ok=True)
    with open(rdp.DISTRO_PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'presets': [SAVED]}, f)
    yield rdp.DISTRO_PRESETS_FILE
    rdp.DISTRO_PRESETS_FILE = before


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser, presets_file):
    app_module.current_project['distros'] = [json.loads(json.dumps(DISTRO))]
    context = pw_browser.new_context(viewport={'width': 1600, 'height': HEIGHT})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.LRD_LAYOUT "
                         "&& (window.app.project.distros || []).some(d => d.id === 'd1')",
                         timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


def _open(pg, key='distro-d1'):
    """Open a gear by the gear's own click handler. A dispatched click, not
    a pointer one: at a phone-narrow window the app's own panels overlap
    the tray, and what is under test is the panel, not the tray."""
    pg.evaluate("""async (key) => {
        const app = window.app;
        app._hwPopoverClose();
        if (key.startsWith('distro-')) await app.loadCustomDistroPresets(true);
        app.renderHardwareDock();
        const gear = document.querySelector(`[data-hwpop="${key}"]`);
        gear.scrollIntoView({block: 'nearest'});
        gear.click();
    }""", key)
    pg.wait_for_function("() => { const p = document.getElementById('hw-gear-popover');"
                         " return p && p.style.display === 'block'"
                         " && p.style.visibility === 'visible'; }")


def _close(pg):
    pg.evaluate("() => window.app._hwPopoverClose()")


def _rect(pg, sel):
    return pg.evaluate("""(sel) => { const el = document.querySelector(sel);
        if (!el) return null; const r = el.getBoundingClientRect();
        return {left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                width: r.width, height: r.height}; }""", sel)


def _is_open(pg):
    return pg.evaluate("() => !!window.app._hwPopover && "
                       "document.getElementById('hw-gear-popover').style.display === 'block'")


# What the panel shows against the window and against itself. Three ways a
# field can be cut off, all checked: an element past the panel's sides or
# under the body's right edge (the scrollbar side), an element whose own
# box clips its text (scrollWidth past clientWidth), and text that runs out
# of a box that does not clip it. Every select must show its chevron, end
# inside the panel, and either fit its choice on one line or wrap it.
FIT_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop || pop.style.display !== 'block') return null;
    const box = pop.getBoundingClientRect();
    const body = pop.querySelector('.hw-pop-body');
    const br = body.getBoundingClientRect();
    const clipL = br.left + body.clientLeft;
    const clipR = clipL + body.clientWidth;
    const problems = [];
    const say = (what, el, extra) => problems.push(Object.assign({
        what, el: el.dataset && el.dataset.lrdField || String(el.className || el.tagName),
        text: (el.textContent || '').trim().slice(0, 40)}, extra || {}));
    pop.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (!r.width && !r.height) return;
        if (r.left < box.left - 0.5 || r.right > box.right + 0.5) {
            say('outside the panel', el, {right: Math.round(r.right), panel: Math.round(box.right)});
        }
        if (body.contains(el) && el !== body
                && (r.left < clipL - 0.5 || r.right > clipR + 0.5)) {
            say('under the body edge', el, {right: Math.round(r.right), clip: Math.round(clipR)});
        }
        const cs = getComputedStyle(el);
        if (!['INPUT', 'SELECT', 'OPTION', 'OPTGROUP'].includes(el.tagName)
                && cs.overflowX !== 'visible'
                && el.scrollWidth > el.clientWidth + 1) {
            say('clips its text', el, {scroll: el.scrollWidth, client: el.clientWidth});
        }
    });
    if (body.scrollWidth > body.clientWidth + 1) {
        say('the body scrolls sideways', body, {scroll: body.scrollWidth, client: body.clientWidth});
    }
    const walk = document.createTreeWalker(pop, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        if (!n.textContent.trim() || n.parentElement.closest('select')) continue;
        range.selectNodeContents(n);
        const inBody = body.contains(n);
        for (const r of range.getClientRects()) {
            if (!r.width) continue;
            const L = inBody ? clipL : box.left, R = inBody ? clipR : box.right;
            if (r.left < L - 0.5 || r.right > R + 0.5) {
                say('text runs past the edge', n.parentElement, {right: Math.round(r.right), edge: Math.round(R)});
            }
        }
    }
    const ctx = document.createElement('canvas').getContext('2d');
    const selects = [];
    pop.querySelectorAll('select').forEach(s => {
        const r = s.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const cs = getComputedStyle(s);
        ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        const text = s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent : '';
        const inner = s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
        const full = ctx.measureText(text).width;
        const word = Math.max(0, ...text.split(/\\s+/).map(w => ctx.measureText(w).width));
        const oneLine = parseFloat(cs.fontSize) * 1.6;
        const rec = {key: s.dataset.lrdField, text, chevron: /svg/.test(cs.backgroundImage),
                     right: Math.round(r.right), inner: Math.round(inner),
                     full: Math.round(full), height: Math.round(r.height)};
        selects.push(rec);
        if (!rec.chevron) say('select shows no chevron', s, {bg: cs.backgroundImage});
        if (r.right > box.right - 0.5 || r.right > clipR + 0.5) say('select ends past the panel', s, rec);
        if (word > inner + 1) say('a word of the select does not fit', s, rec);
        if (full > inner + 1 && !(cs.whiteSpace === 'normal' && r.height > oneLine)) {
            say('select cuts its choice off', s, rec);
        }
    });
    const rm = pop.querySelector('.hw-pop-remove');
    let removeHit = null;
    if (rm) {
        const r = rm.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        removeHit = !!hit && (hit === rm || rm.contains(hit));
    }
    return {vw: window.innerWidth, vh: window.innerHeight,
            box: {left: box.left, top: box.top, right: box.right, bottom: box.bottom,
                  width: box.width},
            problems, selects, removeHit,
            phasing: !!pop.querySelector('[data-lrd-field="distro-phasing-d1"]'),
            perLeg: [...pop.querySelectorAll('small')].some(s => s.textContent === 'A per leg'),
            subs: pop.querySelectorAll('.hw-pop-out-sub').length};
}"""


def _assert_fits(m, where):
    assert m, f"{where}: the gear opened no panel"
    assert m['box']['left'] >= -0.5 and m['box']['top'] >= -0.5, (where, m['box'])
    assert m['box']['right'] <= m['vw'] + 0.5 and m['box']['bottom'] <= m['vh'] + 0.5, (
        f"{where}: the panel runs off the window: {m['box']} in {m['vw']}x{m['vh']}")
    assert not m['problems'], f"{where}: cut off: {m['problems']}"
    assert m['removeHit'], f"{where}: Remove distro is not reachable"


@pytest.mark.parametrize('width', [1600, 900, 700, 420])
def test_the_panel_fits_the_window_and_cuts_nothing_off(page, width):
    pg, errors = page
    pg.set_viewport_size({'width': width, 'height': HEIGHT})
    try:
        _open(pg)
        m = pg.evaluate(FIT_JS)
        _assert_fits(m, f'{width}px')
        # the fields that were cut off, all there to be checked
        assert m['phasing'] and m['perLeg'] and m['subs'] == 3, m
        keys = {s['key'] for s in m['selects']}
        for k in ('distro-system-d1', 'distro-input-d1', 'distro-phasing-d1',
                  'distro-beach-d1', 'distro-preset-d1', 'distro-preset-delete-d1'):
            assert k in keys, (k, m['selects'])
        # a window too narrow for the natural 300px: the panel narrows
        if width - 16 < 300:
            assert m['box']['width'] <= width - 16 + 0.5, m['box']
        # the window shrinks while it is open: still inside, still whole
        pg.set_viewport_size({'width': max(360, width - 200), 'height': 520})
        pg.wait_for_timeout(150)
        m = pg.evaluate(FIT_JS)
        _assert_fits(m, f'{width}px shrunk to {max(360, width - 200)}x520')
    finally:
        _close(pg)
        pg.set_viewport_size({'width': 1600, 'height': HEIGHT})
    assert not errors, errors


def test_with_always_on_scrollbars_nothing_hides_under_the_bar(page):
    """Safari with "show scroll bars: always" drew the body's scrollbar over
    the fields' right edge. The headless engines draw overlay scrollbars,
    so this forces real ones and a body short enough to scroll."""
    pg, errors = page
    pg.set_viewport_size({'width': 640, 'height': 460})
    style = pg.add_style_tag(content=(
        '#hw-gear-popover * { scrollbar-width: auto !important; scrollbar-color: auto !important; }'
        '#hw-gear-popover ::-webkit-scrollbar { width: 12px; background: #333; }'
        '#hw-gear-popover ::-webkit-scrollbar-thumb { background: #777; }'))
    try:
        _open(pg)
        scrolls = pg.evaluate("() => { const b = document.querySelector('#hw-gear-popover .hw-pop-body');"
                              " return b.scrollHeight > b.clientHeight; }")
        assert scrolls, "the body was meant to scroll at this height"
        _assert_fits(pg.evaluate(FIT_JS), 'always-on scrollbars')
    finally:
        _close(pg)
        style.evaluate('el => el.remove()')
        pg.set_viewport_size({'width': 1600, 'height': HEIGHT})
    assert not errors, errors


HEAD = '#hw-gear-popover .hw-pop-head'
POP = '#hw-gear-popover'


def test_the_header_drags_the_panel_inside_the_window(page):
    pg, errors = page
    pg.set_viewport_size({'width': 1200, 'height': HEIGHT})
    try:
        _open(pg)
        start = _rect(pg, POP)
        head = _rect(pg, HEAD)
        assert pg.eval_on_selector(HEAD, 'el => getComputedStyle(el).cursor') == 'move'
        x, y = head['left'] + 30, head['top'] + head['height'] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        # under the 4px threshold: a press, not a drag
        pg.mouse.move(x + 3, y + 2)
        assert _rect(pg, POP)['left'] == start['left'], "moved before the 4px threshold"
        dy = 60 if start['bottom'] + 60 < HEIGHT - 8 else -60
        pg.mouse.move(x - 200, y + dy, steps=6)
        moved = _rect(pg, POP)
        assert abs(moved['left'] - (start['left'] - 200)) <= 1, (start, moved)
        assert abs(moved['top'] - (start['top'] + dy)) <= 1, (start, moved)
        # off the bottom-right: the panel stays inside, its bar whole
        pg.mouse.move(1199, HEIGHT - 1, steps=6)
        r = _rect(pg, POP)
        h = _rect(pg, HEAD)
        assert r['right'] <= 1200 - 8 + 0.5 and r['bottom'] <= HEIGHT - 8 + 0.5, r
        assert h['top'] >= 0 and h['bottom'] <= HEIGHT, h
        # the drag ends outside the panel: no click-away, no close
        assert pg.evaluate("(p) => !document.getElementById('hw-gear-popover')"
                           ".contains(document.elementFromPoint(p[0], p[1]))", [1199, HEIGHT - 1])
        pg.mouse.up()
        assert _is_open(pg), "the end of a drag closed the panel"
        _assert_fits(pg.evaluate(FIT_JS), 'dragged to the corner')
        # off the top-left
        h = _rect(pg, HEAD)
        pg.mouse.move(h['left'] + 30, h['top'] + h['height'] / 2)
        pg.mouse.down()
        pg.mouse.move(1, 1, steps=8)
        pg.mouse.up()
        r = _rect(pg, POP)
        assert r['left'] >= 8 - 0.5 and r['top'] >= 8 - 0.5, r
        assert _is_open(pg)
        # the spot holds through a refresh and a window resize
        pg.evaluate("() => window.app._hwPopoverRefresh()")
        assert _rect(pg, POP)['left'] == r['left'] and _rect(pg, POP)['top'] == r['top']
        pg.set_viewport_size({'width': 900, 'height': 600})
        pg.wait_for_timeout(150)
        _assert_fits(pg.evaluate(FIT_JS), 'dragged, then the window shrank')
        pg.set_viewport_size({'width': 1200, 'height': HEIGHT})
        pg.wait_for_timeout(150)
        # a click outside after the drag closes it, as ever
        pg.mouse.click(600, 60)
        assert not _is_open(pg), "a click outside after a drag did not close the panel"
        # re-opened, it starts at its gear again
        _open(pg)
        again = _rect(pg, POP)
        assert (again['left'], again['top']) == (start['left'], start['top']), (start, again)
    finally:
        _close(pg)
        pg.set_viewport_size({'width': 1600, 'height': HEIGHT})
    assert not errors, errors


def test_the_close_button_closes_and_never_drags(page):
    pg, errors = page
    close = f'{HEAD} .hw-pop-close'
    try:
        _open(pg)
        info = pg.eval_on_selector(close, """b => ({tag: b.tagName, type: b.type,
            text: b.textContent, title: b.title, inHead: !!b.closest('.hw-pop-head'),
            last: b === b.parentElement.lastElementChild})""")
        assert info == {'tag': 'BUTTON', 'type': 'button', 'text': '×', 'title': 'Close',
                        'inHead': True, 'last': True}, info
        # press on × and move: the panel does not move, and stays open
        start = _rect(pg, POP)
        b = _rect(pg, close)
        pg.mouse.move(b['left'] + b['width'] / 2, b['top'] + b['height'] / 2)
        pg.mouse.down()
        pg.mouse.move(b['left'] - 120, b['top'] + 90, steps=6)
        pg.mouse.up()
        assert _rect(pg, POP) == start, "a press on × dragged the panel"
        assert _is_open(pg)
        # a click closes it, as the gear does
        pg.click(close)
        assert not _is_open(pg)
        # the keyboard: Tab-reachable, Enter and Space press it
        for key in ('Enter', ' '):
            _open(pg)
            assert pg.eval_on_selector(close, 'b => b.tabIndex') == 0
            pg.focus(close)
            pg.keyboard.press('Space' if key == ' ' else key)
            assert not _is_open(pg), f"{key!r} on a focused × did not close the panel"
        # Escape still closes it from anywhere
        _open(pg)
        pg.keyboard.press('Escape')
        assert not _is_open(pg)
    finally:
        _close(pg)
    assert not errors, errors


# ── the dock cards in a narrow tray ───────────────────────────────────────

PROC_SEED_JS = """async () => {
    const add = await (await fetch('/api/processors', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-h9', name: 'FIT PROCESSOR MAIN'}),
    })).json();
    const proc = add.resolved[add.resolved.length - 1];
    const slot = await (await fetch(`/api/processors/${proc.id}/slots/0`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-card-h-16xrj45-2xfiber'}),
    })).json();
    const card = slot.resolved.find(p => p.id === proc.id).slots[0].card;
    let box = null;
    for (const dev of ['novastar-cvt4k-s', 'novastar-cvt10']) {
        const r = await fetch(`/api/processors/${proc.id}/cards/${card.id}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: dev})});
        if (r.ok) { box = (await r.json()).resolved
            .find(p => p.id === proc.id).slots[0].card.cvts[0]; break; }
    }
    await window.app.refreshProcessors();
    return {procId: proc.id, cardId: card.id, boxId: box && box.id};
}"""


def _narrow_tray(pg, width):
    pg.evaluate("""(w) => {
        window.LRD_LAYOUT.move('hardware', 'right', 0);
        window.LRD_SIZES.restore({lrd_hardware_w: w});
        window.app.renderHardwareDock();
    }""", width)
    pg.wait_for_timeout(250)


def _reset_tray(pg):
    pg.evaluate("""() => {
        window.LRD_SIZES.restore({lrd_hardware_w: 0});
        window.LRD_LAYOUT.reset();
        window.app.renderHardwareDock();
    }""")


# Every header in the tray: each control inside its card and inside the
# dock's visible body, and each must-reach button (gear, Balance, ≡) the
# element a click at its centre lands on.
CARDS_JS = """(must) => {
    const dock = document.getElementById('hardware-dock');
    const scroller = document.getElementById('hardware-dock-body');
    const sr = scroller.getBoundingClientRect();
    const clipR = sr.left + scroller.clientLeft + scroller.clientWidth;
    const dr = dock.getBoundingClientRect();
    const problems = [], reached = {};
    const name = el => el.dataset.lrdField || String(el.className || el.tagName);
    dock.querySelectorAll('.hw-dock-unit, .hw-dock-box, .hw-dock-loop').forEach(card => {
        const cr = card.getBoundingClientRect();
        if (!cr.width) return;
        const parts = [':scope > .hw-dock-head-row', ':scope > .hw-dock-legs',
                       ':scope > .hw-dock-outputs'];
        parts.forEach(p => card.querySelectorAll(p).forEach(row => {
            row.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (!r.width || !r.height) return;
                if (r.left < cr.left - 0.5 || r.right > cr.right + 0.5) {
                    problems.push({what: 'outside its card', el: name(el), right: Math.round(r.right), card: Math.round(cr.right)});
                }
                if (r.right > Math.min(clipR, dr.right) + 0.5) {
                    problems.push({what: 'outside the dock', el: name(el), right: Math.round(r.right), dock: Math.round(clipR)});
                }
                const cs = getComputedStyle(el);
                if (el.tagName !== 'INPUT' && cs.overflowX !== 'visible'
                        && el.scrollWidth > el.clientWidth + 1) {
                    problems.push({what: 'clips its text', el: name(el), text: el.textContent.slice(0, 30)});
                }
            });
        }));
    });
    dock.querySelectorAll('select').forEach(s => {
        const r = s.getBoundingClientRect();
        if (r.width && !/svg/.test(getComputedStyle(s).backgroundImage)) {
            problems.push({what: 'select shows no chevron', el: name(s)});
        }
    });
    must.forEach(sel => dock.querySelectorAll(sel).forEach(el => {
        el.scrollIntoView({block: 'nearest'});
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        const ok = !!hit && (hit === el || el.contains(hit));
        reached[sel] = (reached[sel] || 0) + 1;
        if (!ok) problems.push({what: 'cannot be clicked', el: name(el),
                                hit: hit ? name(hit) : null});
    }));
    return {problems, reached, dockW: Math.round(dr.width)};
}"""


@pytest.mark.parametrize('width', [320, 400, 600])
def test_the_distro_card_wraps_instead_of_clipping_in_a_narrow_tray(page, width):
    pg, errors = page
    pg.set_viewport_size({'width': 1400, 'height': 900})
    pg.evaluate("""() => {
        const app = window.app;
        app.updateDistro('d1', {name: 'S', ratingA: 200,
            outputRows: [{connector: 'soca', count: 3, coupling: 'll', breakerA: 20}]});
        const L = app.project.layers.find(l => l.type !== 'image');
        if (L) {
            L.powerVoltage = 110; L.powerAmperage = 15; L.panelWatts = 100;
            L.powerSocaDistro = {1: 'd1', 2: 'd1'};
            app.updateLayers([L], true);
        }
    }""")
    try:
        _narrow_tray(pg, width)
        m = pg.evaluate(CARDS_JS, ['[data-hwpop="distro-d1"]',
                                   '[data-lrd-field="distro-balance-d1"]',
                                   '.hw-dock-multi .hw-dock-cablebtn'])
        assert m['reached'].get('[data-hwpop="distro-d1"]') == 1, m
        assert m['reached'].get('[data-lrd-field="distro-balance-d1"]') == 1, m
        assert not m['problems'], f"{width}px tray (dock {m['dockW']}px): {m['problems']}"
        # the gear still opens the panel, and the panel still fits
        pg.locator('[data-hwpop="distro-d1"]').click()
        pg.wait_for_function("() => document.getElementById('hw-gear-popover').style.display === 'block'")
        _assert_fits(pg.evaluate(FIT_JS), f'opened from a {width}px tray')
    finally:
        _close(pg)
        _reset_tray(pg)
        pg.set_viewport_size({'width': 1600, 'height': HEIGHT})
    assert not errors, errors


@pytest.mark.parametrize('width', [320, 400, 600])
def test_the_processor_cards_wrap_instead_of_clipping_in_a_narrow_tray(page, width):
    pg, errors = page
    pg.set_viewport_size({'width': 1400, 'height': 900})
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'data-flow'")
    ids = pg.evaluate(PROC_SEED_JS)
    try:
        assert ids['boxId'], ids
        _narrow_tray(pg, width)
        m = pg.evaluate(CARDS_JS, ['.hw-dock-gear'])
        assert m['reached'].get('.hw-dock-gear', 0) >= 3, m
        assert not m['problems'], f"{width}px tray (dock {m['dockW']}px): {m['problems']}"
        # the processor's gear opens the same shell: a title bar with ×
        _open(pg, f'proc-{ids["procId"]}')
        assert pg.eval_on_selector(f'{HEAD} .hw-pop-close', 'b => b.title') == 'Close'
        assert pg.eval_on_selector(HEAD, 'el => getComputedStyle(el).cursor') == 'move'
        _close(pg)
    finally:
        _close(pg)
        pg.evaluate("""async (ids) => {
            await fetch(`/api/processors/${ids.procId}`, {method: 'DELETE'});
            await window.app.refreshProcessors();
        }""", ids)
        _reset_tray(pg)
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
        pg.set_viewport_size({'width': 1600, 'height': HEIGHT})
    assert not errors, errors
