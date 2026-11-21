"""log_diff: what a log line says about an edit (a diff, never the whole
object), its area and level, its message, and the redaction a log copied
for a bug report gets (2026-11-19 logging audit, phase 1)."""
import log_diff as L


# ── diffs ─────────────────────────────────────────────────────────────────

def test_a_scalar_change_is_old_and_new_and_untouched_keys_are_left_out():
    before = L.snapshot({'columns': 4, 'rows': 3, 'name': 'A'}, ['columns', 'rows', 'name'])
    assert L.diff(before, {'columns': 6, 'rows': 3, 'name': 'A'}) == {'columns': [4, 6]}


def test_a_whole_float_is_the_same_number():
    before = L.snapshot({'h': 500, 'sizes': [1.0, 2]}, ['h', 'sizes'])
    assert L.diff(before, {'h': 500.0, 'sizes': [1, 2.0]}) == {}
    assert L.diff(before, {'h': 500.5, 'sizes': [1, 2]}) == {'h': [500, 500.5]}


def test_nothing_changed_is_an_empty_diff():
    obj = {'x': 1, 'stage3d': {'x': 2}, 'panels': [{'hidden': False}]}
    assert L.diff(L.snapshot(obj, list(obj)), obj) == {}


def test_panels_say_what_was_hidden_or_blanked_not_the_list():
    before = L.snapshot({'panels': [{'hidden': False, 'blank': False}] * 6}, ['panels'])
    after = {'panels': [{'hidden': True}] * 2 + [{'blank': True}] + [{}] * 3}
    assert L.diff(before, after) == {'panels': 'hidden 0 to 2, blank 0 to 1'}


def test_custom_paths_say_cabinets_per_port():
    before = L.snapshot({'customPortPaths': {'4': [1] * 12, '6': [1]}}, ['customPortPaths'])
    after = {'customPortPaths': {'4': [1] * 15, '5': [1] * 8}}
    assert L.diff(before, after) == {'customPortPaths':
                                     'port 4: 12 to 15 cabinets; port 5 added (8 cabinets); port 6 removed'}


def test_a_dict_names_its_changed_fields_one_level_down():
    before = L.snapshot({'stage3d': {'x': 100, 'y': 0, 'z': 5}}, ['stage3d'])
    assert L.diff(before, {'stage3d': {'x': 340, 'y': 0, 'z': 5}}) == {'stage3d.x': [100, 340]}


def test_a_long_list_is_counted_not_copied():
    before = L.snapshot({'bars': list(range(80))}, ['bars'])
    assert L.diff(before, {'bars': list(range(81))}) == {'bars': '80 to 81 items'}


def test_a_long_string_is_cut():
    before = L.snapshot({'notes': 'a'}, ['notes'])
    got = L.diff(before, {'notes': 'b' * 300})['notes']
    assert got[0] == 'a' and len(got[1]) == 80 and got[1].endswith('...')


def test_a_key_that_appears_or_goes_reads_none():
    before = L.snapshot({'a': 1}, ['a', 'b'])
    assert L.diff(before, {'b': 2}) == {'a': [1, None], 'b': [None, 2]}


def test_merge_diffs_keeps_where_a_gesture_started_and_ended():
    assert L.merge_diffs({'x': [30, 31], 'y': [0, 1]}, {'x': [47, 48]}) == {'x': [30, 48], 'y': [0, 1]}


# ── payloads and secrets never reach the log ─────────────────────────────

def test_image_payloads_are_their_size():
    data_url = 'data:image/png;base64,' + 'A' * 5000
    got = L.scrub({'imageData': data_url, 'binder': {'logo': data_url}, 'name': 'Screen 1'})
    assert got == {'imageData': f'<{len(data_url)} chars>',
                   'binder': {'logo': f'<{len(data_url)} chars>'}, 'name': 'Screen 1'}
    before = L.snapshot({'imageData': data_url}, ['imageData'])
    d = L.diff(before, {'imageData': data_url + 'B'})
    assert 'AAAA' not in str(d)


def test_a_bare_base64_run_is_a_payload_and_prose_is_not():
    import base64
    blob = base64.b64encode(bytes(range(256)) * 2).decode('ascii')
    assert L.scrub({'blob': blob}) == {'blob': f'<{len(blob)} chars>'}
    prose = 'the quick brown fox jumps over the lazy dog ' * 10
    assert L.scrub({'note': prose}) == {'note': prose}


def test_secret_keys_are_hidden():
    assert L.scrub({'password': 'hunter2', 'apiKey': 'abc', 'x': 1}) == {
        'password': '[hidden]', 'apiKey': '[hidden]', 'x': 1}


def test_scrub_leaves_a_clean_dict_as_the_same_object():
    d = {'a': 1, 'b': {'c': 'short'}}
    assert L.scrub(d) is d


# ── area and level ────────────────────────────────────────────────────────

def test_levels():
    assert L.level_for('client_error') == 'error'
    assert L.level_for('stage3d_paint_failed') == 'error'
    assert L.level_for('client_error', {'opaque': True}) == 'warn'
    assert L.level_for('toast_error') == 'warn'
    assert L.level_for('merge_runs_refused') == 'warn'
    assert L.level_for('client_log_dropped', {'level': 'warn'}) == 'warn'
    assert L.level_for('socket_layer_updated_suppressed_same_copy') == 'debug'
    assert L.level_for('socket_layer_updated', {'own': True}) == 'debug'
    assert L.level_for('socket_layer_updated', {'own': False}) == 'info'
    # The ones the audit keeps in view.
    assert L.level_for('socket_layer_updated_suppressed_during_restore') == 'info'
    assert L.level_for('socket_project_replaced_held_by_guide') == 'info'
    assert L.level_for('add_layer') == 'info'
    assert L.level_for('anything', {'_lvl': 'warn'}) == 'warn'


def test_areas():
    assert L.area_for('stage3d_edit') == '3d'
    assert L.area_for('idm_phone_page') == 'phone'
    assert L.area_for('export_binder_start') == 'binder'
    assert L.area_for('processor_update') == 'processor'
    assert L.area_for('socket_project_data_skipped') == 'sync'
    assert L.area_for('ui_click') == 'app'
    assert L.area_for('whatever', {'_area': 'power'}) == 'power'
    # A screen edit belongs where the fields it changed are.
    assert L.area_for('update_layer', {'diff': {'dataFlowLabelSize': [1, 2]}}) == 'data'
    assert L.area_for('update_layer', {'diff': {'powerVoltage': [208, 120]}}) == 'power'
    assert L.area_for('update_layer', {'diff': {'riggingBars': 'x'}}) == 'rigging'
    assert L.area_for('update_layer', {'diff': {'stage3d.x': [1, 2]}}) == '3d'
    assert L.area_for('update_layer', {'diff': {'offset_x': [1, 2]}}) == 'pixelmap'
    assert set(L.AREAS) >= {a for _, a in L._AREA_PREFIXES}


# ── messages ─────────────────────────────────────────────────────────────

def test_a_screen_edit_reads_as_what_the_person_did():
    msg = L.message('update_layer', {'id': 2, 'name': 'STAGE LEFT', 'label': 'Change Data Flow Label Size',
                                     'diff': {'dataFlowLabelSize': [47, 48]}})
    assert msg == 'Change Data Flow Label Size: STAGE LEFT (#2) dataFlowLabelSize 47 to 48'


def test_a_folded_run_says_its_steps():
    msg = L.message('ui_change', {'id': 'label-size', 'value': 48, 'from': {'value': 30},
                                  'steps': 18, 'ms': 1400})
    assert msg == 'Set label-size to 48 (from 30) (18 steps, 1.4 s)'


def test_sync_folds_read_as_one_line():
    msg = L.message('sync_echoes_folded', {'counts': {
        'socket_layer_updated_suppressed_same_copy': 12, 'socket_layer_updated_held_for_gesture': 2}})
    assert msg == 'sync: 14 echoes settled (12 same copy, 2 held for a gesture)'


def test_undo_names_what_it_put_back():
    msg = L.message('undo', {'action': 'Move Screen', 'changed': {
        'layers': [{'id': 2, 'name': 'SL', 'keys': ['offset_x', 'offset_y']}], 'added': [], 'removed': [], 'project': []}})
    assert msg == 'Undo Move Screen: SL (offset_x, offset_y)'


def test_generic_messages_and_no_dashes():
    msg = L.message('dock_clear', {'layerId': 3, 'ports': [1, 2], 'page': 'A', 'browser': 'Chrome 131'})
    assert msg == 'dock clear: layerId=3, ports=[1, 2]'
    assert '\u2014' not in L.message('x', {'_msg': 'a \u2014 b'})
    assert L.message('x', {'_msg': 'given'}) == 'given'


def test_normalize_fills_an_older_line():
    entry = {'timestamp': '2026-11-01 10:00:00', 'source': 'client', 'action': 'toast_error',
             'details': {'message': 'Nope'}}
    L.normalize(entry)
    assert (entry['lvl'], entry['area'], entry['msg']) == ('warn', 'app', 'Error shown: Nope')


def test_mentions_layer():
    assert L.mentions_layer({'details': {'layerId': 3}}, '3')
    assert L.mentions_layer({'details': {'ids': [1, 3]}}, 3)
    assert not L.mentions_layer({'details': {'layerId': 4}}, '3')
    assert not L.mentions_layer({'area': 'processor', 'details': {'id': 3}}, '3')


# ── redaction for a bug report ───────────────────────────────────────────

def test_redaction_masks_contacts_addresses_and_user_names():
    text = (r'C:\Users\Sam Lee\Shows\a.lrd /Users/alex/b.lrd /home/kim/c bob@example.com '
            r'10.0.0.42 (555) 123-4567 555-123-4567 +44 20 7946 0958')
    got = L.redact_text(text)
    for gone in ('Sam Lee', 'alex', 'kim', 'bob@example.com', '10.0.0.42', '123-4567', '7946'):
        assert gone not in got, got
    assert r'C:\Users\<user>\Shows' in got and '<email>' in got and '<ip>' in got and '<phone>' in got


def test_redaction_leaves_dates_sizes_and_versions():
    text = '2026-11-18 14:02:11.482 1920x1080 v1.7.0 port 12 of 20 3840x2160 1.7.0-beta.7'
    assert L.redact_text(text) == text


def test_redaction_hides_contact_fields_whole():
    got = L.redact({'details': {'projectManagerName': 'Pat', 'id': 'export-binder-pm-name', 'value': 'Pat Smith',
                                'email': 'x', 'name': 'Screen 1'}})
    assert got['details']['projectManagerName'] == '[hidden]'
    assert got['details']['email'] == '[hidden]'
    assert got['details']['name'] == 'Screen 1'
    assert got['details']['value'] == '[hidden]'
    for field in ('export-binder-pm-phone', 'export-binder-pm-email'):
        assert L.redact({'id': field, 'value': '5551234567'})['value'] == '[hidden]'
    assert L.redact({'id': 'label-size', 'value': '48'})['value'] == '48'
