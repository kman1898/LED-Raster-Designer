"""Quick Palettes: the Pixel Map tab's eight one-click Color 1 / Color 2
pairs, the style switch, Shuffle and the Hue slider (app-quick-palettes.js),
the color math behind them (quick-palettes.js), and the Preferences
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


# US spelling, in everything the person reads. The two modules are new, so
# all of their text is held to it; the template's identifiers and comments
# are older than the rule, so only what renders is read there.
BRITISH = re.compile(r'colour|neighbour|favour|behaviour|\bcentre|\bgrey\b|customis|organis|maths\b', re.I)
SHOWN_ATTRS = re.compile(r'\b(?:data-tooltip|title|aria-label|placeholder|alt|label)="([^"]*)"')


def _shown_in_template(html):
    """The text and the display attributes of a template, line by line."""
    html = re.sub(r'<!--.*?-->', lambda m: '\n' * m.group(0).count('\n'), html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', lambda m: '\n' * m.group(0).count('\n'), html, flags=re.S)
    for number, line in enumerate(html.split('\n'), 1):
        shown = SHOWN_ATTRS.findall(line) + [re.sub(r'<[^>]*>', ' ', line)]
        for text in shown:
            yield number, text


def test_the_display_text_is_us_spelling():
    hits = [f'index.html:{n}: {text.strip()}' for n, text in _shown_in_template(_read(INDEX_HTML))
            if BRITISH.search(text)]
    for name in ('app-quick-palettes.js', 'quick-palettes.js'):
        text = _read(os.path.join(ROOT, 'src', 'static', 'js', name))
        hits += [f'{name}:{n}: {line.strip()}' for n, line in enumerate(text.split('\n'), 1)
                 if BRITISH.search(line)]
    assert not hits, 'British spelling:\n' + '\n'.join(hits)


def test_the_spelling_guard_reads_tooltips_and_text():
    """The guard above has to be able to fail: a tooltip, a label and a note
    each say it, a comment and an id do not."""
    sample = ('<div data-tooltip="Hue, Turn the colour wheel">\n<label>Colour</label>\n'
              '<input id="pref-binder-colour" value="colour">\n<!-- the colour -->\n')
    said = [n for n, text in _shown_in_template(sample) if BRITISH.search(text)]
    assert sorted(set(said)) == [1, 2], said


# ── the browser ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and its preferences) as found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
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
        a.selectLayer(s);
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


# ── the Hue slider under a real mouse and real keys ──────────────────────
#
# page.mouse and page.keyboard are trusted input: the slider moves the way
# it does for a person, so `change` fires only when the browser fires it.

THUMB = 10   # #quick-palette-hue::-webkit-slider-thumb, style.css


def _x_of(pg, value):
    """The x of the thumb's center at `value`, and the slider's y."""
    box = pg.locator('#quick-palette-hue').bounding_box()
    span = box['width'] - THUMB
    return box['x'] + THUMB / 2 + (value + 180) / 360 * span, box['y'] + box['height'] / 2


def _hue(pg):
    return int(pg.locator('#quick-palette-hue').input_value())


def _readout(pg):
    return pg.locator('#quick-palette-hue-reset').text_content()


def _mouse_drag(pg, to):
    """Press on the thumb where it sits, drag to `to`, let go."""
    pg.locator('#quick-palette-hue').scroll_into_view_if_needed()
    x, y = _x_of(pg, _hue(pg))
    pg.mouse.move(x, y)
    pg.mouse.down()
    x2, _ = _x_of(pg, to)
    pg.mouse.move(x2, y, steps=12)
    pg.mouse.up()
    pg.wait_for_timeout(100)


def _mouse_click_thumb(pg):
    """Press and let go on the thumb without moving: no input, no change."""
    pg.locator('#quick-palette-hue').scroll_into_view_if_needed()
    x, y = _x_of(pg, _hue(pg))
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.up()
    pg.wait_for_timeout(100)


def _steps(pg):
    return pg.evaluate("""() => window.app.history.slice(0, window.app.historyIndex + 1)
        .map(h => h.action)""")


def _undo(pg):
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(300)


def _redo(pg):
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(300)


def _turned(pg, pair, degrees):
    return pg.evaluate("""async ([pair, d]) => {
        const m = await import('/static/js/quick-palettes.js');
        return pair.map(c => m.rotateHue(c, d));
    }""", [pair, degrees])


def _pair_of(pg, layer_id):
    return pg.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        const hex = (c) => window.app.rgbToHex(c.r, c.g, c.b).toUpperCase();
        return [hex(l.color1), hex(l.color2)];
    }""", layer_id)


OTHER_PAIR = ['#603A2C', '#B79F92']


def _two_screens(pg):
    """Screen A on the shipped pair selected, screen B on its own pair, a
    clean history, preferences shipped. Returns the two ids."""
    _fresh_screen(pg)
    a = pg.evaluate("() => window.app.currentLayer.id")
    count = pg.evaluate("""() => window.app.project.layers
        .filter(l => (l.type || 'screen') === 'screen').length""")
    if count < 2:
        pg.evaluate("() => window.app.addLayer()")
        pg.wait_for_function("""() => window.app.project.layers
            .filter(l => (l.type || 'screen') === 'screen').length >= 2""")
        pg.wait_for_timeout(300)
    b = pg.evaluate("""async ([a, pair]) => {
        const app = window.app;
        const b = app.project.layers.find(l => (l.type || 'screen') === 'screen' && l.id !== a);
        const rgb = (h) => app.hexToRgb(h);
        b.color1 = rgb(pair[0]);
        b.color2 = rgb(pair[1]);
        b.locked = false;
        b.panelColorMode = 'checker';
        b.transparentFill = false;
        app.updateLayers([b]);
        const first = app.project.layers.find(l => l.id === a);
        first.locked = false;
        first.color1 = rgb('#404680');
        first.color2 = rgb('#959CB8');
        app.updateLayers([first]);
        await Promise.all([...(app._inflightLayerPuts || [])]);
        app._quickPalette = null;
        app.selectLayer(app.project.layers.find(l => l.id === a));
        app.loadQuickPalettes();
        app.resetHistory('Palette Seed');
        return b.id;
    }""", [a, OTHER_PAIR])
    pg.wait_for_timeout(300)
    return a, b


def _select(pg, layer_id):
    pg.evaluate("""(id) => window.app.selectLayer(
        window.app.project.layers.find(l => l.id === id))""", layer_id)
    pg.wait_for_timeout(200)


def _unlock_all(pg):
    pg.evaluate("""() => {
        const app = window.app;
        app.project.layers.forEach(l => { l.locked = false; });
        app.updateLayers(app.project.layers.filter(l => (l.type || 'screen') === 'screen'));
    }""")
    pg.wait_for_timeout(200)


def test_a_click_on_the_thumb_leaves_nothing_open(page):
    """A click that does not move the thumb is no gesture: the next
    selection rebuilds the set round the new screen, and the next drag
    turns the new screen, undoes in one step and leaves the first screen
    alone."""
    pg, errors = page
    a, b = _two_screens(pg)
    _mouse_click_thumb(pg)
    assert _hue(pg) == 0 and _steps(pg) == ['Palette Seed']
    _select(pg, b)
    assert _swatches(pg)[0] == OTHER_PAIR, 'the set was not rebuilt for B'
    _mouse_drag(pg, 158)
    shift = _hue(pg)
    assert shift > 100, shift
    want = _turned(pg, OTHER_PAIR, shift)
    assert _pair_of(pg, b) == want
    assert _pair_of(pg, a) == SHIPPED
    assert _swatches(pg)[0] == want
    assert pg.locator('#color1-hex').input_value() == want[0]
    assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue']
    _undo(pg)
    assert _pair_of(pg, b) == OTHER_PAIR
    assert _hue(pg) == 0
    # back on A: its own set, and the slider works there too
    _select(pg, a)
    assert _swatches(pg)[0] == SHIPPED
    _mouse_drag(pg, -40)
    shift = _hue(pg)
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, shift)
    assert _pair_of(pg, b) == OTHER_PAIR
    assert errors == []


def test_a_drag_back_to_where_it_began_leaves_nothing_open(page):
    """Out and back in one press: the browser need not fire `change`, the
    screen is as it was, there is no step, and the next selection still
    rebuilds."""
    pg, errors = page
    a, b = _two_screens(pg)
    pg.locator('#quick-palette-hue').scroll_into_view_if_needed()
    x, y = _x_of(pg, 0)
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(_x_of(pg, 90)[0], y, steps=6)
    assert _hue(pg) > 30
    pg.mouse.move(x, y, steps=6)
    pg.mouse.up()
    pg.wait_for_timeout(200)
    assert _hue(pg) == 0
    assert _pair_of(pg, a) == SHIPPED
    assert _steps(pg) == ['Palette Seed']
    _select(pg, b)
    assert _swatches(pg)[0] == OTHER_PAIR
    assert errors == []


def test_undo_and_redo_leave_the_slider_true(page):
    """Undo a drag: the screen, the slider, the readout and the swatches
    all go back, and the readout has nothing left to reset. Redo brings all
    of it forward, and a reset from there lands on the first colors
    exactly."""
    pg, errors = page
    a, _ = _two_screens(pg)
    set_before = _swatches(pg)
    _mouse_drag(pg, 158)
    shift = _hue(pg)
    assert shift > 100, shift
    turned = _pair_of(pg, a)
    assert turned != SHIPPED
    set_turned = _swatches(pg)

    _undo(pg)
    assert _pair_of(pg, a) == SHIPPED
    assert (_hue(pg), _readout(pg)) == (0, '0°')
    assert _swatches(pg) == set_before
    # the readout now has nothing to do
    pg.locator('#quick-palette-hue-reset').click()
    pg.wait_for_timeout(200)
    assert _pair_of(pg, a) == SHIPPED
    assert _steps(pg) == ['Palette Seed']

    _redo(pg)
    assert _pair_of(pg, a) == turned
    assert (_hue(pg), _readout(pg)) == (shift, f'+{shift}°')
    assert _swatches(pg) == set_turned
    # reset from a redo: the screen's first colors, to the digit, one step
    pg.locator('#quick-palette-hue-reset').click()
    pg.wait_for_timeout(200)
    assert _pair_of(pg, a) == SHIPPED
    assert _hue(pg) == 0
    assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue', 'Adjust Palette Hue']
    _undo(pg)
    assert _pair_of(pg, a) == turned and _hue(pg) == shift
    # and the slider drags on from where it now says it is
    _mouse_drag(pg, shift - 30)
    moved = _hue(pg)
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, moved)
    assert errors == []


def test_undo_walks_the_slider_back_through_each_drag(page):
    pg, errors = page
    a, _ = _two_screens(pg)
    _mouse_drag(pg, 30)
    first, first_pair = _hue(pg), _pair_of(pg, a)
    _mouse_drag(pg, 70)
    second, second_pair = _hue(pg), _pair_of(pg, a)
    assert 0 < first < second
    _undo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (first, first_pair)
    _undo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (0, SHIPPED)
    _redo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (first, first_pair)
    _redo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (second, second_pair)
    assert errors == []


def test_undo_past_another_edit_keeps_the_slider_true(page):
    """A step that has nothing to do with the slider carries the slider as
    it stood, and a step taken on another screen's set reads 0 for the set
    on show: 0 always means the colors the screen has now."""
    pg, errors = page
    a, b = _two_screens(pg)
    _mouse_drag(pg, 45)
    shift, turned = _hue(pg), _pair_of(pg, a)
    pg.evaluate("""() => { const a = window.app; a.currentLayer.name = 'Renamed';
        a.updateLayers([a.currentLayer]); a.saveState('Rename'); }""")
    _undo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (shift, turned)
    _redo(pg)
    assert (_hue(pg), _pair_of(pg, a)) == (shift, turned)
    # another screen: its own set at 0, then undo while it is selected
    _select(pg, b)
    assert _hue(pg) == 0
    _mouse_drag(pg, 60)
    assert _pair_of(pg, b) != OTHER_PAIR
    _undo(pg)
    assert _pair_of(pg, b) == OTHER_PAIR and _hue(pg) == 0
    _undo(pg)              # the rename, on A, with B selected
    assert _hue(pg) == 0
    _mouse_drag(pg, 20)
    assert _pair_of(pg, b) == _turned(pg, OTHER_PAIR, _hue(pg))
    assert _pair_of(pg, a) == turned
    assert errors == []


def _catch_toasts(pg):
    pg.evaluate("""() => {
        const app = window.app;
        window.__toasts = [];
        if (!app.__qpToast) {
            app.__qpToast = app._toast;
            app._toast = function (msg) {
                window.__toasts.push(String(msg));
                return app.__qpToast.apply(this, arguments);
            };
        }
    }""")


def _toasts(pg):
    return pg.evaluate("() => window.__toasts")


def _lock(pg, *ids):
    """Lock the way the app does: the step is taken as the PUT goes out, so
    the server's echo lands on the screens after it, as it does in a show."""
    pg.evaluate("""async (ids) => {
        const app = window.app;
        const layers = ids.map(id => app.project.layers.find(l => l.id === id));
        layers.forEach(l => { l.locked = true; });
        app.updateLayers(layers);
        app.resetHistory('Palette Seed');
        await Promise.all([...(app._inflightLayerPuts || [])]);
    }""", list(ids))
    pg.wait_for_timeout(200)


def test_a_drag_on_a_locked_screen_changes_nothing_and_the_slider_goes_back(page):
    pg, errors = page
    a, _ = _two_screens(pg)
    _catch_toasts(pg)
    _lock(pg, a)
    set_before = _swatches(pg)
    try:
        _mouse_drag(pg, 158)
        pg.wait_for_timeout(600)            # past any debounce that might land a step
        said = _toasts(pg)
        assert len(said) == 1 and 'is locked' in said[0], said
        assert _pair_of(pg, a) == SHIPPED
        assert _steps(pg) == ['Palette Seed'], 'an empty undo step'
        assert (_hue(pg), _readout(pg)) == (0, '0°')
        assert _swatches(pg) == set_before
        # a second try says it again, and still changes nothing
        pg.evaluate("() => { window.__toasts = []; }")
        _mouse_drag(pg, -90)
        pg.wait_for_timeout(300)
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _pair_of(pg, a) == SHIPPED and _hue(pg) == 0
        # the keys and a click on the track are refused the same way
        pg.evaluate("() => { window.__toasts = []; }")
        pg.locator('#quick-palette-hue').focus()
        pg.keyboard.press('ArrowRight')
        pg.wait_for_timeout(200)
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _hue(pg) == 0 and _pair_of(pg, a) == SHIPPED
        pg.evaluate("() => { window.__toasts = []; }")
        x, y = _x_of(pg, 120)
        pg.mouse.click(x, y)
        pg.wait_for_timeout(200)
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _hue(pg) == 0 and _pair_of(pg, a) == SHIPPED
        assert _steps(pg) == ['Palette Seed']
        # nothing is left waiting to land
        pg.evaluate("() => window.app._flushPendingSaveState()")
        assert _steps(pg) == ['Palette Seed']
    finally:
        _unlock_all(pg)
    # unlocked, the very next drag works and undoes in one step
    _mouse_drag(pg, 50)
    shift = _hue(pg)
    assert shift > 20
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, shift)
    assert _steps(pg)[-1] == 'Adjust Palette Hue'
    _undo(pg)
    assert _pair_of(pg, a) == SHIPPED and _hue(pg) == 0
    assert errors == []


def test_a_locked_drag_leaves_no_step_on_a_screen_as_it_was_loaded(page):
    """The first PUT of a screen as the server loaded it comes back with
    fields tidied, so a refused drag that still sent one read as a change
    in history: an Adjust Palette Hue step with nothing in it. A refused
    drag sends nothing."""
    pg, errors = page
    _two_screens(pg)
    # a screen the server made and no edit has PUT since
    fresh = pg.evaluate("""async () => {
        const res = await fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: '{}'});
        return (await res.json()).id;
    }""")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.project.layers.length > 0")
    pg.wait_for_timeout(800)
    try:
        _select(pg, fresh)
        pair = _pair_of(pg, fresh)
        pg.evaluate("() => window.app.setLockOnSelected(true)")
        pg.wait_for_timeout(300)
        before = _steps(pg)
        assert before[-1] == 'Lock Layers'
        _mouse_drag(pg, 158)
        pg.wait_for_timeout(700)            # past the 400 ms the step used to wait
        assert _steps(pg) == before, 'an empty undo step'
        assert _hue(pg) == 0 and _pair_of(pg, fresh) == pair
    finally:
        _unlock_all(pg)
        pg.evaluate("""async (id) => {
            await fetch(`/api/layer/${id}`, {method: 'DELETE'});
            await window.app.loadProject();
        }""", fresh)
        pg.wait_for_timeout(500)
    assert errors == []


def test_a_swatch_on_a_locked_screen_leaves_no_step(page):
    pg, errors = page
    a, _ = _two_screens(pg)
    _catch_toasts(pg)
    _lock(pg, a)
    try:
        pg.locator('#quick-palette-4').click()
        pg.wait_for_timeout(300)
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _pair_of(pg, a) == SHIPPED
        assert _steps(pg) == ['Palette Seed']
    finally:
        _unlock_all(pg)
    assert errors == []


def test_a_slider_locked_after_it_moved_keeps_its_place(page):
    """Reset on a screen locked at +N is refused too: the screen keeps its
    colors, so the slider keeps saying +N."""
    pg, errors = page
    a, _ = _two_screens(pg)
    _catch_toasts(pg)
    _mouse_drag(pg, 40)
    shift, turned = _hue(pg), _pair_of(pg, a)
    # Locked the way the Lock button does it (setLockOnSelected: the flag and
    # its PUT). A bare `locked = true` with the drag's PUT still out was put
    # back by that PUT's reply, which carries the screen unlocked.
    pg.evaluate("""async () => {
        window.app.setLockOnSelected(true);
        await window.app._layerSavesSettled();
    }""")
    try:
        before = _steps(pg)
        pg.locator('#quick-palette-hue-reset').click()
        pg.wait_for_timeout(200)
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _pair_of(pg, a) == turned and _hue(pg) == shift
        assert _steps(pg) == before
    finally:
        _unlock_all(pg)
    pg.locator('#quick-palette-hue-reset').click()
    pg.wait_for_timeout(200)
    assert _pair_of(pg, a) == SHIPPED and _hue(pg) == 0
    assert errors == []


def test_a_mixed_selection_turns_the_unlocked_screen_only(page):
    """The app's rule for any edit: the unlocked screens take it, the
    locked ones are named in one error. The slider moves, it is true of
    the screen that took it, and the locked screen joins from where it is
    once unlocked."""
    pg, errors = page
    a, b = _two_screens(pg)
    _catch_toasts(pg)
    pg.evaluate("""async ([a, b]) => {
        const app = window.app;
        // locked as the Lock button does it, the flag with its PUT
        app.setSelectedLayersByIds([b], b);
        app.setLockOnSelected(true);
        await app._layerSavesSettled();
        app.setSelectedLayersByIds([a, b], a);
        app.resetHistory('Palette Seed');
    }""", [a, b])
    pg.wait_for_timeout(200)
    try:
        _mouse_drag(pg, 60)
        pg.wait_for_timeout(200)
        shift = _hue(pg)
        assert shift > 20
        assert len(_toasts(pg)) == 1, _toasts(pg)
        assert _pair_of(pg, a) == _turned(pg, SHIPPED, shift)
        assert _pair_of(pg, b) == OTHER_PAIR
        assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue']
    finally:
        _unlock_all(pg)
    pg.locator('#quick-palette-hue').focus()
    pg.keyboard.press('ArrowRight')
    pg.wait_for_timeout(200)
    assert _hue(pg) == shift + 1
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, shift + 1)
    assert _pair_of(pg, b) == _turned(pg, OTHER_PAIR, 1)
    pg.locator('#quick-palette-hue').blur()
    assert errors == []


def test_a_run_of_arrow_keys_is_one_undo_step_however_slow(page):
    """Tap, look at the wall, tap: one adjustment, the same as a drag. The
    step lands when the person leaves the slider; a tap after that is a new
    adjustment."""
    pg, errors = page
    a, _ = _two_screens(pg)
    hue = pg.locator('#quick-palette-hue')
    offset = pg.evaluate("() => [window.app.currentLayer.offset_x, window.app.currentLayer.offset_y]")
    hue.focus()
    for _ in range(3):
        pg.keyboard.press('ArrowRight')
        pg.wait_for_timeout(500)            # past the 400 ms a pause used to end it
    assert _hue(pg) == 3
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, 3)
    # the arrows belong to the slider: the screen did not nudge
    assert pg.evaluate(
        "() => [window.app.currentLayer.offset_x, window.app.currentLayer.offset_y]") == offset
    # Undo with the slider still focused takes the whole run back
    pg.keyboard.press('Control+z')
    pg.wait_for_timeout(300)
    assert _pair_of(pg, a) == SHIPPED and _hue(pg) == 0
    assert _steps(pg) == ['Palette Seed']
    _redo(pg)
    assert _hue(pg) == 3 and _pair_of(pg, a) == _turned(pg, SHIPPED, 3)
    _undo(pg)

    # leaving the slider ends the run; a later run is its own step
    hue.focus()
    pg.keyboard.press('ArrowRight')
    pg.wait_for_timeout(450)
    pg.keyboard.press('ArrowRight')
    hue.blur()
    pg.wait_for_timeout(100)
    assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue']
    hue.focus()
    pg.keyboard.press('ArrowLeft')
    pg.wait_for_timeout(450)
    pg.keyboard.press('ArrowLeft')
    pg.wait_for_timeout(450)
    pg.keyboard.press('ArrowLeft')
    hue.blur()
    pg.wait_for_timeout(100)
    assert _hue(pg) == -1
    assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue', 'Adjust Palette Hue']
    _undo(pg)
    assert _hue(pg) == 2 and _pair_of(pg, a) == _turned(pg, SHIPPED, 2)
    _undo(pg)
    assert _hue(pg) == 0 and _pair_of(pg, a) == SHIPPED
    # out and back in one run changes nothing and takes no step
    hue.focus()
    pg.keyboard.press('ArrowRight')
    pg.wait_for_timeout(450)
    pg.keyboard.press('ArrowLeft')
    hue.blur()
    pg.wait_for_timeout(100)
    assert _hue(pg) == 0 and _pair_of(pg, a) == SHIPPED
    assert _steps(pg) == ['Palette Seed']
    assert errors == []


def test_a_key_run_stays_its_own_step_beside_a_drag_and_a_new_selection(page):
    pg, errors = page
    a, b = _two_screens(pg)
    hue = pg.locator('#quick-palette-hue')
    hue.focus()
    pg.keyboard.press('ArrowRight')
    pg.keyboard.press('ArrowRight')
    # a drag straight after: the keys are one step, the drag another
    _mouse_drag(pg, 40)
    shift = _hue(pg)
    assert _steps(pg) == ['Palette Seed', 'Adjust Palette Hue', 'Adjust Palette Hue']
    _undo(pg)
    assert _hue(pg) == 2 and _pair_of(pg, a) == _turned(pg, SHIPPED, 2)
    _redo(pg)
    assert _hue(pg) == shift
    # keys, then another screen with focus still on the slider
    hue.focus()
    pg.keyboard.press('ArrowRight')
    _select(pg, b)
    assert len(_steps(pg)) == 4
    assert _swatches(pg)[0] == OTHER_PAIR and _hue(pg) == 0
    hue.focus()
    pg.keyboard.press('ArrowRight')
    pg.wait_for_timeout(100)
    assert _pair_of(pg, b) == _turned(pg, OTHER_PAIR, 1)
    assert _pair_of(pg, a) == _turned(pg, SHIPPED, shift + 1)
    hue.blur()
    assert errors == []


def test_a_swatch_at_an_offset_then_the_slider_turns_from_the_swatch(page):
    """The slider measures from the colors the screen has: a swatch picked
    at +N is the new start, and a move runs from it."""
    pg, errors = page
    a, _ = _two_screens(pg)
    _mouse_drag(pg, 30)
    shift = _hue(pg)
    pair = _swatches(pg)[3]
    pg.locator('#quick-palette-4').click()
    pg.wait_for_timeout(200)
    assert _pair_of(pg, a) == pair and _hue(pg) == shift
    _mouse_drag(pg, shift + 40)
    moved = _hue(pg)
    assert _pair_of(pg, a) == _turned(pg, pair, moved - shift)
    # Shuffle starts a new set at 0 from the colors the screen has now
    now = _pair_of(pg, a)
    pg.locator('#quick-palette-shuffle').click()
    pg.wait_for_timeout(200)
    assert _hue(pg) == 0 and _pair_of(pg, a) == now
    _mouse_drag(pg, 25)
    assert _pair_of(pg, a) == _turned(pg, now, _hue(pg))
    assert errors == []


def test_a_project_opened_at_an_offset_starts_the_slider_at_0(page):
    pg, errors = page
    a, _ = _two_screens(pg)
    _mouse_drag(pg, 80)
    assert _hue(pg) != 0
    pg.evaluate("() => { window.app.resetHistory('Palette Seed'); }")
    pg.wait_for_timeout(200)
    assert (_hue(pg), _readout(pg)) == (0, '0°')
    assert _swatches(pg)[0] == _pair_of(pg, a)
    assert errors == []


# ── the field guard (helpers.js installFieldGuard) ───────────────────────

def test_the_field_guard_leaves_the_slider_and_its_fields_alone(page):
    """The guard refuses a value neither page script nor the person put in
    a field. A range is a control, not a field, so it never comes into it:
    with the guard running as it does for a person, a real drag and the
    app's own writes go through, a refused log never appears, and the Hex
    fields the slider writes to still take typing afterwards."""
    pg, errors = page
    a, _ = _two_screens(pg)
    pg.evaluate("""() => {
        window.__lrdFieldGuardLive = true;
        window.__logs = [];
        window.__beacon = navigator.sendBeacon;
        navigator.sendBeacon = (url, blob) => {
            blob.text().then(t => window.__logs.push(JSON.parse(t)));
            return true;
        };
    }""")

    def refused():
        return [e for e in pg.evaluate("() => window.__logs")
                if e['action'] == 'autofill_refused']

    try:
        assert pg.evaluate("() => document.__lrdFieldGuard === true")
        pg.evaluate("""() => {
            window.__trusted = [];
            document.getElementById('quick-palette-hue').addEventListener(
                'input', (e) => window.__trusted.push(e.isTrusted));
        }""")
        _mouse_drag(pg, 100)
        shift = _hue(pg)
        assert shift > 50
        # the browser's own input, the kind the guard reads as the person's
        trusted = pg.evaluate("() => window.__trusted")
        assert trusted and all(trusted), trusted
        turned = _turned(pg, SHIPPED, shift)
        assert _pair_of(pg, a) == turned
        assert pg.locator('#color1-hex').input_value() == turned[0]
        assert pg.locator('#color2-hex').input_value() == turned[1]
        # the app's own value writes on the slider: Undo, and the readout
        _undo(pg)
        assert _hue(pg) == 0
        _redo(pg)
        assert _hue(pg) == shift
        pg.locator('#quick-palette-hue-reset').click()
        pg.wait_for_timeout(200)
        assert _hue(pg) == 0 and _pair_of(pg, a) == SHIPPED
        # the keys, and the guide's scripted write and events
        pg.locator('#quick-palette-hue').focus()
        pg.keyboard.press('ArrowRight')
        pg.locator('#quick-palette-hue').blur()
        assert _hue(pg) == 1
        pg.evaluate("""() => {
            const s = document.getElementById('quick-palette-hue');
            s.value = '9';
            s.dispatchEvent(new Event('input', {bubbles: true}));
            s.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        assert _hue(pg) == 9 and _pair_of(pg, a) == _turned(pg, SHIPPED, 9)
        # a real typed edit in the field the slider wrote to
        hexbox = pg.locator('#color1-hex')
        hexbox.click()
        hexbox.press('Control+a')
        hexbox.press_sequentially('#123456')
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(300)
        assert _pair_of(pg, a)[0] == '#123456'
        pg.wait_for_timeout(300)
        assert refused() == []
    finally:
        pg.evaluate("""() => {
            delete window.__lrdFieldGuardLive;
            navigator.sendBeacon = window.__beacon;
        }""")
    assert errors == []


def test_a_real_palette_source_pick_passes_the_field_guard(page):
    """The Palettes tab's one guarded field: a real pick on the select, and
    the app's own write to it when a color changes."""
    pg, errors = page
    _fresh_screen(pg)
    pg.evaluate("() => { window.__lrdFieldGuardLive = true; }")
    try:
        pg.evaluate("() => window.app.openPreferencesModal()")
        pg.wait_for_timeout(300)
        pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="palettes"]').click()
        src = pg.locator('#pref-quick-palette-source')
        src.focus()
        pg.keyboard.press('ArrowDown')
        pg.wait_for_timeout(100)
        assert src.input_value() == 'custom'
        assert not pg.evaluate("""() => document.getElementById('pref-quick-palette-grid')
            .classList.contains('pm-qp-auto')""")
        pg.keyboard.press('ArrowUp')
        pg.wait_for_timeout(100)
        assert src.input_value() == 'auto'
        pg.evaluate("""() => {
            const el = document.getElementById('pref-quick-palette-3b');
            el.value = '#abcdef'; el.dispatchEvent(new Event('input', {bubbles: true}));
        }""")
        assert src.input_value() == 'custom'
    finally:
        pg.evaluate("""() => {
            delete window.__lrdFieldGuardLive;
            const c = document.getElementById('preferences-cancel');
            if (c) c.click();
        }""")
    assert errors == []


# ── the guide and What's New ─────────────────────────────────────────────

# Every Advanced Guide step 1.7.0 brings, in guide order.
NEW_IN_1_7 = ['quickPalettes', 'processorIp', 'riggingTab', 'riggingSizes', 'riggingAuto', 'riggingDrag',
              'riggingCustom', 'riggingSide', 'riggingTotals', 'riggingCurve',
              's3dOpen', 's3dSelect', 's3dLook', 's3dHandles', 's3dCurve', 's3dYaw', 's3dCamera', 's3dFocus',
              's3dBars', 's3dJoint',
              'outputOpen', 'outputChoices',
              'idmOpen', 'idmModules', 'idmMarkColor', 'idmMarkX', 'idmField', 'idmModuleIds',
              'idmColors', 'idmHighlight', 'idmPointer', 'idmController', 'idmList', 'notesChecklist', 'groupDrag',
              'riggingSheet', 'objExport', 'checkUpdates']


def test_the_guide_step_shows_the_palettes(page):
    """The Advanced Guide's step, played on its own the way What's New's
    Show me plays it: the wall takes a pair, Hue turns it, and leaving the
    guide puts back the person's colors with the slider at 0."""
    pg, errors = page
    a, _ = _two_screens(pg)
    _mouse_drag(pg, 25)
    mine, shift = _pair_of(pg, a), _hue(pg)
    assert pg.evaluate("""() => {
        const q = window.QuickStart, keys = q.tours().advanced
            .map(s => Object.keys(q.steps()).find(k => q.steps()[k] === s));
        return keys[keys.indexOf('blankCabinet') + 1] === 'quickPalettes'
            && q.steps().quickPalettes.since === '1.7.0';
    }""")
    assert pg.evaluate("() => window.QuickStart.newSteps('1.6.0', '1.7.0')") == NEW_IN_1_7
    pg.evaluate("() => { window.QuickStart.setSpeed(6); window.QuickStart.startSteps(['quickPalettes']); }")
    pg.wait_for_function("""() => {
        const c = document.getElementById('qs-callout');
        return c && c.getAttribute('data-qs-state') === 'done';
    }""", timeout=30000)
    note = pg.locator('#qs-callout .qs-result').text_content()
    assert 'Hue turned it' in note and '60°' in note, note
    assert _hue(pg) == 60 and _readout(pg) == '+60°'
    assert pg.locator('#quick-palette-swatches [aria-pressed="true"]').count() == 1
    assert _steps(pg)[-1] == 'Adjust Palette Hue'
    pg.evaluate("() => window.QuickStart.end()")
    pg.wait_for_function("() => !window.QuickStart.state().running && !window.QuickStart.state().visible")
    pg.wait_for_timeout(500)
    assert _pair_of(pg, a) == mine
    assert _hue(pg) == 0, 'the slider kept the guide\'s offset'
    assert _swatches(pg)[0] == mine
    # the slider measures from the person's colors again
    _mouse_drag(pg, 30)
    assert _pair_of(pg, a) == _turned(pg, mine, _hue(pg))
    assert errors == []


def test_whats_new_offers_the_step_for_1_7(page):
    pg, errors = page
    got = pg.evaluate("() => window.WhatsNew.decide('1.7.0', '1.6.0')")
    assert got['show'] and got['window']['key'] == '1.7', got
    assert got['window']['steps'] == NEW_IN_1_7, got
    assert errors == []
