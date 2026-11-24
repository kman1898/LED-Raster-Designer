"""Export > 3D PNG (app-stage3d-png.js), in the real app.

The owner's ruling (2026-11-24): a 3D PNG export with a view pick. The
current camera or a preset view, a size, saved straight to a file.

What this file pins:

* Export pressed on the 3D tab and File > Export 3D PNG open the Export
  dialog on 3D PNG (Export on another tab keeps the dialog's last format), with its own View, Size and Background and none of the
  picture formats' sections; the preview names the file; Export saves one
  PNG of exactly the size picked, through the host's save dialog, and logs
  what it drew (render_3d_png) and where it went (export_3d_png).
* A preset view frames every screen as the tab's view button does: the
  picture's camera is where the button takes the tab's.
* The tab's camera is never moved, and nothing is saved for it.
* No selection, handles or corner spot in the picture: a picture taken with
  both screens selected, the handles up and a corner spot picked is pixel
  for pixel the one taken with nothing selected, and the tab's marks are
  all back afterwards.
* A size the graphics card cannot draw is refused in plain words, with the
  dialog still open and nothing saved.
* The background: the 3D view's, or transparent.
* With the 3D tab never opened, the picture is still drawn, and the tab
  opens normally afterwards.

Run locally:
    python -m pytest tests/test_stage3d_png.py -v -p no:cacheprovider
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402
from test_stage3d import TWO, _context, dbg, open_3d, open_tab, reset, view_from  # noqa: E402

# The client log, read off the page (test_render_log.py's capture).
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _new_page(e2e_server, pw_browser):
    context = _context(pw_browser, CLIENT_LOG)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    # A real save dialog must never open on the test machine.
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(e2e_server, pw_browser)
    yield pg
    context.close()


def logged(pg, action):
    return [e['details'] for e in pg.evaluate("() => window.__clog") if e['action'] == action]


# The picture's pixels, kept on the page under `key`; returns what the
# render said, without the blob.
RENDER_JS = """async ([opts, key]) => {
    const out = await window.app.stage3dPngRender(opts);
    const bmp = await createImageBitmap(out.blob);
    const c = document.createElement('canvas');
    c.width = bmp.width; c.height = bmp.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(bmp, 0, 0);
    window.__png = window.__png || {};
    window.__png[key] = ctx.getImageData(0, 0, c.width, c.height).data;
    const rest = Object.assign({}, out);
    delete rest.blob;
    rest.bytes = out.blob.size;
    rest.bitmap = [bmp.width, bmp.height];
    return rest;
}"""


def render(page, key='a', **opts):
    return page.evaluate(RENDER_JS, [opts, key])


def differing(page, a, b):
    return page.evaluate("""([a, b]) => {
        const x = window.__png[a], y = window.__png[b];
        if (x.length !== y.length) return -1;
        let n = 0;
        for (let i = 0; i < x.length; i += 4) {
            if (x[i] !== y[i] || x[i + 1] !== y[i + 1] || x[i + 2] !== y[i + 2] || x[i + 3] !== y[i + 3]) n += 1;
        }
        return n;
    }""", [a, b])


def camera_now(page):
    return page.evaluate("() => window.app._s3dCameraState()")


def close_enough(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def png_size(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        return im.size, im.mode


def test_the_dialog_saves_a_png_of_the_size_picked(page):
    reset(page)
    open_3d(page, 2)
    written = []

    def dialog(route):
        url = route.request.url
        if url.endswith('/available'):
            route.fulfill(status=200, body='{"ok": true}', content_type='application/json')
        elif url.endswith('/save-file'):
            route.fulfill(status=200, body='{"ok": true, "path": "C:/shows/out/Tour_3D_Front.png"}',
                          content_type='application/json')
        elif url.endswith('/write-file'):
            written.append(route.request.post_data_buffer or b'')
            route.fulfill(status=200, body='{"ok": true}', content_type='application/json')
        else:
            route.fulfill(status=503, body='{}')

    page.unroute('**/api/native-dialog/**')
    page.route('**/api/native-dialog/**', dialog)
    try:
        page.evaluate("() => { window.app._hostCapabilityProbe = null; window.app._isHostClient = undefined; }")
        # Export on the 3D tab opens the dialog on 3D PNG
        tip = page.get_attribute('#btn-export', 'data-tooltip')
        assert tip.startswith('Export, ') and 'On the 3D tab it opens on 3D PNG' in tip
        assert '\u2014' not in tip and '\u2013' not in tip
        page.evaluate("() => { document.getElementById('export-format').value = 'pdf'; }")
        page.click('#btn-export')
        page.wait_for_timeout(300)
        assert page.input_value('#export-format') == 'png-3d'
        assert page.is_visible('#export-3d-png-section')
        for hidden in ('#export-views-section', '#export-canvases-section', '#export-options-section',
                       '#export-obj-note', '#export-binder-section', '#export-pull-sheet-section'):
            assert not page.is_visible(hidden), hidden
        views = page.evaluate("[...document.querySelectorAll('#export-3d-png-view option')].map(o => o.textContent)")
        assert views == ['Current view', 'Front', 'Back', 'Left', 'Right', 'Top', 'Iso'], views
        size_label = page.evaluate("document.querySelector('#export-3d-png-size option[value=view]').textContent")
        canvas = page.evaluate("[document.getElementById('s3d-canvas').width, document.getElementById('s3d-canvas').height]")
        assert size_label == f'Same as the 3D view ({canvas[0]} x {canvas[1]})', size_label
        page.fill('#export-name', 'Tour')
        page.dispatch_event('#export-name', 'input')
        page.select_option('#export-3d-png-view', 'front')
        page.select_option('#export-3d-png-size', '1920x1080')
        assert page.inner_text('#export-preview') == 'Tour_3D_Front.png (1920 x 1080)'
        page.click('#export-confirm')
        settled(page, lambda: len(written), lambda n: n >= 1, 20000)
        body = written[0]
        start = body.index(b'\x89PNG\r\n\x1a\n')
        end = body.index(b'IEND', start) + 8
        size, mode = png_size(body[start:end])
        assert size == (1920, 1080), size
        assert mode in ('RGB', 'RGBA'), mode
        assert b'C:/shows/out/Tour_3D_Front.png' in body
        assert not page.is_visible('#export-modal')
        drew = settled(page, lambda: logged(page, 'render_3d_png'), lambda x: len(x) >= 1)[-1]
        assert drew['view'] == 'front' and drew['size'] == [1920, 1080] and drew['source'] == '3D tab', drew
        assert drew['screens']['n'] == 2 and drew['screens']['inFrame'] == 2, drew
        assert drew['mode'] == 'perspective' and drew['background'] == 'view', drew
        assert drew['_msg'].startswith('3D PNG drew 2 screens (2 in frame), Front, perspective, 1920x1080'), drew
        assert 'data:image' not in str(drew)
        saved = settled(page, lambda: logged(page, 'export_3d_png'), lambda x: len(x) >= 1)[-1]
        assert saved['file'] == 'Tour_3D_Front.png' and saved['saved'] is True, saved
        assert saved['path'] == 'C:/shows/out/Tour_3D_Front.png' and saved['bytes'] > 1000, saved
    finally:
        page.unroute('**/api/native-dialog/**')
        page.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    # File > Export 3D PNG opens the same dialog
    page.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; window.app.handleMenuAction('export-3d-png'); }")
    page.wait_for_timeout(200)
    assert page.input_value('#export-format') == 'png-3d' and page.is_visible('#export-3d-png-section')
    page.click('#export-cancel')
    # Export on another tab keeps the dialog's last format
    page.evaluate("() => { document.getElementById('export-format').value = 'pdf'; }")
    open_tab(page, 'pixel-map')
    page.click('#btn-export')
    page.wait_for_timeout(200)
    assert page.input_value('#export-format') == 'pdf' and not page.is_visible('#export-3d-png-section')
    page.click('#export-cancel')
    open_tab(page, '3d')
    assert page.errors == []


def test_a_preset_view_frames_every_screen_as_its_view_button_does(page):
    reset(page)
    open_3d(page, 2)
    view = page.evaluate("[document.getElementById('s3d-canvas').width, document.getElementById('s3d-canvas').height]")
    for name in ('front', 'top', 'left', 'iso'):
        out = render(page, 'p', view=name, width=view[0], height=view[1])
        assert out['bitmap'] == view and out['inFrame'] == 2 and out['screens'] == 2, out
        tab = view_from(page, name)['camera']
        assert close_enough(out['camera']['position'], tab['position'], 2.0), (name, out['camera'], tab)
        assert close_enough(out['camera']['target'], tab['target'], 2.0), (name, out['camera'], tab)
    # a picture of another shape keeps both screens in frame
    for w, h in ((640, 1600), (3000, 400)):
        out = render(page, 'q', view='front', width=w, height=h)
        assert out['bitmap'] == [w, h] and out['inFrame'] == 2, (w, h, out)
    assert page.errors == []


def test_the_tabs_camera_is_never_moved_or_saved(page):
    reset(page)
    open_3d(page, 2)
    page.evaluate("""() => window.app._s3dApplyCamera({mode: 'perspective', position: [3100, 2200, 7400],
        target: [600, 400, 0], zoom: 1})""")
    page.evaluate("() => window.app._s3dSaveCamera()")
    page.wait_for_timeout(300)
    before = camera_now(page)
    saved_before = page.evaluate("() => JSON.stringify(window.app.project.stage3dCamera)")
    puts = []
    page.on('request', lambda r: puts.append(r.url) if r.method == 'PUT' and r.url.endswith('/api/project/stage3d') else None)
    for name in ('current', 'front', 'back', 'left', 'right', 'top', 'iso'):
        render(page, 'c', view=name, width=800, height=450)
    page.wait_for_timeout(700)
    assert camera_now(page) == before
    assert page.evaluate("() => JSON.stringify(window.app.project.stage3dCamera)") == saved_before
    assert puts == [], puts
    # the current view is the tab's camera
    cur = render(page, 'c', view='current', width=800, height=450)
    assert close_enough(cur['camera']['position'], before['position'], 0.05), (cur['camera'], before)
    assert close_enough(cur['camera']['target'], before['target'], 0.05), (cur['camera'], before)
    # orthographic too
    page.click('#s3d-mode-ortho')
    page.wait_for_timeout(500)
    before = camera_now(page)
    out = render(page, 'c', view='top', width=800, height=450)
    assert out['mode'] == 'orthographic' and out['inFrame'] == 2, out
    assert camera_now(page) == before
    page.click('#s3d-mode-persp')
    page.wait_for_timeout(300)
    assert page.errors == []


def test_no_selection_handles_or_corner_marks_in_the_picture(page):
    ids = reset(page)
    open_3d(page, 2)
    page.evaluate("() => window.app._s3dSetGrid(false)")
    try:
        # both screens selected (accent seams), the handles up, a corner spot picked
        page.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[0])", ids)
        page.evaluate("() => window.app._s3dSetCorners(true)")
        page.evaluate("(id) => window.app._s3dPickCorner(id, 2.5)", ids[0])
        marked = settled(page, lambda: dbg(page), lambda d: d['handles'] and d['handles'].get('shown') and d['corner'])
        assert marked['corner'] and marked['corner']['layerId'] == ids[0], marked['corner']
        accent = page.evaluate("""() => [...window.app._s3d.entries.values()].map(e => e.lineMat.color.getHex())""")
        assert all(c != 0x0a0a0a for c in accent), accent
        out = render(page, 'marked', view='front', width=960, height=540)
        assert out['marks']['selectedSeams'] == 2 and out['marks']['cornerSpots'] == 1, out['marks']
        assert out['marks']['overlays'] >= 1, out['marks']
        # the tab's marks are all back
        after = page.evaluate("""() => { const st = window.app._s3d;
            return { seams: [...st.entries.values()].map(e => e.lineMat.color.getHex()),
                     spot: [...st.entries.values()].some(e => e.seam && e.seam.visible),
                     handles: !!(st.handles && st.handles.group.visible) }; }""")
        assert after['seams'] == accent and after['spot'] and after['handles'], after
        # nothing selected, no spot: the same picture
        page.evaluate("() => window.app._s3dPickCorner(null)")
        page.evaluate("() => window.app._s3dSetCorners(false)")
        page.evaluate("() => window.app.setSelectedLayersByIds([], null)")
        settled(page, lambda: dbg(page), lambda d: not (d['handles'] and d['handles'].get('shown')) and not d['corner'])
        page.wait_for_timeout(400)
        plain = render(page, 'plain', view='front', width=960, height=540)
        assert plain['marks']['selectedSeams'] == 0 and plain['marks']['cornerSpots'] == 0, plain['marks']
        assert differing(page, 'marked', 'plain') == 0
        # and the picture is not empty: the screens' faces are in it
        assert plain['colors']['middle'] not in (None, 'clear'), plain['colors']
    finally:
        page.evaluate("() => { window.app._s3dPickCorner(null); window.app._s3dSetCorners(false); window.app._s3dSetGrid(true); }")
    assert page.errors == []


def test_a_size_the_card_cannot_draw_is_refused(page):
    reset(page)
    open_3d(page, 2)
    limit = page.evaluate("() => window.app.stage3dPngLimit()")
    assert limit['w'] >= 1024 and limit['h'] >= 1024, limit
    err = page.evaluate("""async (w) => { try { await window.app.stage3dPngRender({view: 'front', width: w, height: 1000});
        return null; } catch (e) { return { msg: e.message, refused: !!e.refused }; } }""", limit['w'] + 1)
    assert err and err['refused'], err
    assert err['msg'] == (f"{limit['w'] + 1} x 1000 is too big for this computer's graphics card. "
                          f"The most it can draw is {limit['w']} x {limit['h']}; pick a smaller size."), err
    assert logged(page, 'export_3d_png_refused')[-1]['size'] == [limit['w'] + 1, 1000]
    # through the dialog: refused with the dialog up, nothing saved
    saves = page.evaluate("""() => { const a = window.app; window.__saves = 0;
        a.__realSave = a.saveBlobWithPicker; a.saveBlobWithPicker = () => { window.__saves += 1; return Promise.resolve({saved: false}); };
        a.__realLimit = a.stage3dPngLimit; a.stage3dPngLimit = () => ({w: 1000, h: 1000}); return 0; }""")
    try:
        page.evaluate("() => window.app.openExportModal('png-3d')")
        page.select_option('#export-3d-png-size', '1920x1080')
        page.click('#export-confirm')
        toast = settled(page, lambda: page.inner_text('#app-toast-host'), lambda t: 'too big' in t, 4000)
        assert '1920 x 1080 is too big for this computer' in toast, toast
        assert page.is_visible('#export-modal')
        assert page.evaluate("() => window.__saves") == saves == 0
    finally:
        page.evaluate("""() => { const a = window.app; a.saveBlobWithPicker = a.__realSave; a.stage3dPngLimit = a.__realLimit;
            document.getElementById('export-modal').style.display = 'none'; }""")
    assert page.errors == []


def test_the_background_is_the_views_or_transparent(page):
    reset(page)
    open_3d(page, 2)
    page.evaluate("() => window.app._s3dSetGrid(false)")
    try:
        bg = page.evaluate("() => window.app._s3dTokens().canvas").upper()
        solid = render(page, 's', view='front', width=800, height=450)
        clear = render(page, 't', view='front', width=800, height=450, background='transparent')
        assert solid['colors']['tl'] == bg, (solid['colors'], bg)
        assert clear['colors']['tl'] == 'clear', clear['colors']
        # the screens are drawn the same on both: every solid pixel of the
        # transparent picture is the solid picture's own
        got = page.evaluate("""() => { const s = window.__png.s, t = window.__png.t;
            let solid = 0, clear = 0, off = 0, opaqueS = 0;
            for (let i = 0; i < t.length; i += 4) {
                if (s[i + 3] === 255) opaqueS += 1;
                if (t[i + 3] === 0) { clear += 1; continue; }
                if (t[i + 3] < 255) continue;
                solid += 1;
                if (Math.abs(t[i] - s[i]) > 1 || Math.abs(t[i + 1] - s[i + 1]) > 1 || Math.abs(t[i + 2] - s[i + 2]) > 1) off += 1;
            }
            return { solid, clear, off, opaqueS, n: t.length / 4 }; }""")
        assert got['opaqueS'] == got['n'], got
        assert got['solid'] > 5000 and got['clear'] > 5000 and got['off'] == 0, got
    finally:
        page.evaluate("() => window.app._s3dSetGrid(true)")
    assert page.errors == []


def test_the_picture_is_drawn_with_the_3d_tab_never_opened(e2e_server, pw_browser):
    context, pg = _new_page(e2e_server, pw_browser)
    try:
        reset(pg, TWO)
        assert not pg.evaluate("() => !!(window.app._s3d && window.app._s3d.active)")
        out = render(pg, 'shut', view='front', width=640, height=360)
        assert out['bitmap'] == [640, 360] and out['inFrame'] == 2 and out['source'] == '3D stage, tab shut', out
        assert pg.is_hidden('#s3d-view') and pg.is_hidden('#s3d-toolbar')
        assert not pg.evaluate("() => window.app._s3d.active")
        # the tab still opens and frames its screens
        got = open_3d(pg, 2)
        assert got['active'] and got['camera'], got
        open_tab(pg, 'pixel-map')
        assert pg.errors == []
    finally:
        context.close()
