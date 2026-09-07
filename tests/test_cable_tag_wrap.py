"""Cable tags wrap at their spaces the way port labels do.

"also we should add wrapping like we did to port labels on cable extensions
such as Snake 1 SR A would be / Snake 1 / SR A" (user, 2026-09-07). The
cable tag - the small pill beside a label when "show cable tags" is on: a
power circuit's "10' True1", a data port's "50' CAT" or "SR Primary Snake
+10'" - used to draw as ONE line however long it ran. canvas.js now lays it
out through cableTagLayout(text, labelSize) -> { lines, width, height }:

  - a tag wider than 4.5 x labelSize on one line splits at whitespace into
    the fewest lines (at most 3) whose widest line fits that cap;
  - a bare number or single character is a name's suffix ("Snake 1",
    "SR A") and never starts a line, so the user's example splits as
    ["Snake 1", "SR A"];
  - a tag that fits, or has nowhere to break, draws exactly as before: one
    text call, a size + 4 pill;
  - a wrapped pill is lines x lineHeight + 4 tall, the widest line plus
    padding wide, its lines left-aligned and centred on y, and it keeps
    the one-line pill's corner radius;
  - cableTagWidth is the wrapped width (the flip-inside rule keeps working);
  - the greedy balanced split is ONE helper (_balancedSplit) shared with the
    port label's _layoutCircleLabel, whose old result is pinned here.

Everything calls the renderer directly on the shared page (no project is
touched), spying on ctx.fillText / ctx.roundRect the way test_nfer_tags.py
does.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_cable_tag_wrap.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


HELPERS_JS = """
window.__tw = {
    // The tag's own register: the font it is measured and drawn in.
    register(labelSize) {
        const size = Math.max(8, labelSize * 0.7);
        return { size, padX: size * 0.45, cap: labelSize * 4.5 };
    },
    // Each string's width in the tag font, as the renderer measures it.
    measure(strings, labelSize) {
        const ctx = window.canvasRenderer.ctx;
        const { size } = this.register(labelSize);
        ctx.save();
        ctx.font = 'bold ' + size + 'px ' + (window.app.getProjectFont
            ? window.app.getProjectFont() : 'Arial');
        const out = strings.map(s => ctx.measureText(s).width);
        ctx.restore();
        return out;
    },
    layout(text, labelSize) {
        const l = window.canvasRenderer.cableTagLayout(text, labelSize);
        return { lines: l.lines, width: l.width, height: l.height };
    },
    width(text, labelSize) {
        return window.canvasRenderer.cableTagWidth(text, labelSize);
    },
    // One drawCableTag call at (100, 100), every text call and the pill's
    // roundRect captured in order.
    draw(text, labelSize, opts, printer) {
        const r = window.canvasRenderer, ctx = r.ctx;
        const oT = ctx.fillText, oR = ctx.roundRect;
        const texts = [], rects = [];
        ctx.fillText = function (t, x, y, w) {
            texts.push({ t: String(t), x, y });
            return oT.call(ctx, t, x, y, w);
        };
        ctx.roundRect = function (x, y, w, h, rad) {
            rects.push({ x, y, w, h, rad });
            return oR.call(ctx, x, y, w, h, rad);
        };
        const prevPrinter = r.printerMode;
        if (printer) r.printerMode = true;
        try {
            r.drawCableTag(text, 100, 100, labelSize, undefined, opts || {});
        } finally {
            ctx.fillText = oT;
            ctx.roundRect = oR;
            r.printerMode = prevPrinter;
        }
        return { texts, rects };
    },
    // The port label's layout, in its own font, as the data pass calls it
    // (labelSize 30: natural radius 36, padding 6).
    portLabel(label, fontPx, minRadius, padding) {
        const r = window.canvasRenderer, ctx = r.ctx;
        ctx.save();
        ctx.font = 'bold ' + fontPx + 'px ' + (window.app.getProjectFont
            ? window.app.getProjectFont() : 'Arial');
        try { return r._layoutCircleLabel(label, fontPx, minRadius, padding); }
        finally { ctx.restore(); }
    },
    // The greedy split as _layoutCircleLabel carried it before the helper
    // was pulled out, next to the helper's answer for the same input.
    oldVsNew(label, fontPx, n) {
        const r = window.canvasRenderer, ctx = r.ctx;
        ctx.save();
        ctx.font = 'bold ' + fontPx + 'px ' + (window.app.getProjectFont
            ? window.app.getProjectFont() : 'Arial');
        try {
            const widthOf = (s) => ctx.measureText(s).width;
            const tokens = label.trim().split(/\\s+/).filter(t => t.length > 0);
            const target = widthOf(label) / n;
            const lines = [];
            let cur = tokens[0];
            for (let i = 1; i < tokens.length; i++) {
                const joined = cur + ' ' + tokens[i];
                if (lines.length < n - 1 && widthOf(joined) > target) {
                    lines.push(cur);
                    cur = tokens[i];
                } else {
                    cur = joined;
                }
            }
            lines.push(cur);
            return { old: lines,
                     fresh: r._balancedSplit(tokens, n, widthOf, widthOf(label)) };
        } finally { ctx.restore(); }
    },
};
"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


LONG = "SR Primary Snake +10'"
USERS = "Snake 1 SR A"


def _register(page, label_size):
    return page.evaluate("(L) => window.__tw.register(L)", label_size)


def _measure(page, strings, label_size):
    return page.evaluate("([s, L]) => window.__tw.measure(s, L)",
                         [strings, label_size])


def _draw(page, text, label_size, opts=None, printer=False):
    return page.evaluate("([t, L, o, p]) => window.__tw.draw(t, L, o, p)",
                         [text, label_size, opts or {}, printer])


def _layout(page, text, label_size):
    return page.evaluate("([t, L]) => window.__tw.layout(t, L)",
                         [text, label_size])


# -- a short tag is untouched ------------------------------------------------

def test_a_short_tag_draws_one_line_unchanged(page):
    """"10' True1" at label size 30: one text call with the whole text, the
    old size + 4 pill with its capsule corner, left-aligned one pad in."""
    reg = _register(page, 30)
    out = _draw(page, "10' True1", 30)
    assert [t['t'] for t in out['texts']] == ["10' True1"], out
    assert len(out['rects']) == 1, out
    pill = out['rects'][0]
    (tw,) = _measure(page, ["10' True1"], 30)
    assert pill['h'] == pytest.approx(reg['size'] + 4)
    assert pill['rad'] == pytest.approx((reg['size'] + 4) / 2)
    assert pill['w'] == pytest.approx(tw + reg['padX'] * 2)
    assert pill['y'] == pytest.approx(100 - pill['h'] / 2)
    assert out['texts'][0]['x'] == pytest.approx(pill['x'] + reg['padX'])
    assert out['texts'][0]['y'] == 100
    lay = _layout(page, "10' True1", 30)
    assert lay['lines'] == ["10' True1"]
    assert lay['height'] == pytest.approx(reg['size'] + 4)


def test_a_tag_with_no_space_never_wraps(page):
    """Nowhere legal to break: one line, however wide it runs."""
    text = "Verylongsnakename+10'"
    reg = _register(page, 10)
    (tw,) = _measure(page, [text], 10)
    assert tw > reg['cap'], 'test premise broken: the text fits the cap'
    out = _draw(page, text, 10)
    assert [t['t'] for t in out['texts']] == [text], out
    assert _layout(page, text, 10)['lines'] == [text]


# -- a long tag wraps --------------------------------------------------------

def test_a_long_tag_wraps_to_the_fewest_lines_under_the_cap(page):
    """"SR Primary Snake +10'" at label size 30 runs past 4.5 x 30 on one
    line and comes out as two, each under the cap, drawn in order as a
    stack centred on y; the pill is lines x lineHeight + 4 tall, the widest
    line plus padding wide, and keeps the one-line corner radius."""
    reg = _register(page, 30)
    (one,) = _measure(page, [LONG], 30)
    assert one > reg['cap'], 'test premise broken: the tag fits on one line'

    lay = _layout(page, LONG, 30)
    assert len(lay['lines']) == 2, lay
    assert ' '.join(lay['lines']) == LONG, 'wrapping changed the text'
    widths = _measure(page, lay['lines'], 30)
    assert all(w <= reg['cap'] for w in widths), (lay, widths, reg)

    out = _draw(page, LONG, 30)
    assert [t['t'] for t in out['texts']] == lay['lines'], out
    ys = [t['y'] for t in out['texts']]
    assert ys == sorted(ys), 'lines must draw top to bottom'
    assert ys[1] - ys[0] == pytest.approx(reg['size']), 'leading is the tag size'
    assert sum(ys) / len(ys) == pytest.approx(100), 'the stack centres on y'
    assert len({t['x'] for t in out['texts']}) == 1, 'lines are left-aligned'

    pill = out['rects'][0]
    assert pill['h'] == pytest.approx(2 * reg['size'] + 4)
    assert pill['w'] == pytest.approx(max(widths) + reg['padX'] * 2)
    assert pill['rad'] == pytest.approx((reg['size'] + 4) / 2), \
        'a taller box keeps the one-line pill corner, not a capsule'
    assert pill['y'] == pytest.approx(100 - pill['h'] / 2)
    assert lay['width'] == pytest.approx(pill['w'])
    assert lay['height'] == pytest.approx(pill['h'])


def test_the_users_example_splits_at_the_name(page):
    """"Snake 1 SR A" -> "Snake 1" / "SR A" (the user's own split), at a
    label size where it does not fit the cap. The bare "1" and the lone "A"
    are suffixes of the word before them and never start a line."""
    reg = _register(page, 10)
    (one,) = _measure(page, [USERS], 10)
    assert one > reg['cap'], 'test premise broken: the tag fits on one line'
    lay = _layout(page, USERS, 10)
    assert lay['lines'] == ['Snake 1', 'SR A'], lay
    out = _draw(page, USERS, 10)
    assert [t['t'] for t in out['texts']] == ['Snake 1', 'SR A'], out


def test_three_lines_is_the_most_a_tag_takes(page):
    """A tag that needs more than three lines to meet the cap stops at
    three - the three-line split stands as the narrowest the tag gets."""
    text = "Alpha Bravo Charlie Delta Echo Foxtrot"
    lay = _layout(page, text, 8)
    assert len(lay['lines']) == 3, lay
    assert ' '.join(lay['lines']) == text


# -- the width the flip rule reads ------------------------------------------

@pytest.mark.parametrize('text,label_size', [
    ("10' True1", 30), (LONG, 30), (USERS, 10), ("50' CAT", 24),
])
def test_cable_tag_width_is_the_widest_line_plus_padding(page, text, label_size):
    """cableTagWidth = gap + widest wrapped line + padding, so a wrapped
    tag flips inside the screen on its wrapped width, not its one-line one."""
    reg = _register(page, label_size)
    lay = _layout(page, text, label_size)
    widths = _measure(page, lay['lines'], label_size)
    expected = label_size * 0.25 + max(widths) + reg['padX'] * 2
    got = page.evaluate("([t, L]) => window.__tw.width(t, L)", [text, label_size])
    assert got == pytest.approx(expected), (text, lay, got, expected)


# -- printer page ------------------------------------------------------------

def test_printer_mode_draws_the_same_lines(page):
    """The binder's printer page goes through this same drawer: the same
    lines, in the same order, at the same anchors."""
    screen = _draw(page, LONG, 30)
    printer = _draw(page, LONG, 30, printer=True)
    assert len(screen['texts']) == 2, screen
    assert [t['t'] for t in printer['texts']] == [t['t'] for t in screen['texts']]
    assert [(t['x'], t['y']) for t in printer['texts']] \
        == [(t['x'], t['y']) for t in screen['texts']]
    assert printer['rects'] == screen['rects']


# -- a tall tag stays inside the screen -------------------------------------

def test_a_tall_tag_stays_inside_the_screen(page):
    """Handed the screen's top and bottom, a wrapped pill shifts inside
    them; without them (or with room) it sits centred on y as always."""
    free = _draw(page, LONG, 30)
    pill = free['rects'][0]
    assert pill['y'] == pytest.approx(100 - pill['h'] / 2)

    # Top edge just under the pill's natural top: it moves down to it.
    top = pill['y'] + 5
    clamped = _draw(page, LONG, 30, {'top': top, 'bottom': 1000})
    cp = clamped['rects'][0]
    assert cp['y'] == pytest.approx(top), (pill, cp)
    assert cp['h'] == pytest.approx(pill['h'])
    # The text moved with the pill, still centred in it.
    ys = [t['y'] for t in clamped['texts']]
    assert sum(ys) / len(ys) == pytest.approx(cp['y'] + cp['h'] / 2)

    # Bottom edge above the pill's natural bottom: it moves up to it.
    bottom = pill['y'] + pill['h'] - 5
    clamped = _draw(page, LONG, 30, {'top': -1000, 'bottom': bottom})
    cp = clamped['rects'][0]
    assert cp['y'] + cp['h'] == pytest.approx(bottom), (pill, cp)

    # Plenty of room: untouched.
    roomy = _draw(page, LONG, 30, {'top': -1000, 'bottom': 1000})
    assert roomy['rects'] == free['rects']


# -- the shared helper keeps the port label's old result ----------------------

def test_the_port_label_wrap_still_gives_its_old_result(page):
    """_layoutCircleLabel goes through the shared _balancedSplit now: the
    known "SR A1" still stacks as "SR" over "A1", and on longer labels the
    helper returns exactly what the greedy it replaced returned."""
    lay = page.evaluate("() => window.__tw.portLabel('SR A1', 30, 36, 6)")
    assert lay['lines'] == ['SR', 'A1'], lay
    assert lay['radius'] < page.evaluate(
        "() => window.__tw.portLabel('SRA1SRA1', 30, 36, 6).radius"), \
        'the wrap must still shrink the circle'
    one = page.evaluate("() => window.__tw.portLabel('A B', 30, 36, 6)")
    assert one['lines'] == ['A B'], one

    for label in ('SR Primary Snake Feed A1', 'Snake 1 SR A', 'SR A1 B2 C3'):
        for n in (2, 3, 4):
            out = page.evaluate("([l, n]) => window.__tw.oldVsNew(l, 30, n)",
                                [label, n])
            assert out['fresh'] == out['old'], (label, n, out)
