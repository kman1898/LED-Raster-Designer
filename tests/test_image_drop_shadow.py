"""Photoshop-style Drop Shadow on IMAGE / LOGO layers, asserted on real pixels.

The shadow is baked into the canvas render (an offscreen silhouette, dilated
for Spread and blurred for Size, composited at the Angle/Distance offset), NOT
handed to ctx.shadowBlur - which has no spread and whose offset and blur ignore
the current transform. So every assertion here reads pixels back out of the
canvas with getImageData; a state flag would pass with the whole render ripped
out.

Pinned behaviours:

* Shadow OFF renders exactly what the app rendered before this feature existed
  (the regression guard for every project already out there).
* Photoshop's angle convention: 120 deg is light from the upper left, so the
  shadow falls DOWN-RIGHT and there is nothing up-left of the image.
* Distance moves the shadow; Size softens its edge.
* Spread 100 gives a hard edge, Spread 0 a smooth falloff - asserted on the
  alpha profile across the edge, not just on "something is there".
* The shadow is measured in WORLD units, so its extent is the same at 1x and
  at 2x zoom (the ctx.shadow* properties would have failed this).
* It survives a page reload AND an undo/redo round trip - the layer fields
  have to be listed in the PUT allow-list, the add route, preservedKeys and
  the duplicate/paste blocks or they are silently dropped.
* It is in the EXPORT render, not just the on-screen one: performExport() is
  driven for real and the resulting PNG's pixels are decoded and sampled.
  (PDF is assembled server-side from these same PNGs.)

Run locally:
    python3 -m pytest tests/test_image_drop_shadow.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """One long-lived page; every test rebuilds its own project first."""
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# ── the fixture project ───────────────────────────────────────────────────

# One solid-red 100x100 image at world (200, 200). Red so a WHITE shadow can
# never be confused with the image itself in the blue channel, and square so
# every edge distance is trivially checkable.
IMG_X, IMG_Y, IMG_W, IMG_H = 200, 200, 100, 100

RESET_JS = """async () => {
    const app = window.app;
    const r = window.canvasRenderer;
    // The live server is shared with every other browser test file; clear
    // whatever they left behind and build our own image layer through the
    // real add endpoint.
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    // Let the server's project_data echo of that wipe land BEFORE the layer
    // is added - arriving afterwards it replaces app.project with the empty
    // one and the layer we are about to build disappears mid-test.
    await new Promise(res => setTimeout(res, 500));
    const src = document.createElement('canvas');
    src.width = 100; src.height = 100;
    const sctx = src.getContext('2d');
    sctx.fillStyle = '#ff0000';
    sctx.fillRect(0, 0, 100, 100);
    await fetch('/api/layer/add-image', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'ShadowImage',
            imageData: src.toDataURL('image/png'),
            imageWidth: 100, imageHeight: 100,
            offset_x: 200, offset_y: 200,
        }),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('image_drop_shadow_test_reset');
    const img = app.project.layers.find(l => (l.type || 'screen') === 'image');
    app.currentLayer = img;
    app.selectedLayerIds = new Set([img.id]);
    app.lastSelectedLayerId = img.id;
    // Deterministic camera so world -> device pixel math is exact, and no
    // grid: its 50px lines would land on the sample points.
    r.viewMode = 'pixel-map';
    r.zoom = 1; r.panX = 0; r.panY = 0;
    r.showGrid = false;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    r.render();
    return img.id;
}"""

# renderImageLayer bails out until the Image object has decoded, so every
# draw has to wait for it before pixels mean anything.
DRAW_JS = """async (props) => {
    const app = window.app;
    const r = window.canvasRenderer;
    let l = app.project.layers.find(x => (x.type || 'screen') === 'image');
    if (!l) {
        // A late project_data echo can swap app.project for the state the
        // reset PUT left behind. Re-read rather than fail the frame.
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('image_drop_shadow_test_redraw');
        l = app.project.layers.find(x => (x.type || 'screen') === 'image');
    }
    if (!l) return false;
    if (props) Object.assign(l, props);
    r.render();
    const img = l._imageObj;
    if (img && !img.complete) {
        await new Promise(res => {
            img.addEventListener('load', res, { once: true });
            setTimeout(res, 2000);
        });
    }
    await new Promise(res => requestAnimationFrame(res));
    r.render();
    return true;
}"""

SAMPLE_JS = """(pts) => {
    const r = window.canvasRenderer;
    return pts.map(([wx, wy]) => {
        const dx = Math.round(wx * r.zoom + r.panX);
        const dy = Math.round(wy * r.zoom + r.panY);
        const d = r.ctx.getImageData(dx, dy, 1, 1).data;
        return [d[0], d[1], d[2], d[3]];
    });
}"""

# Far from the image and from every canvas outline: the reference "nothing
# drawn here" colour, read rather than hard-coded so the active-canvas tint
# can change without breaking every assertion.
BG_POINT = [700, 700]


def reset_project(page):
    layer_id = page.evaluate(RESET_JS)
    page.wait_for_timeout(400)
    assert layer_id, layer_id
    return layer_id


def draw(page, props=None):
    assert page.evaluate(DRAW_JS, props) is True
    page.wait_for_timeout(120)


def sample(page, points):
    return page.evaluate(SAMPLE_JS, points)


def blue(page, points):
    return [p[2] for p in sample(page, points)]


def background(page):
    return sample(page, [BG_POINT])[0]


SHADOW_OFF = {
    'imageShadowEnabled': False,
}

# Photoshop's own defaults, i.e. what ticking the checkbox gives you.
SHADOW_DEFAULTS = {
    'imageShadowEnabled': True,
    'imageShadowColor': '#000000',
    'imageShadowOpacity': 75,
    'imageShadowAngle': 120,
    'imageShadowDistance': 10,
    'imageShadowSpread': 0,
    'imageShadowSize': 10,
}


def white_shadow(**overrides):
    """A white, fully opaque shadow: maximum contrast against the dark
    background, and invisible against the red image, so a sampled blue value
    IS the shadow's alpha profile."""
    p = {
        'imageShadowEnabled': True,
        'imageShadowColor': '#ffffff',
        'imageShadowOpacity': 100,
        'imageShadowAngle': 120,
        'imageShadowDistance': 0,
        'imageShadowSpread': 0,
        'imageShadowSize': 40,
    }
    p.update(overrides)
    return p


# ── off means off ─────────────────────────────────────────────────────────

def test_shadow_off_leaves_every_pixel_unchanged(page):
    reset_project(page)
    probes = [
        [IMG_X + 50, IMG_Y + 50],          # inside the image
        [IMG_X + 110, IMG_Y + 110],        # down-right of it
        [IMG_X - 20, IMG_Y - 20],          # up-left of it
        [IMG_X + 50, IMG_Y + 130],         # below it
        BG_POINT,
    ]
    draw(page, SHADOW_OFF)
    before = sample(page, probes)
    # Turning it on and back off must land on exactly the same frame - this
    # is the guard for every project made before the feature existed.
    draw(page, SHADOW_DEFAULTS)
    draw(page, SHADOW_OFF)
    after = sample(page, probes)
    assert before == after, (before, after)
    bg = before[4]
    assert before[1] == bg, before      # nothing outside the image is painted
    assert before[2] == bg, before
    assert before[3] == bg, before


# ── the angle convention ──────────────────────────────────────────────────

def test_default_angle_throws_the_shadow_down_right(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    draw(page, SHADOW_DEFAULTS)
    # Defaults: distance 10 at 120 deg -> offset (+5, +8.66) px, size 10 blur.
    down_right = sample(page, [
        [IMG_X + IMG_W + 2, IMG_Y + 50],   # just right of the image
        [IMG_X + 50, IMG_Y + IMG_H + 4],   # just below it
        [IMG_X + IMG_W + 2, IMG_Y + IMG_H + 2],
    ])
    up_left = sample(page, [
        [IMG_X - 12, IMG_Y + 50],          # left of the image
        [IMG_X + 50, IMG_Y - 12],          # above it
        [IMG_X - 12, IMG_Y - 12],
    ])
    for got in down_right:
        # Black at 75% over the dark background: a real, visible darkening.
        assert got[0] < bg[0] - 3, (got, bg)
    for got in up_left:
        assert got == bg, (got, bg)


def test_distance_moves_the_shadow(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    # Hard silhouette (size 0) so the shadow's position is exact: at 120 deg
    # a distance of 80 offsets it by (+40, +69.3), which is the only way this
    # point - down AND right of the image - gets covered.
    far = [IMG_X + IMG_W + 30, IMG_Y + 80]
    draw(page, white_shadow(imageShadowDistance=0, imageShadowSize=0))
    near_only = blue(page, [far])[0]
    draw(page, white_shadow(imageShadowDistance=80, imageShadowSize=0))
    moved = blue(page, [far])[0]
    assert near_only == bg[2], (near_only, bg)
    assert moved > bg[2] + 100, (moved, bg)


def test_size_softens_the_edge(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    just_outside = [IMG_X + IMG_W + 12, IMG_Y + 50]
    draw(page, white_shadow(imageShadowSize=0))
    hard = blue(page, [just_outside])[0]
    draw(page, white_shadow(imageShadowSize=40))
    soft = blue(page, [just_outside])[0]
    # Size 0 reaches nowhere past the silhouette; size 40 reaches well past it
    # but only partway to full opacity at 12px out.
    assert hard == bg[2], (hard, bg)
    assert soft > bg[2] + 40, (soft, bg)
    assert soft < 245, soft


# ── Spread: the control this whole render pass exists for ─────────────────

def test_spread_100_is_a_hard_edge_and_spread_0_is_a_gradient(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    # Along the image's mid-line, 5 / 20 / 35 px past its right edge, plus one
    # point past the shadow's reach (size 40) in either configuration.
    probes = [
        [IMG_X + IMG_W + 5, IMG_Y + 50],
        [IMG_X + IMG_W + 20, IMG_Y + 50],
        [IMG_X + IMG_W + 35, IMG_Y + 50],
        [IMG_X + IMG_W + 50, IMG_Y + 50],
    ]

    draw(page, white_shadow(imageShadowSpread=100))
    hard = blue(page, probes)
    # Spread 100 = all 40px solid, no falloff at all: the three in-shadow
    # samples are the same value, and it is full opacity.
    assert hard[0] > 245, hard
    assert abs(hard[0] - hard[2]) <= 4, hard
    assert abs(hard[1] - hard[2]) <= 4, hard
    assert hard[3] <= bg[2] + 6, (hard, bg)

    draw(page, white_shadow(imageShadowSpread=0))
    soft = blue(page, probes)
    # Spread 0 = the whole 40px is falloff: strictly decreasing, and never
    # the flat plateau spread 100 produces.
    assert soft[0] < 245, soft
    assert soft[0] > soft[1] + 15, soft
    assert soft[1] > soft[2] + 10, soft
    assert soft[2] > bg[2], (soft, bg)
    assert soft[3] <= bg[2] + 6, (soft, bg)
    # And the two are genuinely different renders at the same Size.
    assert hard[1] > soft[1] + 60, (hard, soft)


# ── world units, not device units ─────────────────────────────────────────

EXTENT_JS = """(args) => {
    const [zoom, y, from, to, threshold] = args;
    const r = window.canvasRenderer;
    r.zoom = zoom; r.panX = 0; r.panY = 0;
    r.render();
    let last = null;
    for (let wx = from; wx <= to; wx += 0.5) {
        const dx = Math.round(wx * r.zoom + r.panX);
        const dy = Math.round(y * r.zoom + r.panY);
        const d = r.ctx.getImageData(dx, dy, 1, 1).data;
        if (d[2] > threshold) last = wx;
    }
    return last;
}"""


def test_shadow_extent_is_the_same_in_world_units_at_two_zooms(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    # Hard-edged shadow, no offset: its right edge sits exactly 40 world units
    # past the image's, and nothing about that may depend on zoom.
    draw(page, white_shadow(imageShadowSpread=100))
    threshold = bg[2] + 60
    at_1x = page.evaluate(EXTENT_JS, [1, IMG_Y + 50, IMG_X + IMG_W, IMG_X + IMG_W + 70, threshold])
    at_2x = page.evaluate(EXTENT_JS, [2, IMG_Y + 50, IMG_X + IMG_W, IMG_X + IMG_W + 70, threshold])
    page.evaluate("() => { const r = window.canvasRenderer; r.zoom = 1; r.render(); }")
    assert at_1x is not None and at_2x is not None, (at_1x, at_2x)
    assert abs(at_1x - (IMG_X + IMG_W + 40)) <= 3, at_1x
    assert abs(at_2x - at_1x) <= 3, (at_1x, at_2x)


# ── persistence ───────────────────────────────────────────────────────────

def test_shadow_survives_a_reload(page):
    reset_project(page)
    draw(page, white_shadow(imageShadowSpread=100))
    # Push it the way the sidebar does, then reload the page for real.
    page.evaluate("""async () => {
        const app = window.app;
        const l = app.project.layers.find(x => (x.type || 'screen') === 'image');
        await app.updateLayers([l]);
    }""")
    page.wait_for_timeout(600)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    stored = page.evaluate("""() => {
        const l = window.app.project.layers.find(x => (x.type || 'screen') === 'image');
        return l ? {
            enabled: l.imageShadowEnabled, color: l.imageShadowColor,
            opacity: l.imageShadowOpacity, angle: l.imageShadowAngle,
            distance: l.imageShadowDistance, spread: l.imageShadowSpread,
            size: l.imageShadowSize,
        } : null;
    }""")
    assert stored == {
        'enabled': True, 'color': '#ffffff', 'opacity': 100, 'angle': 120,
        'distance': 0, 'spread': 100, 'size': 40,
    }, stored
    # And it is still on the canvas, not merely in the object.
    page.evaluate("""() => {
        const r = window.canvasRenderer;
        r.viewMode = 'pixel-map';
        r.zoom = 1; r.panX = 0; r.panY = 0; r.showGrid = false;
    }""")
    draw(page, None)
    bg = background(page)
    got = blue(page, [[IMG_X + IMG_W + 20, IMG_Y + 50]])[0]
    assert got > bg[2] + 150, (got, bg)


def test_shadow_survives_undo_and_redo(page):
    reset_project(page)
    draw(page, SHADOW_OFF)
    bg = background(page)
    probe = [IMG_X + IMG_W + 20, IMG_Y + 50]
    page.evaluate("() => window.app.saveState('shadow test base')")
    page.wait_for_timeout(200)
    draw(page, white_shadow(imageShadowSpread=100))
    page.evaluate("""async () => {
        const app = window.app;
        const l = app.project.layers.find(x => (x.type || 'screen') === 'image');
        await app.updateLayers([l]);
        app.saveState('Drop Shadow');
    }""")
    page.wait_for_timeout(500)
    on = blue(page, [probe])[0]
    assert on > bg[2] + 150, (on, bg)

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    draw(page, None)
    undone = blue(page, [probe])[0]
    assert undone == bg[2], (undone, bg)

    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(700)
    draw(page, None)
    redone = blue(page, [probe])[0]
    assert redone > bg[2] + 150, (redone, bg)


# ── the sidebar controls ──────────────────────────────────────────────────

def set_number(page, selector, value):
    page.fill(selector, value)
    page.dispatch_event(selector, 'change')
    page.wait_for_timeout(120)


def test_sidebar_controls_reach_the_canvas_and_the_server(page):
    reset_project(page)
    page.evaluate("""() => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'image'));
    }""")
    page.wait_for_timeout(300)
    draw(page, None)
    bg = background(page)
    probe = [IMG_X + IMG_W + 20, IMG_Y + 50]

    page.check('#image-shadow-enabled')
    page.wait_for_timeout(300)
    # Ticking the box alone must already draw Photoshop's defaults.
    draw(page, None)
    defaulted = sample(page, [[IMG_X + IMG_W + 2, IMG_Y + 50]])[0]
    assert defaulted[0] < bg[0] - 3, (defaulted, bg)

    set_number(page, '#image-shadow-size', '40')
    set_number(page, '#image-shadow-spread', '100')
    set_number(page, '#image-shadow-distance', '0')
    set_number(page, '#image-shadow-opacity', '100')
    page.fill('#image-shadow-color-hex', '#FFFFFF')
    page.dispatch_event('#image-shadow-color-hex', 'change')
    page.wait_for_timeout(400)
    draw(page, None)
    assert blue(page, [probe])[0] > bg[2] + 150

    page.wait_for_timeout(600)
    stored = page.evaluate("""async () => {
        const project = await (await fetch('/api/project')).json();
        const l = project.layers.find(x => (x.type || 'screen') === 'image');
        return l ? {
            enabled: l.imageShadowEnabled, color: l.imageShadowColor,
            opacity: l.imageShadowOpacity, spread: l.imageShadowSpread,
            size: l.imageShadowSize, distance: l.imageShadowDistance,
            angle: l.imageShadowAngle,
        } : null;
    }""")
    # The hex field keeps whatever case the user typed; the renderer accepts
    # either, so only the value matters.
    stored['color'] = str(stored['color']).lower()
    assert stored == {
        'enabled': True, 'color': '#ffffff', 'opacity': 100, 'spread': 100,
        'size': 40, 'distance': 0, 'angle': 120,
    }, stored

    # Unticking the box takes it back off the canvas.
    page.uncheck('#image-shadow-enabled')
    page.wait_for_timeout(300)
    draw(page, None)
    assert blue(page, [probe])[0] == bg[2]


# ── the export render path ────────────────────────────────────────────────

EXPORT_JS = """async (probes) => {
    const app = window.app;
    // performExport() renders every selected canvas x view through the SAME
    // renderer and hands the writer finished PNG data URLs; stub the writer
    // so nothing is downloaded and we can read the pixels it would have
    // saved. The PDF writer is fed these very images server-side.
    const captured = [];
    const realWriter = app.downloadRenderedPNGs;
    app.downloadRenderedPNGs = async (items) => { captured.push(...items); };
    const canvases = (app.project && app.project.canvases) || [];
    const canvasIds = canvases.length
        ? [app.project.active_canvas_id || canvases[0].id]
        : [null];
    try {
        await app.performExport('ShadowExport', 'png', ['pixel-map'], canvasIds);
    } finally {
        app.downloadRenderedPNGs = realWriter;
    }
    if (captured.length === 0) return { error: 'no images rendered' };
    const item = captured[0];
    const target = canvases.find(c => c && c.id === item.canvasId);
    const wsx = target ? (target.workspace_x || 0) : 0;
    const wsy = target ? (target.workspace_y || 0) : 0;
    const px = await new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => {
            const c = document.createElement('canvas');
            c.width = im.width; c.height = im.height;
            const cx = c.getContext('2d');
            cx.drawImage(im, 0, 0);
            resolve(probes.map(([wx, wy]) => {
                const d = cx.getImageData(Math.round(wx - wsx), Math.round(wy - wsy), 1, 1).data;
                return [d[0], d[1], d[2], d[3]];
            }));
        };
        im.onerror = () => reject(new Error('export png did not decode'));
        im.src = item.dataUrl;
    });
    return { width: item.width, height: item.height, pixels: px };
}"""


def test_shadow_is_baked_into_the_exported_png(page):
    reset_project(page)
    draw(page, white_shadow(imageShadowSpread=100))
    probes = [
        [IMG_X + 50, IMG_Y + 50],           # the image itself
        [IMG_X + IMG_W + 20, IMG_Y + 50],   # inside the shadow
        [IMG_X + IMG_W + 60, IMG_Y + 50],   # past its 40px reach
    ]
    out = page.evaluate(EXPORT_JS, probes)
    assert 'error' not in out, out
    image_px, shadow_px, clear_px = out['pixels']
    assert image_px[0] > 200 and image_px[2] < 60, image_px
    assert shadow_px[2] > 200, shadow_px       # white shadow in the PNG
    assert clear_px[2] < 40, clear_px          # export background


# ── The raster is built once, not once a frame ───────────────────────────

# Spread runs a getImageData plus two sweeps over every pixel of a scratch
# that grows with zoom up to a 4096 cap. Rebuilding that on every frame turned
# a pan into single-digit fps, so the finished raster is cached on the image
# object and only the cheap composite runs per frame. Distance, Angle and
# Opacity are applied at composite time precisely so that dragging any of them
# reuses the cache.
#
# _dilateAlpha is the expensive step and runs once per build, which makes it
# the honest counter for "did this rebuild?".
INSTRUMENT_JS = """() => {
    const r = window.canvasRenderer;
    if (!r.__dilateOrig) r.__dilateOrig = r._dilateAlpha;
    window.__dilateCalls = 0;
    r._dilateAlpha = function (...a) {
        window.__dilateCalls++;
        return r.__dilateOrig.apply(this, a);
    };
}"""

UNINSTRUMENT_JS = """() => {
    const r = window.canvasRenderer;
    if (r.__dilateOrig) { delete r._dilateAlpha; delete r.__dilateOrig; }
}"""


def rebuilds_during(page, js):
    """Count shadow rebuilds while `js` runs."""
    page.evaluate(INSTRUMENT_JS)
    try:
        page.evaluate(js)
        page.wait_for_timeout(120)
        return page.evaluate("() => window.__dilateCalls")
    finally:
        page.evaluate(UNINSTRUMENT_JS)


SPREAD_SHADOW = dict(imageShadowSpread=50, imageShadowSize=20)


def test_the_instrumentation_can_see_a_rebuild(page):
    """Guard the premise: if the counter never fires, every assertion below
    passes by counting nothing."""
    reset_project(page)
    draw(page, white_shadow(**SPREAD_SHADOW))
    n = rebuilds_during(page, """() => {
        const r = window.canvasRenderer;
        const l = window.app.project.layers.find(x => (x.type || 'screen') === 'image');
        if (l._imageObj) delete l._imageObj._lrdShadowRaster;   // force a build
        r.render();
    }""")
    assert n == 1, f"expected exactly one rebuild, counted {n}"


def test_a_repeated_frame_reuses_the_raster(page):
    """A pan re-renders the whole canvas without changing the scale or any
    shadow setting - the raster must survive it."""
    reset_project(page)
    draw(page, white_shadow(**SPREAD_SHADOW))
    n = rebuilds_during(page, """() => {
        const r = window.canvasRenderer;
        for (let i = 0; i < 5; i++) { r.panX += 3; r.render(); }
    }""")
    assert n == 0, (
        f"{n} rebuilds across 5 pan frames - the shadow raster is being "
        "rebuilt per frame, which is what made panning stutter")


def test_dragging_distance_angle_or_opacity_reuses_the_raster(page):
    """None of the three change the raster, only where and how strongly it is
    composited - so dragging the sliders must not rebuild anything."""
    reset_project(page)
    draw(page, white_shadow(**SPREAD_SHADOW))
    n = rebuilds_during(page, """() => {
        const r = window.canvasRenderer;
        const l = window.app.project.layers.find(x => (x.type || 'screen') === 'image');
        for (let i = 0; i < 6; i++) {
            l.imageShadowDistance = 10 + i;
            l.imageShadowAngle = 100 + i;
            l.imageShadowOpacity = 60 + i;
            r.render();
        }
    }""")
    assert n == 0, f"{n} rebuilds while dragging composite-only settings"


@pytest.mark.parametrize('change', [
    "l.imageShadowSize = 40;",
    "l.imageShadowSpread = 80;",
    "l.imageShadowColor = '#00ff00';",
    "r.zoom = 2;",
])
def test_a_change_that_alters_the_raster_does_rebuild_it(page, change):
    """The other half of the contract. A cache that never invalidates would
    pass every test above and show a stale shadow."""
    reset_project(page)
    draw(page, white_shadow(**SPREAD_SHADOW))
    n = rebuilds_during(page, """() => {
        const r = window.canvasRenderer;
        const l = window.app.project.layers.find(x => (x.type || 'screen') === 'image');
        %s
        r.render();
    }""" % change)
    assert n == 1, f"{change!r} produced {n} rebuilds, expected 1"


def test_the_reused_raster_draws_the_same_pixels(page):
    """The cache must be invisible: a cached frame has to match the frame that
    built it, or panning would quietly change what the shadow looks like."""
    reset_project(page)
    draw(page, white_shadow(**SPREAD_SHADOW))
    probes = [
        [IMG_X + IMG_W + 5, IMG_Y + 50],
        [IMG_X + IMG_W + 15, IMG_Y + 50],
        [IMG_X + IMG_W + 25, IMG_Y + 50],
        [IMG_X + 50, IMG_Y + IMG_H + 15],
    ]
    first = sample(page, probes)
    page.evaluate("() => window.canvasRenderer.render()")   # cached path
    page.wait_for_timeout(80)
    again = sample(page, probes)
    assert again == first, f"cached frame differs: {first} -> {again}"
