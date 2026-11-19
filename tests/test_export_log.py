"""What the server's exports and the native output feed write to the app
log (2026-11-19 logging audit, phase 2): one export_file_done line per
/api/export/* request with what it wrote, its bytes and its time; a
failed export as a warning with its error; the native feed's first frame
and each size change, never every frame; the pull sheet's rows and bytes;
and never a picture or a file's contents."""
import base64
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402
import log_diff  # noqa: E402
import routes_export  # noqa: E402
import routes_output  # noqa: E402
import routes_pull_sheet  # noqa: E402


@pytest.fixture()
def lines(monkeypatch):
    """Every line the export, output and pull-sheet routes write."""
    got = []

    def spy(action, details=None, source='server', **kw):
        got.append({'action': action, 'details': details, **kw})

    for mod in (routes_export, routes_output, routes_pull_sheet):
        monkeypatch.setattr(mod, 'log_event', spy)
    return got


def _png(w, h, colour=(255, 0, 0, 255)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (w, h), colour).save(buf, format='PNG')
    return buf.getvalue()


def _data_url(w=10, h=10):
    return 'data:image/png;base64,' + base64.b64encode(_png(w, h)).decode()


def _done(got):
    return [x for x in got if x['action'] == 'export_file_done']


def test_a_png_export_says_what_it_wrote(client_with_layer, lines):
    resp = client_with_layer.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    [line] = _done(lines)
    d = line['details']
    assert d['route'] == '/api/export/png' and d['status'] == 200 and d['files'] == 1 and d['screens'] == 1
    assert d['bytes'] == len(resp.data) and d['ms'] >= 0
    assert d['size'] == [app_module.current_project.get('raster_width', 1920),
                         app_module.current_project.get('raster_height', 1080)]
    assert line['area'] == 'export'
    assert line['msg'].startswith('PNG export written: 1 file, ') and f'{len(resp.data):,} bytes' in line['msg']


def test_a_zip_of_client_images_names_its_files_never_their_bytes(client, lines):
    images = [{'name': 'A.png', 'data': _data_url()}, {'name': 'B.png', 'data': _data_url()}]
    resp = client.post('/api/export/zip-images', json={'project_name': 'P', 'images': images})
    assert resp.status_code == 200
    [line] = _done(lines)
    d = line['details']
    assert d['files'] == 2 and d['names'] == ['A.png', 'B.png'] and d['image_bytes'] > 0
    assert 'base64' not in json.dumps(d)
    assert line['msg'].startswith('PNG ZIP export written: 2 files')


def test_the_binder_pdf_says_its_pages_and_bitmaps(client, lines):
    page = {'name': 'p1', 'width': 2200, 'height': 1700, 'page_size': [792, 612],
            'ops': [{'op': 'rect', 'x': 10, 'y': 10, 'w': 100, 'h': 50, 'fill': '#ff0000'}],
            'images': {}}
    resp = client.post('/api/export/pdf-from-pages', json={'project_name': 'P', 'pages': [page, page]})
    assert resp.status_code == 200, resp.get_json()
    [line] = _done(lines)
    d = line['details']
    assert d['pages'] == 2 and d['bitmaps'] == 0 and d['ops'] == 2 and d['bytes'] == len(resp.data)
    assert line['msg'].startswith('Binder PDF written: 1 file, 2 pages')


def test_a_refused_export_is_a_warning_with_its_error(client, lines):
    resp = client.post('/api/export/pdf-from-pages', json={'project_name': 'P', 'pages': []})
    assert resp.status_code == 400
    [line] = _done(lines)
    assert line['level'] == 'warn' and line['details']['status'] == 400
    assert line['details']['error'] == 'pages must be a non-empty list'
    assert line['msg'] == 'Binder PDF failed (400): pages must be a non-empty list'


def test_a_psd_export_counts_its_layers(client_with_layer, lines):
    pytest.importorskip('pytoshop')
    resp = client_with_layer.post('/api/export/psd-from-image', json={
        'project_name': 'P', 'view_name': 'Pixel Map', 'image_data': _data_url(64, 32), 'width': 64, 'height': 32,
        'layers': [{'name': 'S1', 'offset_x': 0, 'offset_y': 0, 'width': 32, 'height': 32, 'visible': True}]})
    assert resp.status_code == 200
    [line] = _done(lines)
    d = line['details']
    assert d['layers'] == 1 and d['size'] == [64, 32] and d['view'] == 'Pixel Map'
    assert '1 PSD layer' in line['msg']


def test_the_xml_export_counts_its_slices(client_with_layer, lines):
    resp = client_with_layer.post('/api/export/resolume', json={'project_name': 'P'})
    assert resp.status_code == 200
    old = next(x for x in lines if x['action'] == 'export_resolume')['details']
    assert old['slices'] >= 1 and old['bytes'] == len(resp.data) and old['screens'] >= 1
    [line] = _done(lines)
    assert line['details']['slices'] == old['slices']
    msg = log_diff.message('export_resolume', old)
    assert msg.startswith('Advanced Output XML written: ') and 'slice' in msg


def test_the_pull_sheet_line_has_its_rows_and_bytes(client, lines):
    pytest.importorskip('openpyxl')
    body = {'project_name': 'P', 'pull_list': {'positions': [
        {'name': 'SL', 'rows': [{'type': 'Cat6A', 'length': '50', 'qty': 2}, {'type': 'True1', 'length': '25', 'qty': 4}]},
    ]}}
    resp = client.post('/api/export/pull-sheet', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    d = next(x for x in lines if x['action'] == 'export_pull_sheet')['details']
    assert d['positions'] == 1 and d['rows'] == 2 and d['bytes'] == len(resp.data)
    assert log_diff.message('export_pull_sheet', d).startswith('Pull sheet written: 1 position, 2 rows, ')


def test_the_svg_line_reads_plainly():
    msg = log_diff.message('export_svg', {'files': 2, 'bytes': 12345, 'each': [
        {'file': 'a.svg', 'view': 'power', 'canvas': 'C1', 'bytes': 1}, {'file': 'b.svg', 'view': 'data-flow'}]})
    assert msg == 'SVG export: 2 files, 12,345 bytes (data-flow, power)'


def test_a_native_feed_logs_its_first_frame_and_size_changes_only(client, lines):
    feed = 'feedlog000001'
    with routes_output._cond:
        routes_output._feeds[feed] = routes_output._Feed()
    try:
        for png in (_png(64, 32), _png(64, 32), _png(64, 32), _png(128, 32)):
            assert client.post(f'/api/output/feed/{feed}/frame', data=png,
                               headers={'Content-Type': 'image/png'}).status_code == 200
        client.post(f'/api/output/feed/{feed}/frame', data=b'not a picture', headers={'Content-Type': 'image/png'})
    finally:
        with routes_output._cond:
            routes_output._feeds.pop(feed, None)
    got = [x for x in lines if x['action'] == 'output_native_frame']
    assert [(x['details']['seq'], x['details']['size']) for x in got] == [(1, [64, 32]), (4, [128, 32]), (5, None)]
    assert got[0]['details']['first'] is True and got[0]['area'] == 'output'
    assert got[0]['msg'].startswith(f'Native output {feed} got its first frame, 64x32 (')
    assert got[1]['msg'].startswith(f'Native output {feed} frame size changed, 128x32')
    assert all('PNG' not in json.dumps(x['details']) for x in got)


def test_the_png_size_is_read_off_its_header():
    assert routes_output._png_size(_png(7, 5)) == (7, 5)
    assert routes_output._png_size(b'\x89PNG\r\n\x1a\n' + b'x' * 64) is None
    assert routes_output._png_size(b'') is None
