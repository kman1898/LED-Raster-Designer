#!/usr/bin/env python3
"""Capture the README's pictures from the app itself, into .github/media/.

What it makes (OUTPUTS, below):

    pixel-map.png, cabinet-id.png, show-look.png, data.png, power.png
        one screenshot per main view tab, the demo wall framed in the canvas
    demo.gif
        a short loop of the app in use: the views in turn, and the processor
        dragged onto the wall in the Data view, its ports landing
    social-preview.png
        1280 x 640, for the repository's social preview (Settings -> General)

The show is the guides' demo show (src/static/js/quickstart.js), taken from
the shipped src/static/data/tour_snapshots.json: the Advanced Guide's last
entry snapshot before it adds a second screen - one 12 x 6 wall with its
processor, snakes, distro and multis all attached. Nothing private is read.

How it runs: a FRESH server on a free port, the way tests/conftest.py's
e2e_server starts one - an empty in-memory project and preferences, and the
named layouts, distro presets and cable stock presets pointed at scratch
files in a temporary folder - so a run never reads or writes a person's own
project or preferences. A headless Chromium drives it; the server is shut
down at the end. Every gesture is placed by the script, frame by frame, so
two runs give the same pictures.

Run it after a release changes how the views look:

    python scripts/capture_readme_media.py
    python scripts/capture_readme_media.py --only data.png

tests/test_readme_media.py checks that every file here exists, that README.md
shows each one, and that nothing in .github/media is left unreferenced.
"""

import argparse
import base64
import copy
import io
import json
import logging
import math
import os
import shutil
import sys
import tempfile
import threading
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
MEDIA = os.path.join(ROOT, '.github', 'media')
SNAPSHOTS = os.path.join(SRC, 'static', 'data', 'tour_snapshots.json')
ICON = os.path.join(SRC, 'icon.png')

# One screenshot per main view tab: (file, the tab's data-mode).
TABS = (
    ('pixel-map.png', 'pixel-map'),
    ('cabinet-id.png', 'cabinet-id'),
    ('show-look.png', 'show-look'),
    ('data.png', 'data-flow'),
    ('power.png', 'power'),
)
GIF = 'demo.gif'
SOCIAL = 'social-preview.png'
# Every file this script writes into .github/media. tests/test_readme_media.py
# reads this list.
OUTPUTS = tuple(name for name, _ in TABS) + (GIF, SOCIAL)

# The tab screenshots: a roomy window at twice the pixels, so they stay
# crisp on a high-density screen.
SHOT_VIEWPORT = {'width': 1600, 'height': 1000}
SHOT_SCALE = 2
SHOT_DOCK_H = 300            # the tray tall enough for the processor and its box
PNG_LIMIT = 1_500_000        # bytes

# The GIF: a smaller window, scaled down to GIF_WIDTH.
GIF_VIEWPORT = {'width': 1280, 'height': 800}
GIF_DOCK_H = 230
GIF_WIDTH = 960
GIF_FRAME_MS = 100           # 10 fps while something moves
GIF_LIMIT = 6_000_000

SOCIAL_SIZE = (1280, 640)
TAGLINE = 'Plan LED video walls, from pixel map to binder.'

# The app's own colors (src/static/css/style.css, theme.js's red accent).
BG = '#1a1a1a'
PANEL = '#252525'
BORDER = '#3a3a3a'
TEXT = '#e0e0e0'
MUTED = '#9a9a9a'


# ── a fresh server, the way the tests start one ──────────────────────────

class Server:
    """The app on a free port with scratch state. Use as a context manager:
    the server shuts down and the scratch folder goes when it ends."""

    def __enter__(self):
        self.scratch = tempfile.mkdtemp(prefix='lrd-readme-media-')
        sys.path.insert(0, SRC)
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        import app as app_module
        from app import app, socketio, _build_initial_project
        import routes_layouts
        import routes_distro_presets
        import routes_cable_stock
        import routes_panel_catalog
        from werkzeug.serving import make_server

        routes_layouts.LAYOUTS_FILE = os.path.join(self.scratch, 'layouts.json')
        routes_distro_presets.DISTRO_PRESETS_FILE = os.path.join(self.scratch, 'distro_presets.json')
        routes_cable_stock.CABLE_STOCK_PRESETS_FILE = os.path.join(self.scratch, 'cable_stock_presets.json')
        # Never reach GitHub for the panel catalog: a newer one would
        # "update" the page mid-capture. A port nothing listens on fails at
        # once, the way an offline launch does.
        routes_panel_catalog._PANEL_CATALOG_RAW_URL = 'http://127.0.0.1:9/panel_catalog.json'

        app_module.current_project = _build_initial_project()
        app_module.next_layer_id = 1
        app_module.server_preferences = {}
        app.config['TESTING'] = True
        if socketio.server.eio.async_mode != 'threading':
            raise SystemExit(f'expected the threading server, got {socketio.server.eio.async_mode}')
        # What socketio.run does in threading mode (app.run, threaded),
        # bound here so the port is ours before anything is served and the
        # server can be shut down at the end.
        self.httpd = make_server('127.0.0.1', 0, app, threaded=True)
        self.url = f'http://127.0.0.1:{self.httpd.server_port}'
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.opener.open(self.url + '/api/project', timeout=10) as r:
            if r.status != 200:
                raise SystemExit(f'the server answered HTTP {r.status}')
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.thread.join(timeout=10)
        shutil.rmtree(self.scratch, ignore_errors=True)

    def put_project(self, project):
        req = urllib.request.Request(
            self.url + '/api/project', data=json.dumps(project).encode('utf-8'),
            method='PUT', headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=10) as r:
            if r.status != 200:
                raise SystemExit(f'loading the demo show failed: HTTP {r.status}')


def demo_project():
    """The demo show: the Advanced Guide's last entry snapshot that still has
    one screen (the step after adds a second, not yet attached)."""
    with open(SNAPSHOTS, encoding='utf-8') as f:
        tour = json.load(f)['tours']['advanced']
    found = None
    for entry in tour['steps']:
        snap = tour['unique'][entry] if isinstance(entry, int) else entry
        if len(snap.get('layers') or []) == 1:
            found = snap
    if not found:
        raise SystemExit(f'{SNAPSHOTS}: no one-screen snapshot in the Advanced Guide')
    return copy.deepcopy(found)


def unplaced(project):
    """The same show with the processor's ports taken off the wall - where
    the GIF's drag starts."""
    project = copy.deepcopy(project)
    project.setdefault('port_assignments', {})['pins'] = []
    return project


# ── the page ─────────────────────────────────────────────────────────────

# No first-run guide (a new browser is stamped silently by What's New), and
# the tray at a height that shows a processor's ports.
INIT_JS = """(dockH) => {
    try {
        localStorage.setItem('lrd_quickstart_disabled', '1');
        localStorage.setItem('lrd_dock_h', String(dockH));
    } catch (e) {}
}"""

# Every frame is a still: no transition or animation is caught half-way
# (a tab's hover fade, a panel's fold), so two runs give the same frames.
STILL_CSS = '*, *::before, *::after { transition: none !important; animation: none !important; }'

# Frame every wall in the canvas: centered, the union spanning most of it.
# fitToView frames the raster, and on the demo's 5K raster the wall would be
# a patch in a corner. (quickstart.js frameLayers, with more of the canvas.)
FRAME_JS = """() => {
    const a = window.app, r = window.canvasRenderer;
    if (a.remeasureCanvas) a.remeasureCanvas();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    a.project.layers.forEach(l => {
        const b = r.getLayerBoundsInActiveView(l), ws = r._layerCanvasOffset(l);
        x0 = Math.min(x0, b.x + ws.wx); y0 = Math.min(y0, b.y + ws.wy);
        x1 = Math.max(x1, b.x + ws.wx + b.width); y1 = Math.max(y1, b.y + ws.wy + b.height);
    });
    const w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0);
    r.zoom = Math.min(r.canvas.width * 0.84 / w, r.canvas.height * 0.78 / h);
    r.panX = r.canvas.width / 2 - (x0 + w / 2) * r.zoom;
    r.panY = r.canvas.height / 2 - (y0 + h / 2) * r.zoom;
    const zl = document.getElementById('zoom-level');
    if (zl && typeof r._zoomToPercent === 'function') zl.value = r._zoomToPercent(r.zoom) + '%';
    r.render();
}"""

# Anything that could stand over the app: a guide, What's New, a modal, a
# menu, a focused field's caret.
CLEAR_JS = """() => {
    try { if (window.QuickStart && window.QuickStart.state().visible) window.QuickStart.end(); } catch (e) {}
    try { window.app.hideContextMenu(); } catch (e) {}
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
}"""

# What is visibly up over the app, so a capture never ships one.
OVERLAYS_JS = """() => {
    const shown = el => {
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0
            && r.width > 40 && r.height > 40;
    };
    return [...document.querySelectorAll(
        '.modal, [id$="-modal"], #qs-callout, [id*="whatsnew"], [class*="whatsnew"], [id*="splash"]')]
        .filter(shown).map(el => el.id || String(el.className));
}"""

FLAG_JS = """() => {
    const f = document.getElementById('hw-dock-flag');
    return f && !f.classList.contains('view-hidden') ? f.textContent : null;
}"""

# The client point of the middle of a wall's last cabinet (where a processor
# drop takes every unplaced port), as quickstart.js cabinetPointRaw finds it.
LAST_CABINET_JS = """() => {
    const a = window.app, r = window.canvasRenderer, l = a.project.layers[0];
    const p = l.panels[l.panels.length - 1];
    const o1 = r.getLayerRenderOffset(l), o2 = r._layerCanvasOffset(l);
    const wx = p.x + p.width / 2 + o1.dx + o2.wx, wy = p.y + p.height / 2 + o1.dy + o2.wy;
    const rect = r.canvas.getBoundingClientRect();
    return { x: rect.left + wx * r.zoom + r.panX, y: rect.top + wy * r.zoom + r.panY };
}"""


def open_app(browser, server, viewport, scale, dock_h):
    context = browser.new_context(viewport=viewport, device_scale_factor=scale)
    context.add_init_script(f'({INIT_JS})({int(dock_h)})')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(server.url, wait_until='domcontentloaded')
    page.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=60000)
    page.wait_for_function("() => !!(window.app.project && window.canvasRenderer)")
    page.wait_for_function("(n) => window.app.project.layers.length === n", arg=1)
    page.wait_for_timeout(1500)
    page.add_style_tag(content=STILL_CSS)
    page.evaluate(CLEAR_JS)
    return context, page, errors


def show_view(page, mode, click=True):
    """Switch to view `mode` and frame the wall in it."""
    if click:
        page.locator(f'.view-tab[data-mode="{mode}"]').click()
    page.wait_for_function(
        "(m) => document.querySelector('.view-tab.active')?.dataset.mode === m", arg=mode)
    # The tray folds in or out with the view; let it land before framing.
    page.wait_for_timeout(600)
    page.evaluate(FRAME_JS)
    page.wait_for_timeout(300)


def assert_clear(page, errors, where):
    up = page.evaluate(OVERLAYS_JS)
    if up:
        raise SystemExit(f'{where}: something is up over the app: {up}')
    if errors:
        raise SystemExit(f'{where}: the page threw: {errors[0]}')


def write_png(png_bytes, path, limit=PNG_LIMIT):
    """Write a PNG; when it is over `limit`, re-encode it as 256 colors."""
    from PIL import Image
    im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    im.save(path, optimize=True)
    if os.path.getsize(path) > limit:
        im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) \
          .save(path, optimize=True)
    return os.path.getsize(path)


# ── the tab screenshots ──────────────────────────────────────────────────

def capture_tabs(browser, server, names, log):
    server.put_project(demo_project())
    context, page, errors = open_app(browser, server, SHOT_VIEWPORT, SHOT_SCALE, SHOT_DOCK_H)
    try:
        for name, mode in TABS:
            if name not in names:
                continue
            show_view(page, mode)
            flag = page.evaluate(FLAG_JS)
            if flag is not None and 'not all attached' in flag:
                raise SystemExit(f'{name}: the demo show reads "{flag}"; it should be all attached')
            page.mouse.move(2, SHOT_VIEWPORT['height'] - 2)     # no hover on anything
            page.wait_for_timeout(200)
            assert_clear(page, errors, name)
            log(name, write_png(page.screenshot(), os.path.join(MEDIA, name)))
    finally:
        context.close()


def social_visual(browser, server):
    """The app's Data view, cropped to the canvas and the tray under it."""
    server.put_project(demo_project())
    context, page, errors = open_app(browser, server, SHOT_VIEWPORT, SHOT_SCALE, SHOT_DOCK_H)
    try:
        show_view(page, 'data-flow')
        page.mouse.move(2, SHOT_VIEWPORT['height'] - 2)
        page.wait_for_timeout(200)
        assert_clear(page, errors, SOCIAL)
        box = page.evaluate("""() => {
            const c = document.getElementById('canvas-container').getBoundingClientRect();
            const d = document.getElementById('hardware-dock').getBoundingClientRect();
            return { x: c.left, y: c.top, width: c.width, height: d.bottom - c.top };
        }""")
        return page.screenshot(clip=box)
    finally:
        context.close()


# ── the social preview ───────────────────────────────────────────────────

def social_html(icon_png, shot_png):
    icon = base64.b64encode(icon_png).decode('ascii')
    shot = base64.b64encode(shot_png).decode('ascii')
    w, h = SOCIAL_SIZE
    # Everything that matters sits inside the central 1200 x 560: 40 px in
    # from the sides, 40 px from the top and bottom.
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {w}px; height: {h}px; background: {BG}; overflow: hidden; }}
body {{ font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
        color: {TEXT}; display: flex; align-items: center; padding: 0 64px; gap: 48px; }}
.words {{ flex: 0 0 470px; }}
.words img {{ width: 112px; height: 112px; display: block; margin: 0 0 28px -8px; }}
h1 {{ font-size: 54px; line-height: 1.05; font-weight: 700; letter-spacing: -0.5px; color: #f2f2f2; }}
p {{ margin-top: 20px; font-size: 26px; line-height: 1.35; color: {MUTED}; text-wrap: balance; }}
.shot {{ flex: 1 1 auto; height: 480px; border: 1px solid {BORDER}; border-radius: 10px;
         overflow: hidden; background: {PANEL}; }}
.shot img {{ width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }}
</style></head><body>
<div class="words">
  <img src="data:image/png;base64,{icon}" alt="">
  <h1>LED Raster Designer</h1>
  <p>{TAGLINE}</p>
</div>
<div class="shot"><img src="data:image/png;base64,{shot}" alt=""></div>
</body></html>"""


def capture_social(browser, server, log):
    with open(ICON, 'rb') as f:
        icon_png = f.read()
    html = social_html(icon_png, social_visual(browser, server))
    context = browser.new_context(
        viewport={'width': SOCIAL_SIZE[0], 'height': SOCIAL_SIZE[1]}, device_scale_factor=1)
    try:
        page = context.new_page()
        page.set_content(html, wait_until='load')
        page.wait_for_timeout(200)
        png = page.screenshot()
    finally:
        context.close()
    from PIL import Image
    if Image.open(io.BytesIO(png)).size != SOCIAL_SIZE:
        raise SystemExit(f'{SOCIAL}: rendered at the wrong size')
    log(SOCIAL, write_png(png, os.path.join(MEDIA, SOCIAL)))


# ── the GIF ──────────────────────────────────────────────────────────────

def _ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


class Recorder:
    """Frames of the page with a drawn pointer (a headless screenshot has
    none), each held for its own time. The real mouse moves with the drawn
    one, so the page reacts (hover, drag) exactly as it would to a hand."""

    def __init__(self, page, start):
        self.page = page
        self.frames = []        # (PIL image, ms)
        self.pos = start
        self.pressed = False
        page.mouse.move(*start)

    def shot(self, ms):
        from PIL import Image, ImageDraw
        im = Image.open(io.BytesIO(self.page.screenshot())).convert('RGB')
        draw = ImageDraw.Draw(im)
        x, y = self.pos
        if self.pressed:
            draw.ellipse((x - 11, y - 11, x + 11, y + 11), outline=(255, 255, 255), width=2)
        arrow = [(0, 0), (0, 19), (5, 14), (8.5, 22), (11.5, 20.8), (8, 13), (14, 13)]
        draw.polygon([(x + ax, y + ay) for ax, ay in arrow], fill=(255, 255, 255), outline=(0, 0, 0))
        self.frames.append((im, ms))

    def hold(self, ms):
        self.shot(ms)

    def glide(self, to, ms, settle_ms=40):
        """Move the pointer to `to` over `ms`, a frame every GIF_FRAME_MS."""
        x0, y0 = self.pos
        n = max(1, round(ms / GIF_FRAME_MS))
        for i in range(1, n + 1):
            t = _ease(i / n)
            self.pos = (x0 + (to[0] - x0) * t, y0 + (to[1] - y0) * t)
            self.page.mouse.move(*self.pos)
            self.page.wait_for_timeout(settle_ms)
            self.shot(GIF_FRAME_MS)

    def press(self):
        self.page.mouse.down()
        self.pressed = True

    def release(self):
        self.page.mouse.up()
        self.pressed = False


def center(page, selector):
    box = page.locator(selector).bounding_box()
    if not box:
        raise SystemExit(f'nothing to aim at: {selector}')
    return (box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)


def capture_gif(browser, server, log):
    server.put_project(unplaced(demo_project()))
    context, page, errors = open_app(browser, server, GIF_VIEWPORT, 1, GIF_DOCK_H)
    try:
        show_view(page, 'pixel-map', click=False)
        assert_clear(page, errors, GIF)
        canvas = center(page, '#canvas-container')
        rec = Recorder(page, (canvas[0] + 120, canvas[1] + 160))
        rec.hold(1600)

        def to_tab(mode, hold_ms):
            rec.glide(center(page, f'.view-tab[data-mode="{mode}"]'), 500)
            rec.press()
            rec.release()
            show_view(page, mode, click=False)
            rec.hold(hold_ms)

        to_tab('cabinet-id', 1300)
        to_tab('show-look', 1300)
        to_tab('data-flow', 900)
        flag = page.evaluate(FLAG_JS) or ''
        if 'not all attached' not in flag:
            raise SystemExit(f'{GIF}: the wall should start with no ports, the flag reads "{flag}"')

        # The processor onto the wall's last cabinet: every port lands.
        pid = page.evaluate("() => window.app.project.processors[0].id")
        # Its header row, in the open space right of its buttons.
        rec.glide(center(page, f'[data-hwdock="processor-{pid}"]'), 700)
        rec.press()
        rec.shot(GIF_FRAME_MS)
        drop = page.evaluate(LAST_CABINET_JS)
        rec.glide((drop['x'], drop['y']), 1300, settle_ms=60)
        page.wait_for_timeout(200)
        rec.hold(700)
        rec.release()
        page.wait_for_function(
            "() => ((window.app.project.port_assignments || {}).pins || []).length > 0", timeout=10000)
        page.wait_for_timeout(900)
        flag = page.evaluate(FLAG_JS) or ''
        if 'not all attached' in flag:
            raise SystemExit(f'{GIF}: the drop did not attach the wall, the flag reads "{flag}"')
        rec.hold(1800)

        to_tab('power', 2000)
        assert_clear(page, errors, GIF)
        frames = rec.frames
    finally:
        context.close()
    log(GIF, write_gif(frames, os.path.join(MEDIA, GIF)))


def write_gif(frames, path):
    """Scale the frames to GIF_WIDTH, map them all onto ONE palette (so a
    still area never shimmers between frames) and write a looping GIF."""
    from PIL import Image
    w0, h0 = frames[0][0].size
    size = (GIF_WIDTH, round(h0 * GIF_WIDTH / w0))
    small = [(im.resize(size, Image.LANCZOS), ms) for im, ms in frames]
    # The palette from a strip of the frames that are held longest - every
    # view the GIF shows - so each view's colors are in it.
    keys = sorted(small, key=lambda f: -f[1])[:8]
    strip = Image.new('RGB', (size[0], size[1] * len(keys)))
    for i, (im, _) in enumerate(keys):
        strip.paste(im, (0, size[1] * i))
    palette = strip.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im, _ in small]
    out[0].save(path, save_all=True, append_images=out[1:],
                duration=[ms for _, ms in small], loop=0, optimize=True, disposal=1)
    return os.path.getsize(path)


# ── main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--only', choices=OUTPUTS, help='regenerate just this file')
    args = ap.parse_args()
    names = {args.only} if args.only else set(OUTPUTS)
    os.makedirs(MEDIA, exist_ok=True)
    limits = {GIF: GIF_LIMIT, SOCIAL: PNG_LIMIT}
    written = []

    def log(name, size):
        written.append(name)
        over = ' - OVER THE LIMIT' if size > limits.get(name, PNG_LIMIT) else ''
        print(f'wrote .github/media/{name} ({size:,} bytes){over}')

    from playwright.sync_api import sync_playwright
    with Server() as server, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            if names & {name for name, _ in TABS}:
                capture_tabs(browser, server, names, log)
            if GIF in names:
                capture_gif(browser, server, log)
            if SOCIAL in names:
                capture_social(browser, server, log)
        finally:
            browser.close()
    over = [n for n in written
            if os.path.getsize(os.path.join(MEDIA, n)) > limits.get(n, PNG_LIMIT)]
    if over:
        raise SystemExit(f'over the size limit: {", ".join(over)}')


if __name__ == '__main__':
    main()
