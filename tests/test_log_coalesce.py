"""The log writer (app.log_event): one line with a level, an area and a
plain message; repeated lines of one gesture fold into one; a line is
capped; and the viewer's filters on GET /api/logs (2026-11-19 logging
audit, phase 1)."""
import json

import pytest

import app as app_module
import routes_logs


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    """The writer and the viewer both pointed at a throwaway file."""
    app_module.flush_log()
    path = tmp_path / 'led_raster_designer.log'
    path.write_text('', encoding='utf-8')
    monkeypatch.setattr(app_module, 'LOG_FILE_PATH', str(path))
    monkeypatch.setattr(app_module, 'LOG_DIR_PATH', str(tmp_path))
    monkeypatch.setattr(routes_logs, 'LOG_FILE_PATH', str(path))
    monkeypatch.setattr(routes_logs, 'LOG_DIR_PATH', str(tmp_path))
    yield path
    app_module.flush_log()


def _write(action, details=None, **kw):
    # conftest wraps app.log_event; the routes call the same function.
    app_module.log_event(action, details, **kw)


def _lines(path):
    app_module.flush_log()
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def test_a_line_has_level_area_message_and_the_old_keys(log_file):
    _write('merge_runs_refused', {'why': 'locked', 'layerId': 3})
    [line] = _lines(log_file)
    assert list(line) == ['timestamp', 'lvl', 'area', 'source', 'action', 'msg', 'details']
    assert line['lvl'] == 'warn' and line['area'] == 'data' and line['source'] == 'server'
    assert line['msg'] == 'merge runs refused: why=locked, layerId=3'
    # milliseconds, local time
    assert len(line['timestamp']) == len('2026-11-18 14:02:11.482')


def test_a_page_line_names_its_level_area_and_message(log_file):
    _write('custom_thing', {'a': 1, '_lvl': 'warn', '_area': 'power', '_msg': 'Said plainly'}, source='client')
    [line] = _lines(log_file)
    assert (line['lvl'], line['area'], line['msg']) == ('warn', 'power', 'Said plainly')
    assert line['details'] == {'a': 1}


def test_held_spinner_ticks_fold_into_one_line(log_file):
    for v in range(30, 49):
        _write('ui_change', {'id': 'label-size', 'type': 'number', 'value': v, 'page': 'A'}, source='client')
    lines = _lines(log_file)
    assert [x['action'] for x in lines] == ['ui_change', 'ui_change']
    first, run = lines
    assert first['details']['value'] == 30
    assert run['details']['value'] == 48 and run['details']['steps'] == 19
    assert run['details']['from'] == {'value': 30}
    assert run['msg'].startswith('Set label-size to 48 (from 30) (19 steps')
    # the run is stamped when it began
    assert run['timestamp'] == first['timestamp']


def test_two_fields_fold_apart_and_another_page_folds_apart(log_file):
    for v in range(3):
        _write('ui_change', {'id': 'a', 'value': v, 'page': 'A'}, source='client')
        _write('ui_change', {'id': 'b', 'value': v, 'page': 'A'}, source='client')
        _write('ui_change', {'id': 'a', 'value': v, 'page': 'B'}, source='client')
    lines = _lines(log_file)
    runs = [(x['details']['id'], x['details']['page'], x['details'].get('steps')) for x in lines]
    assert sorted(r for r in runs if r[2]) == [('a', 'A', 3), ('a', 'B', 3), ('b', 'A', 3)]


def test_a_warning_writes_the_held_runs_first(log_file):
    for v in range(4):
        _write('ui_change', {'id': 'a', 'value': v, 'page': 'A'}, source='client')
    _write('toast_error', {'message': 'Nope'}, source='client')
    actions = [x['action'] for x in _lines(log_file)]
    assert actions == ['ui_change', 'ui_change', 'toast_error']


def test_echo_bookkeeping_is_debug_and_folds_into_one_sync_line(log_file):
    for i in range(12):
        _write('socket_layer_updated_suppressed_same_copy', {'id': 2, 'page': 'A'}, source='client')
    _write('socket_layer_updated_held_for_gesture', {'id': 2, 'page': 'A'}, source='client')
    _write('socket_layer_updated_held_for_gesture', {'id': 2, 'page': 'A'}, source='client')
    lines = _lines(log_file)
    assert [x['lvl'] for x in lines] == ['debug', 'debug']
    assert lines[1]['action'] == 'sync_echoes_folded' and lines[1]['area'] == 'sync'
    assert lines[1]['msg'].startswith('sync: 14 echoes settled (12 same copy, 2 held for a gesture)')


def test_a_line_after_a_quiet_second_starts_a_new_run(log_file, monkeypatch):
    monkeypatch.setattr(app_module, 'LOG_FOLD_WINDOW_S', 0.0)
    _write('ui_change', {'id': 'a', 'value': 1, 'page': 'A'}, source='client')
    _write('ui_change', {'id': 'a', 'value': 2, 'page': 'A'}, source='client')
    assert [x['details']['value'] for x in _lines(log_file)] == [1, 2]


def test_fold_false_never_folds(log_file):
    for v in range(3):
        _write('ui_change', {'id': 'a', 'value': v, 'page': 'A'}, source='client', fold=False)
    assert len(_lines(log_file)) == 3


def test_a_huge_line_is_capped_and_a_traceback_keeps_its_end(log_file):
    tb = 'Traceback (most recent call last):\n' + 'x' * 20000 + '\nValueError: the end'
    _write('unhandled_exception', {'error': 'e', 'traceback': tb, 'other': list(range(5000))})
    [line] = _lines(log_file)
    raw = json.dumps(line)
    assert len(raw.encode('utf-8')) <= app_module.LOG_LINE_MAX_BYTES
    assert line['details']['traceback'].endswith('ValueError: the end')
    assert line['details']['truncated'] is True
    assert line['lvl'] == 'error'


def test_an_image_payload_is_never_written(log_file):
    _write('whatever', {'imageData': 'data:image/png;base64,' + 'A' * 4000})
    text = log_file.read_text(encoding='utf-8')
    assert 'AAAAAAAA' not in text and '<4022 chars>' in text


# ── a screen save logs what it changed ───────────────────────────────────

def _layer(client):
    r = client.post('/api/layer/add', json={'name': 'STAGE LEFT', 'columns': 4, 'rows': 3})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def test_update_layer_logs_the_diff_and_the_gesture_name(client, log_file):
    layer = _layer(client)
    body = dict(layer)
    body['dataFlowLabelSize'] = 48
    r = client.put(f"/api/layer/{layer['id']}?client=P1&seq=1", json=body,
                   headers={'X-LRD-Action': 'Change%20Data%20Flow%20Label%20Size'})
    assert r.status_code == 200
    edits = [x for x in _lines(log_file) if x['action'] == 'update_layer']
    assert len(edits) == 1, edits
    d = edits[0]['details']
    assert d['diff'] == {'dataFlowLabelSize': [d['diff']['dataFlowLabelSize'][0], 48]}
    assert d['label'] == 'Change Data Flow Label Size'
    assert edits[0]['area'] == 'data'
    assert edits[0]['msg'].startswith('Change Data Flow Label Size: STAGE LEFT')
    assert len(json.dumps(edits[0])) < 1000


def test_a_save_that_changed_nothing_is_debug(client, log_file):
    layer = _layer(client)
    client.put(f"/api/layer/{layer['id']}", json=dict(layer))
    lines = _lines(log_file)
    assert not [x for x in lines if x['action'] == 'update_layer']
    [noop] = [x for x in lines if x['action'] == 'layer_save_noop']
    assert noop['lvl'] == 'debug'


def test_a_dragged_screen_folds_into_one_move(client, log_file):
    layer = _layer(client)
    body = dict(layer)
    for x in range(0, 200, 20):
        body['offset_x'] = x
        client.put(f"/api/layer/{layer['id']}?client=P1", json=body)
    edits = [x for x in _lines(log_file) if x['action'] == 'update_layer']
    assert len(edits) == 2, [e['msg'] for e in edits]
    assert edits[1]['details']['diff']['offset_x'] == [0, 180]
    assert edits[1]['details']['steps'] == 9


def test_prefs_and_canvas_log_what_changed(client, log_file):
    old = dict(app_module.server_preferences or {})
    try:
        new = dict(old, frameRate=50)
        client.put('/api/preferences', json=new)
        client.put('/api/canvas/c1', json={'workspace_x': 123})
    finally:
        app_module.server_preferences = old
    lines = _lines(log_file)
    [prefs] = [x for x in lines if x['action'] == 'save_preferences']
    assert list(prefs['details']['diff']) == ['frameRate'] or old.get('frameRate') == 50
    [canvas] = [x for x in lines if x['action'] == 'canvas_update']
    assert canvas['details']['diff']['workspace_x'][1] == 123
    assert 'changed' not in canvas['details']


# ── the viewer's filters ─────────────────────────────────────────────────

def _old_line(action, details, ts='2026-11-01 10:00:00'):
    return json.dumps({'timestamp': ts, 'source': 'client', 'action': action, 'details': details})


def test_viewer_filters_by_level_area_text_and_screen(client, log_file):
    _write('add_layer', {'id': 3, 'name': 'Wall'})
    _write('merge_runs_refused', {'layerId': 3, 'why': 'locked'})
    _write('socket_project_data', {'page': 'A'}, source='client')
    _write('stage3d_edit', {'id': 4})
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(_old_line('toast_error', {'message': 'Older line'}) + '\n')

    def get(q):
        data = client.get('/api/logs?fill=1&' + q).get_json()
        return [json.loads(x) for x in data['lines']]

    assert [x['action'] for x in get('lvl=warn')] == ['merge_runs_refused', 'toast_error']
    assert [x['action'] for x in get('lvl=error,warn,info')] == [
        'add_layer', 'merge_runs_refused', 'stage3d_edit', 'toast_error']
    assert [x['action'] for x in get('area=3d')] == ['stage3d_edit']
    assert [x['action'] for x in get('q=older')] == ['toast_error']
    assert [x['action'] for x in get('layer=3')] == ['add_layer', 'merge_runs_refused']
    # an older line gets its level, area and message filled in
    older = get('q=older')[0]
    assert (older['lvl'], older['area'], older['msg']) == ('warn', 'app', 'Error shown: Older line')


def test_viewer_without_filters_is_unchanged(client, log_file):
    _write('add_layer', {'id': 3})
    data = client.get('/api/logs').get_json()
    assert data['filtered'] is False and data['matched_count'] is None
    assert json.loads(data['lines'][0])['action'] == 'add_layer'


def test_copy_for_a_bug_report_is_redacted(client, log_file):
    _write('ui_change', {'id': 'export-binder-pm-email', 'value': 'pat@example.com'}, source='client')
    _write('native_dialog_save_file', {'path': r'C:\Users\Pat Smith\Shows\a.lrd', 'host': '192.168.1.20'})
    data = client.get('/api/logs?redact=1&fill=1').get_json()
    text = '\n'.join(data['lines'])
    assert 'pat@example.com' not in text and 'Pat Smith' not in text and '192.168.1.20' not in text
    plain = '\n'.join(client.get('/api/logs').get_json()['lines'])
    assert 'Pat Smith' in plain   # the file itself keeps them
