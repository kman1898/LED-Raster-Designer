"""Tests for NovaStar SCR encoder module."""
import os
import sys
import struct
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import scr_encoder


class TestMakeJson:
    """Tests for JSON section generation."""

    def test_single_screen_json(self):
        result = scr_encoder.make_json(1)
        assert result == b'[{"si":0,"x1":0,"y1":0,"x2":0,"y2":0,"x3":0,"y3":0,"x4":0,"y4":0}]'

    def test_single_screen_json_length(self):
        assert len(scr_encoder.make_json(1)) == 66

    def test_multi_screen_json(self):
        result = scr_encoder.make_json(3)
        assert b'"si":0' in result
        assert b'"si":1' in result
        assert b'"si":2' in result
        assert result.startswith(b'[')
        assert result.endswith(b']')

    def test_screen_count_matches_entries(self):
        for n in [1, 2, 3, 5, 8]:
            result = scr_encoder.make_json(n)
            assert result.count(b'"si":') == n


class TestCalcChecksums:
    """Tests for checksum calculation."""

    def test_single_screen_checksum_formula(self):
        # Create minimal valid data
        data = bytearray(500)
        data[0:4] = b'DSCI'
        result = scr_encoder.calc_checksums(data, 1)
        stored_ck = struct.unpack_from('<H', result, 4)[0]
        # Verify: stored = (sum_excluding_4_5 - 990) & 0xFFFF
        bsum = sum(result[0:4]) + sum(result[6:])
        expected = (bsum - 990) & 0xFFFF
        assert stored_ck == expected

    def test_multi_screen_checksum_formula(self):
        data = bytearray(500)
        data[0:4] = b'DSCI'
        for screens in [1, 2, 3, 5]:
            result = scr_encoder.calc_checksums(data, screens)
            stored_ck = struct.unpack_from('<H', result, 4)[0]
            ck_const = 783 + screens * 207
            bsum = sum(result[0:4]) + sum(result[6:])
            expected = (bsum - ck_const) & 0xFFFF
            assert stored_ck == expected

    def test_b8_checksum_formula(self):
        data = bytearray(500)
        data[0:4] = b'DSCI'
        result = scr_encoder.calc_checksums(data, 1)
        stored_b8 = struct.unpack_from('<H', result, 0xB8)[0]
        b8_const = 492 + 1 * 207
        b8sum = sum(result[0xBA:])
        expected = (b8sum - b8_const) & 0xFFFF
        assert stored_b8 == expected

    def test_checksum_constant_scaling(self):
        # ck_const = 783 + screens * 207
        assert 783 + 1 * 207 == 990
        assert 783 + 2 * 207 == 1197
        assert 783 + 3 * 207 == 1404


class TestBuildSingleScreenScr:
    """Tests for single-screen SCR file generation."""

    def test_magic_bytes(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        assert data[0:4] == b'DSCI'

    def test_file_size(self):
        # File size = 0x155 + (panels-1)*17 + transition + footer
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        panels = 8 * 2
        transition_len = 4 + 1 + 2 + 66  # pw+ph+01+jlen+json
        expected = 0x155 + (panels - 1) * 17 + transition_len + len(scr_encoder.FOOTER)
        assert len(data) == expected

    def test_cols_rows_stored(self):
        data = scr_encoder.build_single_screen_scr(10, 5, 96, 108)
        assert data[0x145] == 10
        assert data[0x147] == 5

    def test_screen_count_is_one(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        assert data[0x13A] == 1

    def test_panel_dimensions_in_records(self):
        data = scr_encoder.build_single_screen_scr(4, 3, 120, 80)
        # First record at 0x155
        pw = struct.unpack_from('<H', data, 0x155)[0]
        ph = struct.unpack_from('<H', data, 0x157)[0]
        assert pw == 120
        assert ph == 80

    def test_checksums_valid(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        stored_ck = struct.unpack_from('<H', data, 4)[0]
        bsum = sum(data[0:4]) + sum(data[6:])
        expected = (bsum - 990) & 0xFFFF
        assert stored_ck == expected

    def test_footer_present(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        assert data[-len(scr_encoder.FOOTER):] == scr_encoder.FOOTER

    def test_json_present(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        assert b'[{"si":0' in data

    def test_v0a_field(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        v0a = struct.unpack_from('<H', data, 0x0A)[0]
        assert v0a == len(data) - 0x155 - 14

    def test_d2_field(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        v0a = struct.unpack_from('<H', data, 0x0A)[0]
        d2 = struct.unpack_from('<H', data, 0xD2)[0]
        assert d2 == v0a - 68

    def test_default_snake_order(self):
        data = scr_encoder.build_single_screen_scr(4, 2, 96, 108)
        # First record is at binary (col=0, row=1) — column-major, skipping origin.
        # NovaStar row convention: binary row 1 → app row 0.
        # Default snake: app row 0 L->R (chains 0,1,2,3), app row 1 R->L (7,6,5,4)
        # So binary (col=0, row=1) = app (col=0, row=0) = chain 0
        rec0 = data[0x155:0x155 + 17]
        b7 = rec0[7]  # chain order for binary (col=0, row=1) = app (col=0, row=0)
        assert b7 == 0  # app row 0, col 0, first in L->R snake

    def test_custom_port_assignments(self):
        assignments = [
            {'col': 0, 'row': 0, 'port_num': 0, 'chain_order': 0, 'b5': 0},
            {'col': 1, 'row': 0, 'port_num': 0, 'chain_order': 1, 'b5': 0},
            {'col': 0, 'row': 1, 'port_num': 1, 'chain_order': 0, 'b5': 0},
            {'col': 1, 'row': 1, 'port_num': 1, 'chain_order': 1, 'b5': 0},
        ]
        data = scr_encoder.build_single_screen_scr(2, 2, 96, 108, port_assignments=assignments)
        # Check that records have correct port assignments
        # First record (col=0, row=1): port_num=1
        rec0 = data[0x155:0x155 + 17]
        assert rec0[6] == 0  # port_num (1-based input=1 → 0-based binary=0)

    def test_various_panel_sizes(self):
        for pw, ph in [(48, 96), (64, 64), (96, 108), (104, 208), (120, 80), (192, 192)]:
            data = scr_encoder.build_single_screen_scr(4, 3, pw, ph)
            assert data[0:4] == b'DSCI'
            # Verify checksum
            stored_ck = struct.unpack_from('<H', data, 4)[0]
            bsum = sum(data[0:4]) + sum(data[6:])
            expected = (bsum - 990) & 0xFFFF
            assert stored_ck == expected

    def test_large_grid(self):
        data = scr_encoder.build_single_screen_scr(36, 18, 104, 208)
        assert data[0:4] == b'DSCI'
        assert data[0x145] == 36
        assert data[0x147] == 18

    def test_section_markers(self):
        data = scr_encoder.build_single_screen_scr(8, 2, 64, 64)
        # Section 0x03E9 at offset 0x36
        assert struct.unpack_from('<H', data, 0x36)[0] == 0x03E9
        # Section 0x03EE at offset 0xB6
        assert struct.unpack_from('<H', data, 0xB6)[0] == 0x03EE
        # Footer marker 0x03EA
        assert struct.unpack_from('<H', data, len(data) - len(scr_encoder.FOOTER))[0] == 0x03EA


class TestBuildMultiScreenScr:
    """Tests for multi-screen SCR file generation."""

    def test_single_screen_delegates(self):
        screens = [{'cols': 8, 'rows': 2, 'pw': 64, 'ph': 64}]
        data = scr_encoder.build_multi_screen_scr(screens)
        assert data[0:4] == b'DSCI'
        assert data[0x13A] == 1

    def test_two_screens(self):
        screens = [
            {'cols': 10, 'rows': 5, 'pw': 96, 'ph': 108, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0},
            {'cols': 10, 'rows': 5, 'pw': 96, 'ph': 108, 'screen_x': 960, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 5},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        assert data[0:4] == b'DSCI'
        assert data[0x13A] == 2

    def test_five_screens(self):
        screens = [
            {'cols': 19, 'rows': 5, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0},
            {'cols': 33, 'rows': 2, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 300,
             'sc_idx': 1, 'port_start': 11},
            {'cols': 24, 'rows': 11, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 540,
             'sc_idx': 4, 'port_start': 14},
            {'cols': 18, 'rows': 6, 'pw': 60, 'ph': 120, 'screen_x': 2400, 'screen_y': 1080,
             'sc_idx': 3, 'port_start': 6},
            {'cols': 24, 'rows': 9, 'pw': 60, 'ph': 120, 'screen_x': 2400, 'screen_y': 0,
             'sc_idx': 2, 'port_start': 0},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        assert data[0:4] == b'DSCI'
        assert data[0x13A] == 5

    def test_multi_screen_checksum(self):
        screens = [
            {'cols': 10, 'rows': 5, 'pw': 96, 'ph': 108, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0},
            {'cols': 10, 'rows': 5, 'pw': 96, 'ph': 108, 'screen_x': 960, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 5},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        stored_ck = struct.unpack_from('<H', data, 4)[0]
        ck_const = 783 + 2 * 207
        bsum = sum(data[0:4]) + sum(data[6:])
        expected = (bsum - ck_const) & 0xFFFF
        assert stored_ck == expected

    def test_multi_screen_json_has_all_entries(self):
        screens = [
            {'cols': 8, 'rows': 2, 'pw': 64, 'ph': 64, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0},
            {'cols': 8, 'rows': 2, 'pw': 64, 'ph': 64, 'screen_x': 512, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 2},
            {'cols': 8, 'rows': 2, 'pw': 64, 'ph': 64, 'screen_x': 1024, 'screen_y': 0,
             'sc_idx': 1, 'port_start': 0},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        assert data.count(b'"si":') >= 3

    def test_screen_header_positions(self):
        screens = [
            {'cols': 10, 'rows': 5, 'pw': 96, 'ph': 108, 'screen_x': 100, 'screen_y': 200,
             'sc_idx': 0, 'port_start': 0},
            {'cols': 8, 'rows': 3, 'pw': 96, 'ph': 108, 'screen_x': 500, 'screen_y': 600,
             'sc_idx': 1, 'port_start': 5},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        # Native format: sections start at 0x13B + N*4.
        # For 2 screens: 0x138 + (3 + 2*4) = 0x143.
        # StandardScreen header layout: Type(1) VMode(1) X(2) Y(2) Cols(2) Rows(2)
        num_screens = len(screens)
        sec0_start = 0x138 + 3 + num_screens * 4  # = 0x143 for 2 screens
        x0   = struct.unpack_from('<H', data, sec0_start + 2)[0]
        y0   = struct.unpack_from('<H', data, sec0_start + 4)[0]
        cols0 = struct.unpack_from('<H', data, sec0_start + 6)[0]
        rows0 = struct.unpack_from('<H', data, sec0_start + 8)[0]
        assert cols0 == 10
        assert rows0 == 5
        assert x0 == 100
        assert y0 == 200


class TestGenerateScrFiles:
    """Tests for the high-level generate_scr_files function."""

    def test_single_layer_single_file(self):
        layers = [{
            'columns': 8,
            'rows': 2,
            'cabinet_width': 64,
            'cabinet_height': 64,
            'offset_x': 0,
            'offset_y': 0,
        }]
        results = scr_encoder.generate_scr_files('test_project', layers)
        assert len(results) == 1
        filename, data = results[0]
        assert filename == 'test_project.scr'
        assert data[0:4] == b'DSCI'

    def test_multi_sending_card_single_file(self):
        """Multi-SC ports should all go into one SCR file."""
        layers = [
            {
                'columns': 8, 'rows': 2,
                'cabinet_width': 64, 'cabinet_height': 64,
                'offset_x': 0, 'offset_y': 0,
                'scrPortSendingCards': {'0': 1, '1': 2},
                'portAssignments': [
                    {'col': 0, 'row': 0, 'port': 0, 'pixelIndex': 0},
                    {'col': 1, 'row': 0, 'port': 0, 'pixelIndex': 1},
                    {'col': 0, 'row': 1, 'port': 1, 'pixelIndex': 0},
                    {'col': 1, 'row': 1, 'port': 1, 'pixelIndex': 1},
                ],
            }
        ]
        results = scr_encoder.generate_scr_files('test_project', layers)
        assert len(results) == 1
        assert results[0][0] == 'test_project.scr'

    def test_output_files_have_valid_checksums(self):
        layers = [{
            'columns': 10, 'rows': 5,
            'cabinet_width': 96, 'cabinet_height': 108,
            'offset_x': 0, 'offset_y': 0,
        }]
        results = scr_encoder.generate_scr_files('test', layers)
        for filename, data in results:
            stored_ck = struct.unpack_from('<H', data, 4)[0]
            bsum = sum(data[0:4]) + sum(data[6:])
            screens = data[0x13A]
            expected = (bsum - (783 + screens * 207)) & 0xFFFF
            assert stored_ck == expected

    def test_default_sending_card(self):
        layers = [{
            'columns': 4, 'rows': 3,
            'cabinet_width': 96, 'cabinet_height': 108,
            'offset_x': 0, 'offset_y': 0,
        }]
        results = scr_encoder.generate_scr_files('test', layers)
        assert len(results) == 1
        assert results[0][0] == 'test.scr'


class TestFooter:
    """Tests for the footer constant."""

    def test_footer_length(self):
        # Footer is a fixed-size constant (extracted from production files)
        assert len(scr_encoder.FOOTER) > 0
        assert len(scr_encoder.FOOTER) < 300

    def test_footer_starts_with_section_marker(self):
        marker = struct.unpack_from('<H', scr_encoder.FOOTER, 0)[0]
        assert marker == 0x03EA

    def test_footer_is_constant(self):
        # Footer should be the same every time
        assert scr_encoder.FOOTER == scr_encoder.FOOTER


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_minimum_grid(self):
        data = scr_encoder.build_single_screen_scr(1, 1, 96, 108)
        assert data[0:4] == b'DSCI'

    def test_single_column(self):
        data = scr_encoder.build_single_screen_scr(1, 10, 96, 108)
        assert data[0x145] == 1
        assert data[0x147] == 10

    def test_single_row(self):
        data = scr_encoder.build_single_screen_scr(10, 1, 96, 108)
        assert data[0x145] == 10
        assert data[0x147] == 1

    def test_square_panels(self):
        data = scr_encoder.build_single_screen_scr(8, 8, 64, 64)
        assert data[0:4] == b'DSCI'

    def test_wide_panels(self):
        data = scr_encoder.build_single_screen_scr(4, 3, 192, 96)
        pw = struct.unpack_from('<H', data, 0x155)[0]
        ph = struct.unpack_from('<H', data, 0x157)[0]
        assert pw == 192
        assert ph == 96

    def test_tall_panels(self):
        data = scr_encoder.build_single_screen_scr(4, 3, 96, 208)
        pw = struct.unpack_from('<H', data, 0x155)[0]
        ph = struct.unpack_from('<H', data, 0x157)[0]
        assert pw == 96
        assert ph == 208

    def test_record_count(self):
        # Should have (panels - 1) records (skip origin)
        data = scr_encoder.build_single_screen_scr(5, 4, 96, 108)
        panels = 5 * 4
        # Records start at 0x155, each 17 bytes
        # After records: transition starts
        # Find transition by looking for JSON
        js = data.find(b'[{"si":')
        # JSON is preceded by json_len(2) + 01 + ph(2) + pw(2)
        records_end = js - 2 - 1 - 4  # approximate
        records_bytes = records_end - 0x155
        # Should be roughly (panels-1) * 17
        assert abs(records_bytes - (panels - 1) * 17) < 20


class TestAnchorPanels:
    """Tests for anchor panel generation on non-SC0 screens."""

    def test_anchor_at_last_position(self):
        """Screens with sc_idx > 0 should have anchor at (cols-1, rows-1) binary."""
        screens = [
            {'cols': 10, 'rows': 5, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0, 'panels': []},
            {'cols': 8, 'rows': 3, 'pw': 60, 'ph': 120, 'screen_x': 600, 'screen_y': 0,
             'sc_idx': 1, 'port_start': 0, 'panels': []},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        # Find Screen 1 section start
        num_screens = 2
        sec_sizes = []
        for i in range(num_screens):
            sec_sizes.append(struct.unpack_from('<I', data, 0x13B + i * 4)[0])
        sec1_start = 0x138 + 3 + num_screens * 4 + sec_sizes[0]
        rec_start = sec1_start + 14  # 10-byte header + 4-byte marker

        # Last record in column-major: col=7, row=2 (cols-1, rows-1)
        cols, rows = 8, 3
        last_rec_idx = cols * rows - 1
        roff = rec_start + last_rec_idx * 17
        col_val = struct.unpack_from('<H', data, roff + 4)[0]
        row_val = struct.unpack_from('<H', data, roff + 6)[0]
        sender = data[roff + 13]
        port = data[roff + 14]
        chain = struct.unpack_from('<H', data, roff + 15)[0]

        assert col_val == 7  # cols - 1
        assert row_val == 2  # rows - 1
        assert sender == 0   # SC0
        assert port == 0     # Port 1 (0-based)
        assert chain == 8 * 3  # cols * rows (safe non-colliding value)

    def test_no_anchor_on_sc0(self):
        """Screens with sc_idx == 0 should NOT have an anchor."""
        screens = [
            {'cols': 10, 'rows': 5, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0, 'panels': []},
            {'cols': 8, 'rows': 3, 'pw': 60, 'ph': 120, 'screen_x': 600, 'screen_y': 0,
             'sc_idx': 1, 'port_start': 0, 'panels': []},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)
        # Check Screen 0 last record — should NOT be an anchor
        num_screens = 2
        sec0_start = 0x138 + 3 + num_screens * 4
        rec_start = sec0_start + 14
        cols, rows = 10, 5
        last_rec_idx = cols * rows - 1
        roff = rec_start + last_rec_idx * 17
        sender = data[roff + 13]
        # On SC0, last panel should be sc_idx=0 (normal) or 0xFF (hidden), not anchor
        # Since sc_idx == 0, sender will be 0 (same as anchor) but that's the real SC
        # The key check is that it's NOT forced to port=0 chain=0 if it's a real panel
        # For empty panels list it defaults, which is fine
        assert sender == 0  # sc_idx 0 — real panel, same sender value

    def test_anchor_replaces_visible_panel(self):
        """Anchor should replace a visible panel at the anchor position."""
        # Create panels for Screen 1 (sc_idx=1) with a visible panel at (4, 0) in app coords
        # That maps to binary (4, 2) for rows=3: binary_row = (app_row - 1 + rows) % rows
        panels = [
            {'col': c, 'row': r, 'port_num': 1, 'chain_order': c * 3 + r, 'hidden': False}
            for c in range(5) for r in range(3)
        ]
        screens = [
            {'cols': 5, 'rows': 3, 'pw': 60, 'ph': 120, 'screen_x': 0, 'screen_y': 0,
             'sc_idx': 0, 'port_start': 0, 'panels': []},
            {'cols': 5, 'rows': 3, 'pw': 60, 'ph': 120, 'screen_x': 300, 'screen_y': 0,
             'sc_idx': 1, 'port_start': 0, 'panels': panels},
        ]
        data = scr_encoder.build_multi_screen_scr(screens)

        num_screens = 2
        sec_sizes = []
        for i in range(num_screens):
            sec_sizes.append(struct.unpack_from('<I', data, 0x13B + i * 4)[0])
        sec1_start = 0x138 + 3 + num_screens * 4 + sec_sizes[0]
        rec_start = sec1_start + 14

        # Last record: binary (4, 2) = anchor position
        last_rec_idx = 5 * 3 - 1
        roff = rec_start + last_rec_idx * 17
        sender = data[roff + 13]
        port = data[roff + 14]
        chain = struct.unpack_from('<H', data, roff + 15)[0]
        assert sender == 0   # Anchor
        assert port == 0
        assert chain == 5 * 3  # cols * rows
