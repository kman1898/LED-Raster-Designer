"""Quick Palettes: the Pixel Map tab's eight one-click Color 1 / Color 2
pairs, the style switch, Shuffle and the Hue slider (app-quick-palettes.js),
the colour maths behind them (quick-palettes.js), and the Preferences
Palettes tab that lets the user keep their own eight.

Run locally:
    python3 -m pytest tests/test_quick_palettes.py -v --browser chromium
"""
import os
import re

import pytest

from conftest import settled

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
SHIPPED = ['#404680', '#959CB8']


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ── the sources ───────────────────────────────────────────────────────────

def test_the_section_sits_under_colors_on_the_pixel_map_tab():
    html = _read(INDEX_HTML)
    colors = html.index('<h2>Colors</h2>')
    quick = html.index('id="quick-palettes-panel"')
    text_panel = html.index('id="text-layer-panel"')
    assert colors < quick < text_panel
    tag = re.search(r'<div class="([^"]*)" data-tab="([^"]*)" id="quick-palettes-panel">', html)
    assert tag and 'panel' in tag.group(1).split() and 'screen-only' in tag.group(1).split()
    assert tag.group(2) == 'pixel-map'
    # a .panel-header over a .panel-content: the shared section fold
    # (initSectionCollapse) gives it the collapse arrow
    block = html[quick:text_panel]
    assert '<div class="panel-header"' in block and '<div class="panel-content">' in block
    for i in ['quick-palette-swatches', 'quick-palette-hue', 'quick-palette-hue-reset',
              'quick-palette-shuffle', 'quick-palette-style-tonal',
              'quick-palette-style-bold', 'quick-palette-style-split']:
        assert html.count(f'id="{i}"') == 1, i
    assert 'min="-180" max="180" step="1"' in block


# ── the browser ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and its preferences) as found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');"
        "localStorage.removeItem('ledRasterQuickPaletteStyle');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.project.layers.length > 0")
    pg.wait_for_timeout(800)
    yield pg, errors
    context.close()


def _fresh_screen(pg):
    """One screen on the shipped pair, selected, preferences shipped."""
    pg.evaluate("""async () => {
        const a = window.app;
        a._serverPreferences = {};
        try { localStorage.removeItem('appPreferences'); } catch (e) {}
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: '{}'});
        const s = a.project.layers.find(l => (l.type || 'screen') === 'screen');
        s.color1 = {r: 64, g: 70, b: 128};
        s.color2 = {r: 149, g: 156, b: 184};
        s.panelColorMode = 'checker';
        s.transparentFill = false;
        a.updateLayers([s]);
        a._quickPalette = null;
        a.selectLayer(s.id);
        a.loadQuickPalettes();
    }""")
    pg.wait_for_timeout(300)


def _layer(pg):
    return pg.evaluate("""() => {
        const l = window.app.currentLayer;
        const hex = (c) => window.app.rgbToHex(c.r, c.g, c.b).toUpperCase();
        return {id: l.id, c1: hex(l.color1), c2: hex(l.color2),
                mode: l.panelColorMode || 'checker', transparent: !!l.transparentFill};
    }""")


def _swatches(pg):
    return pg.evaluate("() => window.app.getQuickPalettes()")


def test_the_maths_keeps_every_pair_readable_and_even(page):
    """Every style at every whole-ten base hue: eight different pairs,
    Color 1 dark enough for white cabinet IDs (4.5:1), the two colours far
    enough apart to tell cabinets apart, and Color 1 within a narrow band
    of brightness across the eight (the point of working in OKLCH)."""
    pg, errors = page
    out = pg.evaluate("""async () => {
        const m = await import('/static/js/quick-palettes.js');
        const bad = [];
        for (const style of Object.keys(m.QUICK_PALETTE_STYLES)) {
            for (let base = 0; base < 360; base += 10) {
                const set = m.generateQuickPalettes(base, style, null);
                if (set.length !== 8) bad.push([style, base, 'count', set.length]);
                if (new Set(set.map(p => p.join())).size !== 8) bad.push([style, base, 'dupes']);
                const lights = [];
                for (const [c1, c2] of set) {
                    const white = m.contrastRatio('#FFFFFF', c1);
                    const apart = m.contrastRatio(c1, c2);
                    if (white < 4.5) bad.push([style, base, c1, 'white', white]);
                    if (apart < 2.5) bad.push([style, base, c1, c2, 'apart', apart]);
                    lights.push(m.rgbToOklch(m.parseHex(c1))[0]);
                }
                if (Math.max(...lights) - Math.min(...lights) > 0.03) bad.push([style, base, 'lightness', lights]);
            }
        }
        return {
            bad,
            shipped: m.shippedQuickPalettes(),
            same: m.rotateHue('#404680', 0),
            round: m.rotateHue(m.rotateHue('#404680', 30), -30),
            junk: m.normalizeQuickPalettes([['nope', '#123'], 7]),
        };
    }""")
    assert out['bad'] == [], out['bad'][:5]
    assert out['shipped'][0] == SHIPPED
    assert len(out['shipped']) == 8
    assert out['same'] == '#404680'
    assert out['round'] == '#404680'
    # a junk entry falls back to the shipped pair in its slot; '#123' expands
    assert out['junk'][0] == ['#404680', '#112233']
    assert out['junk'][1] == out['shipped'][1]
    assert errors == []


def test_palette_1_is_the_screen_s_own_colours_and_a_click_applies_a_pair(page, e2e_server):
    pg, errors = page
    _fresh_screen(pg)
    sw = _swatches(pg)
    assert sw[0] == SHIPPED
    assert pg.locator('#quick-palette-1').get_attribute('aria-pressed') == 'true'
    # a screen on a palette pattern, drawn see-through: a pair puts it back
    # on the plain checkerboard so the colours show
    pg.evaluate("() => { const l = window.app.currentLayer; l.panelColorMode = 'diagonal'; l.transparentFill = true; }")
    pg.locator('#quick-palette-4').click()
    got = _layer(pg)
    assert [got['c1'], got['c2']] == sw[3]
    assert got['mode'] == 'checker' and got['transparent'] is False
    assert pg.locator('#quick-palette-4').get_attribute('aria-pressed') == 'true'
    # the Colors section's fields follow
    assert pg.locator('#color1-hex').input_value() == sw[3][0]
    assert pg.locator('#color2-hex').input_value() == sw[3][1]
    # the set does not move under the click: palette 1 is still the old pair
    assert _swatches(pg)[0] == SHIPPED
    # the server has it (a reload keeps it)
    lid = got['id']
    read = f"""async () => {{
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === {lid});
        return window.app.rgbToHex(l.color1.r, l.color1.g, l.color1.b).toUpperCase();
    }}"""
    served = settled(pg, lambda: pg.evaluate(read), lambda v: v == sw[3][0])
    assert served == sw[3][0]
    # one undo step takes it back
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(400)
    back = _layer(pg)
    assert [back['c1'], back['c2']] == SHIPPED, back
    assert errors == []


def test_the_styles_and_shuffle_rebuild_the_eight(page):
    pg, errors = page
    _fresh_screen(pg)
    tonal = _swatches(pg)
    pg.locator('#quick-palette-style-bold').click()
    bold = _swatches(pg)
    assert bold != tonal and len(bold) == 8
    # outside Tonal, palette 1 is built like the rest
    assert bold[0] != SHIPPED
    assert pg.locator('#quick-palette-style-bold').get_attribute('aria-pressed') == 'true'
    assert pg.evaluate("() => localStorage.getItem('ledRasterQuickPaletteStyle')") == 'bold'
    pg.locator('#quick-palette-style-split').click()
    split = _swatches(pg)
    assert split not in (tonal, bold)
    pg.locator('#quick-palette-style-tonal').click()
    assert _swatches(pg) == tonal
    pg.locator('#quick-palette-shuffle').click()
    shuffled = _swatches(pg)
    assert shuffled != tonal and len(shuffled) == 8
    # nothing on the screen changed
    got = _layer(pg)
    assert [got['c1'], got['c2']] == SHIPPED
    assert errors == []


def test_the_hue_slider_turns_the_set_and_the_screen_in_one_undo_step(page):
    pg, errors = page
    _fresh_screen(pg)
    before = _swatches(pg)
    pg.locator('#quick-palette-4').click()
    pair = before[3]
    # a drag: several input events, then one change
    pg.evaluate("""() => {
        const s = document.getElementById('quick-palette-hue');
        for (const v of [3, 7, 12]) { s.value = String(v); s.dispatchEvent(new Event('input')); }
        s.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(600)
    expect = pg.evaluate("""async (pair) => {
        const m = await import('/static/js/quick-palettes.js');
        return pair.map(c => m.rotateHue(c, 12));
    }""", pair)
    got = _layer(pg)
    assert [got['c1'], got['c2']] == expect
    assert pg.locator('#quick-palette-hue-reset').text_content() == '+12°'
    after = _swatches(pg)
    assert after[3] == expect
    assert pg.locator('#quick-palette-4').get_attribute('aria-pressed') == 'true'
    # one undo step for the whole drag
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(400)
    back = _layer(pg)
    assert [back['c1'], back['c2']] == pair, back
    # the reset button turns it back to 0
    pg.evaluate("""() => {
        const s = document.getElementById('quick-palette-hue');
        s.value = '-20'; s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(500)
    pg.locator('#quick-palette-hue-reset').click()
    pg.wait_for_timeout(500)
    assert pg.locator('#quick-palette-hue').input_value() == '0'
    assert pg.locator('#quick-palette-hue-reset').text_content() == '0°'
    assert errors == []


def test_my_own_eight_from_preferences(page):
    """Change a pair on the Palettes tab: the source flips to the user's
    own, Save stores the eight, and the Pixel Map swatches show them with
    the style switch and Shuffle put away. Reset Defaults brings the
    shipped set and the built source back."""
    pg, errors = page
    _fresh_screen(pg)
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="palettes"]').click()
    assert pg.locator('#pref-quick-palette-source').input_value() == 'auto'
    pg.evaluate("""() => {
        const el = document.getElementById('pref-quick-palette-2a');
        el.value = '#112233'; el.dispatchEvent(new Event('input', {bubbles: true}));
    }""")
    assert pg.locator('#pref-quick-palette-source').input_value() == 'custom'
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(500)
    prefs = pg.evaluate("() => window.app.getPreferences()")
    assert prefs['quickPaletteSource'] == 'custom'
    assert prefs['quickPaletteColors'][1][0] == '#112233'
    assert prefs['quickPaletteColors'][0] == SHIPPED
    sw = _swatches(pg)
    assert sw[1][0] == '#112233'
    assert pg.evaluate("() => document.getElementById('quick-palettes-panel').classList.contains('qp-custom')")
    assert not pg.locator('#quick-palette-shuffle').is_visible()
    pg.locator('#quick-palette-2').click()
    assert _layer(pg)['c1'] == '#112233'
    # Reset Defaults (asks first in the dialog) lands the shipped set
    shipped = pg.evaluate("() => window.app.getPreferencesDefaults()")
    assert shipped['quickPaletteSource'] == 'auto'
    assert shipped['quickPaletteColors'][0] == SHIPPED
    pg.evaluate("(d) => { window.app.fillPreferencesUI(d); }", shipped)
    assert pg.locator('#pref-quick-palette-source').input_value() == 'auto'
    assert pg.locator('#pref-quick-palette-2a').input_value().upper() == shipped['quickPaletteColors'][1][0]
    assert errors == []
