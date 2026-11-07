"""The power right-click menu in the owner's words, 2026-10-20.

- "unshare doesnt sound correct": a shared circuit offers "Remove 3fer"
  (named by its ways), the batch "Remove 3fers from this screen".
- The tray's distro unplugs read "Unplug multi" / "Unplug circuit"
  (tests/test_hardware_dock.py pins those).
- Tab steps circuits in the Power view, so the menu says "Previous
  Circuit" / "Next Circuit" there.
- "when i click to redraw a circuit and it is highlighted we need to make
  sure it stays highlighted until after it has been redrawn": the run open
  for redrawing keeps its highlight after Alt is let go, until Esc.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_menu_wording.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, alt_click,
)

MENU_TEXT_JS = """() => [...document.querySelectorAll('#context-menu .menu-option')]
    .filter(e => e.offsetParent !== null).map(e => e.textContent.trim())"""


def _menu(page, p):
    page.evaluate("() => window.app.hideContextMenu()")
    page.mouse.click(p['x'], p['y'], button='right')
    landed(page)
    return page.evaluate(MENU_TEXT_JS)


def test_a_3fer_offers_remove_3fer_and_the_screen_remove_3fers(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    items = _menu(page, pt(page, wall, 2, 1))
    assert 'Remove 3fer' in items, items
    assert 'Remove 3fers from this screen' in items, items
    assert not any('Un-share' in t for t in items), items


def test_the_tab_items_say_circuit_in_the_power_view(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    items = _menu(page, pt(page, wall, 2, 1))
    assert any(t.startswith('Previous Circuit') for t in items), items
    assert any(t.startswith('Next Circuit') for t in items), items
    assert not any(t.startswith('Next Port') for t in items), items


def test_the_circuit_being_redrawn_stays_lit_until_esc(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    page.evaluate("() => window.app.hideContextMenu()")
    alt_click(page, pt(page, wall, 0, 4))
    away = pt(page, wall, 4, 9)
    page.mouse.move(away['x'], away['y'])
    landed(page)
    lit = """(id) => window.canvasRenderer._runUnderlayLit(window.__nf.layer(id), 2)"""
    assert page.evaluate("() => window.app._overrideHover") is None
    assert page.evaluate(lit, wall), 'the circuit being redrawn stays lit'
    page.keyboard.press('Escape')
    landed(page)
    assert not page.evaluate(lit, wall), 'Esc ends the redraw and its highlight'


# ── a screen back from custom keeps its old drawing, unused ───────────────
#
# The owner, 2026-10-20, on beta.4: custom off, take a circuit over, and
# every click or fill was refused - "5 panels already wired to other
# circuits, R1C20 on Screen2 -> circuit 40". The old custom drawing stays in
# powerCustomPaths after custom goes off; only the runs taken over by hand
# may hold cabinets on an automatic screen.

def _back_from_custom(page):
    from test_nfer_custom_rulings import custom_on, fill
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    page.evaluate("() => window.app.hideContextMenu()")
    custom_on(page)
    assert fill(page, [(wall, 0, 9)])
    custom_on(page)    # and off again: the drawing stays in the dict
    assert page.evaluate("(id) => window.__nf.layer(id).powerFlowPattern", wall) != 'custom'
    assert page.evaluate("(id) => Object.keys(window.__nf.layer(id).powerCustomPaths).length", wall) > 0
    return wall


def test_a_redraw_after_custom_off_refills_its_own_cabinets(page):
    """The old custom drawing no longer blocks the redraw: a fill over the
    taken-over circuit's own cabinets lands, with no error."""
    wall = _back_from_custom(page)
    alt_click(page, pt(page, wall, 0, 4))
    num = page.evaluate("(id) => window.__nf.layer(id).powerCustomIndex", wall)
    cols = page.evaluate("""([id, n]) => [...new Set(window.__nf.layer(id).powerCustomPaths[n]
        .map(e => e.col))].sort((a, b) => a - b)""", [wall, num])
    errors = page.evaluate("""() => { window.__errs = [];
        const real = window.app._toast.bind(window.app);
        window.app._toast = (m, err, ms) => { if (err) window.__errs.push(m); return real(m, err, ms); };
        return true; }""")
    n = page.evaluate("(spans) => window.__nf.select(spans)", [[wall, cols[0], cols[-1]]])
    assert n == 5 * len(cols), n
    ok = page.evaluate("() => window.app._applyPatternFill('power', 'tl-v')")
    landed(page)
    assert ok, page.evaluate("() => window.__errs")
    assert page.evaluate("() => window.__errs") == [], 'no error for a redraw that worked'
    page.keyboard.press('Escape')
    landed(page)


def test_a_redraw_in_auto_refuses_a_cabinet_already_on_another_circuit(page):
    """The owner, 2026-10-20: "it allowed me to put wiring on a panel that
    already had cabling so this is an error". Clicking a cabinet the next
    automatic circuit feeds is refused, named, and changes nothing."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    page.evaluate("() => window.app.hideContextMenu()")
    alt_click(page, pt(page, wall, 0, 4))
    num = page.evaluate("(id) => window.__nf.layer(id).powerCustomIndex", wall)
    before = page.evaluate("([id, n]) => JSON.stringify(window.__nf.layer(id).powerCustomPaths[n])", [wall, num])
    page.evaluate("""() => { window.__errs = [];
        const real = window.app._toast.bind(window.app);
        window.app._toast = (m, err, ms) => { if (err) window.__errs.push(m); return real(m, err, ms); }; }""")
    q = pt(page, wall, 0, 9)
    page.mouse.click(q['x'], q['y'])
    landed(page)
    after = page.evaluate("([id, n]) => JSON.stringify(window.__nf.layer(id).powerCustomPaths[n])", [wall, num])
    assert after == before, 'the other circuit\'s cabinet must not be taken'
    errs = page.evaluate("() => window.__errs")
    assert errs and 'already wired' in errs[0], errs
    page.keyboard.press('Escape')
    landed(page)


def test_a_refused_redraw_is_in_the_log(page):
    """A refusal the user reads reaches the log as toast_error."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4}])
    sent = page.evaluate("""async () => {
        const blobs = [];
        const real = navigator.sendBeacon;
        navigator.sendBeacon = (url, body) => { if (String(url).includes('/api/log')) blobs.push(body); return true; };
        try { window.app._toast('Cannot apply: test refusal', true); }
        finally { navigator.sendBeacon = real; }
        return Promise.all(blobs.map(b => (typeof b === 'string' ? b : b.text()))); }""")
    assert any('toast_error' in s and 'test refusal' in s for s in sent), sent
