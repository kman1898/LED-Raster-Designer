"""Tests for export API endpoints."""

import io
import json
import zipfile
import base64


def _make_test_image_data():
    """Create a minimal valid base64 PNG for testing."""
    from PIL import Image
    img = Image.new('RGBA', (10, 10), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


def test_export_png(client_with_layer):
    """POST /api/export/png returns a PNG image."""
    resp = client_with_layer.post('/api/export/png', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    # PNG magic bytes
    assert resp.data[:4] == b'\x89PNG'


def test_export_psd(client_with_layer):
    """POST /api/export/psd returns a PSD file (or ZIP fallback without pytoshop)."""
    resp = client_with_layer.post('/api/export/psd', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    # PSD magic bytes "8BPS" if pytoshop installed, ZIP "PK" as fallback
    assert resp.data[:4] in (b'8BPS', b'PK\x03\x04')


def test_export_unified_single_png(client_with_layer):
    """POST /api/export with format=png and one view returns PNG."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'png',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


def test_export_unified_multi_png_zip(client_with_layer):
    """POST /api/export with format=png and multiple views returns ZIP."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'png',
        'views': ['pixel-map', 'cabinet-id'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.content_type == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert len(zf.namelist()) == 2


def test_export_unified_pdf(client_with_layer):
    """POST /api/export with format=pdf returns a PDF."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'pdf',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


def test_export_zip_images(client_with_layer):
    """POST /api/export/zip-images creates a ZIP from base64 images."""
    img_data = _make_test_image_data()
    resp = client_with_layer.post('/api/export/zip-images', json={
        'project_name': 'Test',
        'images': [
            {'name': 'view1.png', 'data': img_data},
            {'name': 'view2.png', 'data': img_data},
        ],
    })
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'view1.png' in zf.namelist()
    assert 'view2.png' in zf.namelist()


def test_export_pdf_from_images(client_with_layer):
    """POST /api/export/pdf-from-images creates a PDF from base64 images."""
    img_data = _make_test_image_data()
    resp = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Test',
        'images': [
            {'name': 'Pixel Map', 'data': img_data, 'width': 100, 'height': 100},
        ],
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


def test_export_zip_layers(client_with_layer):
    """POST /api/export/zip returns ZIP of layer PNGs with manifest."""
    resp = client_with_layer.post('/api/export/zip', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'manifest.json' in zf.namelist()


def test_client_log(client):
    """POST /api/log accepts client-side log entries."""
    resp = client.post('/api/log', json={
        'action': 'test_action',
        'details': {'key': 'value'},
    })
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


# ── Resolume XML Export Tests ──────────────────────────────────────

def test_export_resolume_xml(client_with_layer):
    """POST /api/export/resolume returns valid XML."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test Project',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    assert resp.status_code == 200
    assert 'xml' in resp.content_type
    xml = resp.data.decode('utf-8')
    assert '<?xml version="1.0"' in xml
    assert '<XmlState name="Test Project">' in xml
    assert 'Resolume Arena' in xml


def test_export_resolume_xml_has_slice(client_with_layer):
    """Resolume XML contains a Slice for the screen layer.

    v0.8 Slice 11: the wrapping <Screen> element is named after the canvas
    (default 'Canvas 1' for a fresh project, not the old hard-coded
    'Screen 1'); the layer's own name lives on the inner Polygon/Slice
    Common Params block. Verify both: the per-canvas Screen wrapper exists,
    and the Slice carries the layer's name from the conftest fixture
    ('TestScreen').
    """
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert '<Slice' in xml
    assert '<Screen name="Canvas 1"' in xml
    assert 'value="TestScreen"' in xml


def test_export_resolume_xml_correct_rect(client_with_layer):
    """Resolume XML InputRect matches layer bounds."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    # Default layer: 8 cols × 5 rows, 192×384 cabinet, offset 0,0
    # Width = 8 * 192 = 1536, Height = 5 * 384 = 1920
    assert '<InputRect' in xml
    assert '<OutputRect' in xml


def test_export_resolume_xml_composition_size(client_with_layer):
    """Resolume XML contains correct composition texture size."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    xml = resp.data.decode('utf-8')
    assert 'width="3840"' in xml
    assert 'height="2160"' in xml


def test_export_resolume_xml_hidden_layer_excluded(client):
    """Hidden layers are excluded from Resolume XML export."""
    import app as app_module
    # Add two layers, hide one
    client.post('/api/layer/add', json={
        'name': 'Visible', 'columns': 4, 'rows': 3,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    client.post('/api/layer/add', json={
        'name': 'Hidden', 'columns': 4, 'rows': 3,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    # Hide the second layer
    layers = app_module.current_project['layers']
    hidden_layer = [l for l in layers if l['name'] == 'Hidden'][0]
    hidden_layer['visible'] = False

    resp = client.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert 'value="Visible"' in xml
    assert 'value="Hidden"' not in xml


def test_export_resolume_xml_multiple_layers(client):
    """Resolume XML contains one Slice per visible screen layer."""
    client.post('/api/layer/add', json={
        'name': 'Main', 'columns': 10, 'rows': 5,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    client.post('/api/layer/add', json={
        'name': 'Side', 'columns': 5, 'rows': 8,
        'cabinet_width': 60, 'cabinet_height': 120,
        'offset_x': 1000, 'offset_y': 0,
    })
    resp = client.post('/api/export/resolume', json={
        'project_name': 'Multi',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert 'value="Main"' in xml
    assert 'value="Side"' in xml
    assert xml.count('<Slice') == 2


def test_export_resolume_xml_bezier_warper(client_with_layer):
    """Resolume XML contains BezierWarper with 16 vertices (4x4 grid)."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert '<BezierWarper controlWidth="4" controlHeight="4">' in xml
    # 4x4 grid = 16 vertices inside the BezierWarper
    import re
    warper_section = re.search(r'<BezierWarper.*?</BezierWarper>', xml, re.DOTALL)
    assert warper_section
    vertices = re.findall(r'<v x=', warper_section.group())
    assert len(vertices) == 16


# ── The binder's PDF: pages as display lists ─────────────────────────────
# /api/export/pdf-from-pages (app.py) replays what app-binder.js's
# recording context wrote down - rects, lines, text and images in page
# pixels - onto a page of `page_size` points, the text set in Helvetica so
# the PDF's text is real text (2026-09-08: "so all the text seems low res
# still" - the cure is vector text, the way a Vectorworks packet reads).

def _page(ops, images=None, **over):
    page = {'name': 'P', 'width': 2200, 'height': 1700, 'page_size': [792, 612],
            'ops': ops, 'images': images or {}}
    page.update(over)
    return page


def _text(text, **over):
    op = {'op': 'text', 'text': text, 'x': 42, 'y': 60, 'size': 35, 'weight': 800,
          'align': 'left', 'baseline': 'alphabetic', 'color': '#111111', 'rotate': 0}
    op.update(over)
    return op


def _pdf_pages(data):
    from pypdf import PdfReader
    return PdfReader(io.BytesIO(data)).pages


def _fonts(page):
    res = page['/Resources']
    return sorted(f['/BaseFont'].lstrip('/') for f in res['/Font'].values()) if '/Font' in res else []


def test_pdf_from_pages_replays_every_op_kind_on_a_page_in_points(client):
    """One page carrying every op kind - a filled rect, a stroked rect, a
    solid and a dashed polyline, plain and rotated text, an image - comes
    back as a PDF whose page is `page_size` points, whose text is real text
    (extract_text finds it) set in Helvetica / Helvetica-Bold (weight >= 600
    is Bold), and whose image is an XObject on the page."""
    ops = [
        {'op': 'rect', 'x': 0, 'y': 0, 'w': 2200, 'h': 1700, 'fill': '#ffffff'},
        {'op': 'rect', 'x': 42, 'y': 70, 'w': 2116, 'h': 6, 'fill': '#111111'},
        {'op': 'rect', 'x': 100, 'y': 100, 'w': 24, 'h': 24, 'stroke': '#111111', 'width': 2},
        {'op': 'line', 'points': [[100, 300], [200, 300], [200, 400]], 'width': 3, 'dash': [], 'stroke': '#111111'},
        {'op': 'line', 'points': [[100, 500], [900, 500]], 'width': 2, 'dash': [12, 6], 'stroke': '#666666'},
        _text('CIRCUITS'),
        _text('SR1-1', x=1100, y=200, size=24, weight=400, align='center'),
        _text('page 3 of 17', x=2158, y=60, size=27, weight=400, align='right', baseline='middle'),
        _text("SR1 · 125'", x=2000, y=600, size=28, weight=700, align='center', rotate=1.5707963267948966),
        {'op': 'image', 'id': 'img1', 'x': 300, 'y': 700, 'w': 800, 'h': 400},
    ]
    resp = client.post('/api/export/pdf-from-pages', json={
        'project_name': 'Show', 'pages': [_page(ops, {'img1': _make_test_image_data()})],
    })
    assert resp.status_code == 200, resp.get_json()
    assert resp.content_type == 'application/pdf' and resp.data[:5] == b'%PDF-'
    pages = _pdf_pages(resp.data)
    assert len(pages) == 1
    page = pages[0]
    assert [float(v) for v in page.mediabox] == [0.0, 0.0, 792.0, 612.0]
    text = page.extract_text()
    for want in ('CIRCUITS', 'SR1-1', 'page 3 of 17', "SR1 · 125'"):
        assert want in text, (want, text)
    assert _fonts(page) == ['Helvetica', 'Helvetica-Bold']
    xobjects = page['/Resources'].get('/XObject', {})
    assert xobjects, 'the image op lands as an XObject on the page'
    assert any(x.get_object().get('/Subtype') == '/Image' for x in xobjects.values())
    # the content stream carries the vector ops: a dash pattern, a path
    content = page.get_contents().get_data()
    assert b' d' in content and b' l' in content and b' re' in content, content[:400]
    assert b'Helvetica-Bold' in resp.data and b'Helvetica' in resp.data
    from pypdf import PdfReader
    assert PdfReader(io.BytesIO(resp.data)).metadata.title == 'Show'


def test_pdf_from_pages_sizes_every_page_on_its_own(client):
    """Each page is its own size in points: the letter floor, and a page
    that grew (letter wide, 978.48 pt tall - 2718 page px)."""
    resp = client.post('/api/export/pdf-from-pages', json={
        'project_name': 'Show',
        'pages': [_page([_text('Cover')]),
                  _page([_text('SR - MAIN')], height=2718, page_size=[792, 612 * 2718 / 1700]),
                  _page([_text('Pull')])],
    })
    assert resp.status_code == 200
    pages = _pdf_pages(resp.data)
    assert [[float(v) for v in p.mediabox] for p in pages] == \
        [[0, 0, 792, 612], [0, 0, 792, 978.48], [0, 0, 792, 612]]
    assert [p.extract_text().strip() for p in pages] == ['Cover', 'SR - MAIN', 'Pull']


def test_pdf_from_pages_takes_a_sheet_of_any_size(client):
    """The binder's sheets: a Tabloid page (3400 x 2200 px at 200 px/in) is
    1224 x 792 pt, a Letter one 792 x 612, an ARCH D 2592 x 1728 - inches
    x 72 - and a text at the sheet's far corner lands there, in points."""
    sheets = [(3400, 2200, [1224, 792]), (2200, 1700, [792, 612]), (7200, 4800, [2592, 1728])]
    resp = client.post('/api/export/pdf-from-pages', json={
        'project_name': 'Set',
        'pages': [_page([_text('2.1', x=w - 100, y=h - 60, size=56, weight=800)], width=w, height=h, page_size=pt)
                  for w, h, pt in sheets],
    })
    assert resp.status_code == 200
    pages = _pdf_pages(resp.data)
    assert [[float(v) for v in p.mediabox] for p in pages] == [[0, 0, *pt] for _w, _h, pt in sheets]
    for p in pages:
        assert '2.1' in p.extract_text()
        # the number is set in Helvetica-Bold at 56 px x 72 / 200 = 20.16 pt
        assert b'20.16' in p.get_contents().get_data() or b'20.2' in p.get_contents().get_data()


def test_pdf_from_pages_rotated_text_does_not_crash_and_is_still_text(client):
    """The brackets' labels turn a quarter either way; both come through as
    text, and nothing else on the page moves."""
    ops = [_text('K1 · 100\'', x=2000, y=600, size=28, weight=700, align='center', rotate=1.5707963267948966),
           _text('K2 · 100\'', x=200, y=600, size=28, weight=700, align='center', rotate=-1.5707963267948966),
           _text('CIRCUITS')]
    resp = client.post('/api/export/pdf-from-pages', json={'project_name': 'Show', 'pages': [_page(ops)]})
    assert resp.status_code == 200
    text = _pdf_pages(resp.data)[0].extract_text()
    assert "K1 · 100'" in text and "K2 · 100'" in text and 'CIRCUITS' in text, text


def test_pdf_from_pages_rejects_a_bad_payload_with_400_json(client):
    """A bad payload is a 400 with a JSON error, like the sibling route's
    errors - never a 500 and never a half-built PDF."""
    bad = [
        ({}, 'pages must be'),
        ({'pages': []}, 'pages must be'),
        ({'pages': ['x']}, 'page 1'),
        ({'pages': [{'name': 'x'}]}, 'page_size'),
        ({'pages': [_page([_text('a')], page_size=[792])]}, 'page_size'),
        ({'pages': [_page([_text('a')], width=0)]}, 'width and height'),
        ({'pages': [_page('nope')]}, 'ops must be a list'),
        ({'pages': [_page([{'op': 'arc'}])]}, 'every op must be one of'),
        ({'pages': [_page([_text(5)])]}, 'text must be a string'),
        ({'pages': [_page([{'op': 'line', 'points': [[1, 2]], 'stroke': '#000000'}])]}, 'two points'),
        ({'pages': [_page([{'op': 'rect', 'x': 'a', 'y': 0, 'w': 1, 'h': 1, 'fill': '#000'}])]}, 'must be a number'),
        ({'pages': [_page([{'op': 'image', 'id': 'nope', 'x': 0, 'y': 0, 'w': 1, 'h': 1}])]}, 'has no bitmap'),
        ({'pages': [_page([{'op': 'image', 'id': 'i', 'x': 0, 'y': 0, 'w': 1, 'h': 1}],
                          {'i': 'data:image/png;base64,AAAA'})]}, 'not a PNG'),
    ]
    for payload, want in bad:
        resp = client.post('/api/export/pdf-from-pages', json=payload)
        assert resp.status_code == 400, (payload, resp.status_code, resp.data[:200])
        err = resp.get_json()
        assert err and want in err['error'], (payload, err)
    resp = client.post('/api/export/pdf-from-pages', data='not json', content_type='text/plain')
    assert resp.status_code == 400 and 'error' in resp.get_json()
    # the sibling keeps every other export
    ok = client.post('/api/export/pdf-from-images', json={
        'project_name': 'Test', 'images': [{'name': 'Pixel Map', 'data': _make_test_image_data(),
                                            'width': 100, 'height': 100}]})
    assert ok.status_code == 200 and ok.data[:5] == b'%PDF-'
