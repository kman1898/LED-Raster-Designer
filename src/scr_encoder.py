"""
NovaStar SCR File Encoder
Generates .scr binary files for NovaStar VPU/SmartLCT sending card configuration.

Supports single-screen and multi-screen files with multiple sending cards.
Reverse-engineered format verified against 12+ production files.

Checksum formulas:
- Main (bytes 4-5): (sum_all_bytes_except_4_5 - (783 + screens*207)) & 0xFFFF
- B8 (bytes 0xB8-0xB9): (sum_from_0xBA - (492 + screens*207)) & 0xFFFF

File structure:
- Header: 0x000-0x035 (DSCI magic, checksums, section markers)
- Section 0x03E9: 0x036-0x0B3 (config)
- Section 0x03EE: 0x0B4-0x137 (sub-checksum, derived fields)
- Pre-record: 0x138+ (screen count, section size table)
- Per-screen sections: 10-byte header + 4-byte marker + cols*rows*17 records + 11-byte suffix
- Transition: json_len(2) + json  (NO pw/ph/flag prefix)
- Footer: 173 + (N-1)*40 bytes, N = num_screens; header bytes [2:4] = N*0xE7 as LE uint16

v0a formula (header[0x0A] size field): fsize - footer_size - 182
sec2[0xD2] field: v0a - len(transition)
"""
import struct
import io
import zipfile


# 173-byte footer for single-screen files
FOOTER = bytes(
    b'\xea\x03\xe7\x00' + b'\x00' * 128 +
    b'\x01\x00\x01\x00\x01\xe4' + b'\x00' * 35
)  # 173 bytes exactly


def make_footer(num_screens):
    """
    Build the variable-length footer for the given number of screens.

    Footer structure (verified from native NovaStar files):
    - 4 bytes: EA 03 + (num_screens * 0xE7 as LE uint16)
    - 128 zeros
    - Block 0: [num_screens, 00, 01, 00, 01, E4] + 36 zeros (or 35 if N==1)
    - Blocks 1..N-1: [01, 00, 01, E4] + 36 zeros (35 for last block)

    Total size = 173 + (num_screens - 1) * 40 bytes
    """
    footer = bytearray()
    # 4-byte header: EA 03 + (N * 0xE7) as LE uint16
    footer += b'\xea\x03'
    footer += struct.pack('<H', num_screens * 0xE7)
    # 128 zeros
    footer += b'\x00' * 128
    # Block 0: [N, 00, 01, 00, 01, E4] + trailing zeros
    footer += bytes([num_screens, 0x00, 0x01, 0x00, 0x01, 0xE4])
    if num_screens == 1:
        footer += b'\x00' * 35  # single-screen: 35 trailing zeros
    else:
        footer += b'\x00' * 36  # multi-screen block 0: 36 zeros before next block
        # Additional blocks (1 per extra screen)
        for i in range(1, num_screens):
            footer += b'\x01\x00\x01\xe4'
            if i == num_screens - 1:
                footer += b'\x00' * 35  # last block: 35 trailing zeros
            else:
                footer += b'\x00' * 36  # intermediate blocks: 36 zeros
    return bytes(footer)


def make_json(screens):
    """Build the JSON section for the given number of screens."""
    entries = ','.join(
        '{{"si":{},"x1":0,"y1":0,"x2":0,"y2":0,"x3":0,"y3":0,"x4":0,"y4":0}}'.format(i)
        for i in range(screens)
    )
    return '[{}]'.format(entries).encode('ascii')


def calc_checksums(data, screens):
    """Calculate and write both checksums into the data."""
    ck_const = 783 + screens * 207
    b8_const = 492 + screens * 207

    data = bytearray(data)
    data[0xB8] = 0
    data[0xB9] = 0
    b8 = (sum(data[0xBA:]) - b8_const) & 0xFFFF
    struct.pack_into('<H', data, 0xB8, b8)
    data[4] = 0
    data[5] = 0
    ck = (sum(data[0:4]) + sum(data[6:]) - ck_const) & 0xFFFF
    struct.pack_into('<H', data, 4, ck)
    return bytes(data)


def build_single_screen_scr(cols, rows, pw, ph, port_assignments=None):
    """
    Build a single-screen SCR file from scratch.

    Args:
        cols: number of columns
        rows: number of rows
        pw: panel width in pixels
        ph: panel height in pixels
        port_assignments: list of dicts with keys:
            col, row, port_num, chain_order, b5 (0=normal, 1=return start, 255=continuation)
            If None, uses default horizontal snake on port 0.

    Returns:
        bytes: complete SCR file
    """
    screens = 1
    panels = cols * rows
    json_data = make_json(screens)

    # Transition: pw(2) + ph(2) + 01 + json_len(2) + json
    transition = struct.pack('<HH', pw, ph) + bytes([0x01])
    transition += struct.pack('<H', len(json_data)) + json_data

    fsize = 0x155 + (panels - 1) * 17 + len(transition) + len(FOOTER)
    v0a = fsize - 0x155 - 14

    # Header (0x00-0x35)
    header = bytearray(0x36)
    header[0:4] = b'DSCI'
    header[6] = 0x80
    header[0x0E] = 0xAD
    struct.pack_into('<H', header, 0x0A, v0a)

    # Section 0x03E9 (0x36-0xB3)
    sec1 = bytearray(0xB4 - 0x36)
    struct.pack_into('<H', sec1, 0, 0x03E9)
    sec1[2] = 0xE2
    sec1[4] = 0x01
    sec1[5] = 0x01
    sec1[6] = 0xC0
    sec1[7] = 0x06
    sec1[8] = 0x16
    sec1[9] = 0x04

    # Section 0x03EE (0xB4-0x137)
    sec2 = bytearray(0x138 - 0xB4)
    struct.pack_into('<H', sec2, 2, 0x03EE)
    struct.pack_into('<H', sec2, 0xD2 - 0xB4, v0a - 68)

    # Pre-record (0x138-0x154)
    prerec = bytearray(0x155 - 0x138)
    prerec[2] = screens
    struct.pack_into('<H', prerec, 3, v0a - 205)
    prerec[6] = 0x00
    prerec[7] = 0x01
    prerec[0x145 - 0x138] = cols
    prerec[0x147 - 0x138] = rows

    # Check if the panel at binary origin (0,0) is hidden — set pre-record flag.
    # Binary (0,0) corresponds to app row 1 due to NovaStar row convention.
    origin_app_row = 1 % rows if rows > 1 else 0
    origin_hidden = False
    if port_assignments:
        for a in port_assignments:
            if a.get('col') == 0 and a.get('row') == origin_app_row and a.get('hidden', False):
                origin_hidden = True
                break
    if origin_hidden:
        prerec[0x149 - 0x138] = 0xFF  # origin is blank
        prerec[0x14A - 0x138] = 0x01
        prerec[0x14B - 0x138] = 0x01

    # Default port map: horizontal snake on port 0
    if port_assignments is None:
        port_assignments = []
        order = 0
        for row in range(rows):
            if row % 2 == 0:
                col_range = range(cols)
            else:
                col_range = range(cols - 1, -1, -1)
            for col in col_range:
                port_assignments.append({
                    'col': col, 'row': row,
                    'port_num': 0, 'chain_order': order, 'b5': 0
                })
                order += 1

    # Build lookup: (col, row) -> assignment
    assign_map = {}
    for a in port_assignments:
        assign_map[(a['col'], a['row'])] = a

    # Build hidden panels set
    hidden_set = set()
    for a in port_assignments:
        if a.get('hidden', False):
            hidden_set.add((a['col'], a['row']))

    # Build records: column-major order, skip origin (0,0)
    # NovaStar row convention: app_row = (binary_row + 1) % rows
    records = bytearray()
    for col in range(cols):
        for row in range(rows):
            if col == 0 and row == 0:
                continue
            # Map binary row to app row for panel data lookup
            app_row = (row + 1) % rows
            rec = bytearray(17)
            struct.pack_into('<HH', rec, 0, pw, ph)
            rec[4] = 1

            if (col, app_row) in hidden_set:
                # Hidden/blank panel: b5=0xFF, b6=1, b7=1
                rec[5] = 0xFF
                rec[6] = 1
                rec[7] = 1
            else:
                a = assign_map.get((col, app_row), {'port_num': 1, 'chain_order': 0, 'b5': 0})
                rec[5] = a.get('b5', 0)
                rec[6] = max(0, a.get('port_num', 1) - 1)  # Convert 1-based to 0-based
                rec[7] = a.get('chain_order', 0) & 0xFF

            rec[8] = 0
            struct.pack_into('<H', rec, 9, col * pw)
            struct.pack_into('<H', rec, 11, row * ph)
            struct.pack_into('<H', rec, 13, col)
            struct.pack_into('<H', rec, 15, row)
            records += rec

    data = bytearray(header + sec1 + sec2 + prerec + records + transition + FOOTER)
    return calc_checksums(data, screens)


def build_multi_screen_scr(screens_list):
    """
    Build a multi-screen SCR file from scratch.

    Args:
        screens_list: list of screen dicts, each with:
            cols: int - number of columns
            rows: int - number of rows
            pw: int - panel width in pixels
            ph: int - panel height in pixels
            screen_x: int - screen X position in NovaStar raster
            screen_y: int - screen Y position in NovaStar raster
            sc_idx: int - sending card index (0-based)
            port_start: int - first port number on this sending card
            panels: list of panel dicts with:
                col: int, row: int,
                port_num: int, chain_order: int,
                hidden: bool (optional)

    Returns:
        bytes: complete SCR file
    """
    num_screens = len(screens_list)

    if num_screens == 1:
        s = screens_list[0]
        port_assignments = []
        for p in s.get('panels', []):
            if not p.get('hidden', False):
                port_assignments.append({
                    'col': p['col'], 'row': p['row'],
                    'port_num': p.get('port_num', 0),
                    'chain_order': p.get('chain_order', 0),
                    'b5': p.get('b5', 0),
                })
        return build_single_screen_scr(
            s['cols'], s['rows'], s['pw'], s['ph'],
            port_assignments=port_assignments if port_assignments else None
        )

    json_data = make_json(num_screens)

    # Native format: section size = 25 + cols*rows*17
    # ALL panels in the bounding box are written. Hidden/stair-step panels use
    # sender=0xFF, port=1, chain=1 as a NovaStar placeholder — they are never skipped.
    # (10-byte StandardScreen header + 4-byte marker + cols*rows*17 records + 11-byte suffix)
    section_sizes = [25 + s['cols'] * s['rows'] * 17 for s in screens_list]

    total_sections = sum(section_sizes)

    # Transition: json_len(2) + json  — NO pw/ph/flag prefix (verified from native files)
    transition = struct.pack('<H', len(json_data)) + json_data

    # Footer: variable length based on num_screens (verified from native files)
    footer = make_footer(num_screens)

    # Pre-record: 2 zero bytes + screen_count(1) + N×4-byte section sizes (u32LE each)
    # This places sections at 0x138 + 3 + N*4 = 0x13B + N*4 (matches native files)
    prerec = bytearray(3 + num_screens * 4)
    prerec[2] = num_screens
    for s_idx, sz in enumerate(section_sizes):
        struct.pack_into('<I', prerec, 3 + s_idx * 4, sz)

    sections_start = 0x138 + len(prerec)  # = 0x13B + N*4
    fsize = sections_start + total_sections + len(transition) + len(footer)
    # v0a formula: fsize - footer_size - 182 (verified from native files)
    v0a = fsize - len(footer) - 182

    # Header (0x00-0x35)
    header = bytearray(0x36)
    header[0:4] = b'DSCI'
    header[6] = 0x80
    # header[0x0E-0x0F] = footer_size as LE uint16 (verified from native files)
    struct.pack_into('<H', header, 0x0E, len(footer))
    struct.pack_into('<H', header, 0x0A, v0a)

    # Section 0x03E9 (0x36-0xB3)
    sec1 = bytearray(0xB4 - 0x36)
    struct.pack_into('<H', sec1, 0, 0x03E9)
    sec1[2] = 0xE2
    sec1[4] = 0x01
    sec1[5] = 0x01
    sec1[6] = 0xC0
    sec1[7] = 0x06
    sec1[8] = 0x16
    sec1[9] = 0x04

    # Section 0x03EE (0xB4-0x137)
    sec2 = bytearray(0x138 - 0xB4)
    struct.pack_into('<H', sec2, 2, 0x03EE)
    # sec2[0xD2] = v0a - len(transition) (verified from native: 40326 - 263 = 40063)
    struct.pack_into('<H', sec2, 0xD2 - 0xB4, v0a - len(transition))

    # Build per-screen section data
    all_screen_data = bytearray()
    for s_idx, s in enumerate(screens_list):
        cols = s['cols']
        rows = s['rows']
        pw = s['pw']
        ph = s['ph']
        screen_x = s.get('screen_x', 0)
        screen_y = s.get('screen_y', 0)
        sc_idx = s.get('sc_idx', 0)
        port_start = s.get('port_start', 0)

        # Build panel lookup: (col, row) -> panel dict
        panel_map = {}
        for p in s.get('panels', []):
            panel_map[(p['col'], p['row'])] = p

        # 10-byte StandardScreen header: Type(1) VMode(1) X(2) Y(2) Cols(2) Rows(2)
        sec_hdr = bytearray(10)
        sec_hdr[0] = 0x01  # Type
        sec_hdr[1] = 0x00  # VMode
        struct.pack_into('<H', sec_hdr, 2, screen_x)
        struct.pack_into('<H', sec_hdr, 4, screen_y)
        struct.pack_into('<H', sec_hdr, 6, cols)
        struct.pack_into('<H', sec_hdr, 8, rows)

        # Format marker: depends on sc_idx and minimum port used.
        # SC1/SC2 (sc_idx 0-1) with standard ports 0-7 → Format A (FF 01 01 00)
        # SC3+ or port >= 8 → explicit [sc_idx, min_port_0based, 00, 00]
        # Verified from native files (2026 EDC.scr).
        non_hidden_ports = [
            p.get('port_num', 1)
            for p in s.get('panels', [])
            if not p.get('hidden', False)
        ]
        min_port_0based = (min(non_hidden_ports) - 1) if non_hidden_ports else 0
        if sc_idx <= 1 and min_port_0based <= 7:
            marker = b'\xff\x01\x01\x00'  # Format A (standard)
        else:
            marker = bytes([sc_idx & 0xFF, min_port_0based & 0xFF, 0x00, 0x00])

        # Origin/anchor convention for binary position (cols-1, rows-1):
        # - Anchor screens (sc_idx > 0): sender=0, port=0, chain=cols*rows
        #   (safe value above any data chain to avoid collision)
        # - Non-anchor screens (sc_idx == 0): origin duplicate — visible with
        #   same sender/port/chain as the first data panel (chain=0).
        has_anchor = sc_idx > 0
        origin_col = cols - 1
        origin_row = rows - 1  # binary row
        anchor_chain = cols * rows  # safe: always > max data chain index

        # Find the first visible panel's port for origin duplicate
        first_port_0based = 0
        for p in sorted(s.get('panels', []), key=lambda x: x.get('chain_order', 999)):
            if not p.get('hidden', False):
                first_port_0based = (p.get('port_num', port_start + 1) - 1) & 0xFF
                break

        # Write records for ALL panels in the bounding box (column-major order).
        # Hidden/stair-step panels use sender=0xFF, port=1, chain=1 per NovaStar convention.
        # Connected panels use the normal sender/port/chain routing.
        #
        # NovaStar row convention: the binary stores rows offset by 1 from the
        # app's display.  App row 0 (display row 1) maps to binary row N-1,
        # and app rows 1..N-1 map to binary rows 0..N-2.  This is because
        # NovaLCT always displays binary row N-1 as display row 1.
        # Formula: app_row = (binary_row + 1) % rows
        records = bytearray()
        chain_counter = 0
        for col in range(cols):
            for row in range(rows):
                # Map binary row to app row for panel data lookup
                app_row = (row + 1) % rows
                rec = bytearray(17)
                struct.pack_into('<H', rec, 0, screen_x + col * pw)
                struct.pack_into('<H', rec, 2, screen_y + row * ph)
                struct.pack_into('<H', rec, 4, col)
                struct.pack_into('<H', rec, 6, row)
                struct.pack_into('<H', rec, 8, pw)
                struct.pack_into('<H', rec, 10, ph)
                rec[12] = 0x01  # Active always 1
                if col == origin_col and row == origin_row:
                    if has_anchor:
                        # Anchor panel: sender=0 (SC0), port=0 (Port 1)
                        rec[13] = 0x00  # sender=0
                        rec[14] = 0x00  # port=0 (0-based)
                        struct.pack_into('<H', rec, 15, anchor_chain)
                    else:
                        # Origin duplicate: visible, same port as first data
                        # panel, chain=0 (duplicates the cable entry)
                        rec[13] = sc_idx & 0xFF
                        rec[14] = first_port_0based
                        struct.pack_into('<H', rec, 15, 0)  # chain=0
                elif panel_map.get((col, app_row), {}).get('hidden', False):
                    # Stair-step/unconnected panel: NovaStar placeholder convention
                    rec[13] = 0xFF  # sender=255
                    rec[14] = 0x01  # port=1
                    struct.pack_into('<H', rec, 15, 1)  # chain=1
                else:
                    p = panel_map.get((col, app_row), {})
                    rec[13] = sc_idx & 0xFF
                    rec[14] = (p.get('port_num', port_start + 1) - 1) & 0xFF
                    struct.pack_into('<H', rec, 15, p.get('chain_order', chain_counter))
                    chain_counter += 1
                records += rec

        # 11-byte suffix (zeros)
        suffix = bytes(11)

        all_screen_data += bytes(sec_hdr) + marker + records + suffix

    # Assemble file
    data = bytearray(header + sec1 + sec2 + prerec + all_screen_data
                     + transition + footer)

    return calc_checksums(data, num_screens)


def generate_scr_files(project_name, layers):
    """
    Generate SCR file(s) from layer data.

    Args:
        project_name: project name for filenames
        layers: list of layer dicts with SCR configuration and port assignments

    Returns:
        list of (filename, bytes) tuples
    """
    import os as _os
    _log_dir = _os.environ.get('_LRD_LOG_DIR', _os.path.dirname(_os.path.abspath(__file__)))
    _os.makedirs(_log_dir, exist_ok=True)
    _debug_path = _os.path.join(_log_dir, 'scr_debug.log')
    with open(_debug_path, 'w', encoding='utf-8') as _dbf:
        for lyr in layers:
            _dbf.write(f"=== Layer: {lyr.get('name')} ({lyr.get('columns')}x{lyr.get('rows')}) ===\n")
            _dbf.write(f"  flowPattern={lyr.get('flowPattern', '(not sent)')}\n")
            _dbf.write(f"  scrScreenX={lyr.get('scrScreenX')} scrScreenY={lyr.get('scrScreenY')}\n")
            _dbf.write(f"  scrPortNumbers={lyr.get('scrPortNumbers', {})}\n")
            _dbf.write(f"  scrPortSendingCards={lyr.get('scrPortSendingCards', {})}\n")
            _dbf.write(f"  cabinet_width={lyr.get('cabinet_width')} cabinet_height={lyr.get('cabinet_height')}\n")
            pa_list = lyr.get('portAssignments', [])
            _dbf.write(f"  total portAssignments: {len(pa_list)}\n")
            # Group by port
            _ports = {}
            for _pa in pa_list:
                _k = _pa.get('port', 0)
                _ports.setdefault(_k, []).append(_pa)
            for _pk in sorted(_ports.keys()):
                _plist = _ports[_pk]
                _visible = [p for p in _plist if not p.get('hidden', False)]
                _first3 = [(p['col'], p['row'], p.get('hidden', False)) for p in _plist[:3]]
                _last3  = [(p['col'], p['row'], p.get('hidden', False)) for p in _plist[-3:]]
                _label = f"Port {_pk}" if _pk != 0 else "Hidden (port 0)"
                _dbf.write(f"  {_label} ({len(_plist)} panels, {len(_visible)} visible): "
                           f"first={_first3}  last={_last3}\n")
        _dbf.write("\n")
        # Log chain=0 positions and full chain sequences for binary verification
        _dbf.write("=== Chain assignments (what goes into SCR binary) ===\n")
        for lyr in layers:
            _fp = lyr.get('flowPattern', 'tl-h')
            _dbf.write(f"  Layer: {lyr.get('name')} (flowPattern={_fp})\n")
            _port_num_map = lyr.get('scrPortNumbers', {})
            _port_sc_map = lyr.get('scrPortSendingCards', {})
            # Collect ALL visible panels per port in portAssignment order
            _port_panels = {}  # nova_port -> [list of (col,row) in order]
            for _pa in lyr.get('portAssignments', []):
                _app_port = _pa.get('port', 1)
                if _pa.get('hidden', False) or _app_port == 0:
                    continue
                _nova_port = _port_num_map.get(str(_app_port), _app_port)
                _port_panels.setdefault(_nova_port, []).append((_pa['col'], _pa['row']))
            for _np in sorted(_port_panels.keys()):
                _panels = _port_panels[_np]
                _N = len(_panels)
                _sc = _port_sc_map.get(str(_np), 1)
                _c0, _r0 = _panels[0]
                _cN, _rN = _panels[-1]
                _dbf.write(f"    NovaStar port {_np} (0-based: {_np-1}, SC{_sc}): "
                           f"{_N} panels, "
                           f"chain=0 at col={_c0},row={_r0} (cable entry) -> "
                           f"chain={_N-1} at col={_cN},row={_rN} (chain end)\n")
                # Show first and last 5 chain assignments
                if _N <= 10:
                    for _ci, (_c, _r) in enumerate(_panels):
                        _dbf.write(f"      chain={_ci}: col={_c}, row={_r}\n")
                else:
                    for _ci in range(5):
                        _c, _r = _panels[_ci]
                        _dbf.write(f"      chain={_ci}: col={_c}, row={_r}\n")
                    _dbf.write(f"      ... ({_N - 10} more) ...\n")
                    for _ci in range(_N-5, _N):
                        _c, _r = _panels[_ci]
                        _dbf.write(f"      chain={_ci}: col={_c}, row={_r}\n")
        _dbf.write("\n")
        # Log origin/anchor panel info
        _dbf.write("=== Origin/Anchor info ===\n")
        for lyr in layers:
            _sc_map = lyr.get('scrPortSendingCards', {})
            _sc_nums = set(_sc_map.values()) or {1}
            _cols = lyr.get('columns', 0)
            _rows = lyr.get('rows', 0)
            for _sc in sorted(_sc_nums):
                _sc_idx = _sc - 1
                _origin_app = (_cols - 1, 0)  # app coords
                _origin_bin = (_cols - 1, _rows - 1)  # binary coords
                if _sc_idx > 0:
                    _anch_chain = _cols * _rows
                    _dbf.write(f"  Layer '{lyr.get('name')}' SC{_sc} (sc_idx={_sc_idx}): "
                               f"ANCHOR at app({_origin_app[0]},{_origin_app[1]}) "
                               f"binary({_origin_bin[0]},{_origin_bin[1]}) "
                               f"sender=0 port=0 chain={_anch_chain}\n")
                else:
                    _dbf.write(f"  Layer '{lyr.get('name')}' SC{_sc} (sc_idx={_sc_idx}): "
                               f"ORIGIN DUPLICATE at app({_origin_app[0]},{_origin_app[1]}) "
                               f"binary({_origin_bin[0]},{_origin_bin[1]}) chain=0\n")
        _dbf.write("\n")

    # Group layers by sending card
    sc_groups = {}  # sending_card_num -> list of screen dicts

    for layer in layers:
        port_sc_map = layer.get('scrPortSendingCards', {})
        port_num_map = layer.get('scrPortNumbers', {})

        # Determine which sending card(s) this layer's ports are on
        sc_numbers = set()
        for port_str, sc_num in port_sc_map.items():
            sc_numbers.add(sc_num)
        if not sc_numbers:
            sc_numbers = {1}  # default to SC1

        for sc_num in sc_numbers:
            if sc_num not in sc_groups:
                sc_groups[sc_num] = []

            # Origin/anchor position: binary (cols-1, rows-1) = app (cols-1, 0).
            # For anchor screens (sc_idx > 0): replaced by anchor in binary.
            # For non-anchor screens: origin duplicate (visible, chain=0).
            # In both cases this position is always VISIBLE in the binary.
            layer_cols = layer['columns']
            layer_rows = layer['rows']
            origin_app_col = layer_cols - 1
            origin_app_row = 0  # binary (cols-1, rows-1) -> app_row = (rows-1+1)%rows = 0
            needs_anchor = (sc_num - 1) > 0  # sc_idx > 0

            # Check if the origin position is hidden in the ORIGINAL app data
            # (before filtering).  This determines whether the anchor adds a
            # visible panel to a previously-hidden position.
            origin_hidden_in_app = True
            for pa in layer.get('portAssignments', []):
                if pa['col'] == origin_app_col and pa['row'] == origin_app_row:
                    if not pa.get('hidden', False) and pa.get('port', 0) != 0:
                        origin_hidden_in_app = False
                    break

            # Filter port assignments to only those on this sending card
            # and compute sequential chain_order per port
            # port_num in portAssignments is the app's 1-based port number
            # port_num_map maps app port -> NovaStar port number (for the binary)
            filtered_panels = []
            port_chain_counters = {}  # nova_port -> next chain index
            for pa in layer.get('portAssignments', []):
                app_port = pa.get('port', 1)  # app's 1-based port
                is_hidden = pa.get('hidden', False) or app_port == 0

                # Skip the origin/anchor position — it will be written
                # specially in the binary (anchor or origin duplicate).
                if pa['col'] == origin_app_col and pa['row'] == origin_app_row:
                    continue

                if is_hidden:
                    # Hidden panels (port=0 from JS or hidden flag set) are not
                    # routed through any real port — add them directly without
                    # touching the chain counters.
                    assigned_sc = port_sc_map.get(str(app_port), sc_num)
                    if assigned_sc == sc_num or app_port == 0:
                        filtered_panels.append({
                            'col': pa['col'],
                            'row': pa['row'],
                            'port_num': 0,
                            'chain_order': 0,
                            'hidden': True,
                            'b5': 0,
                        })
                    continue

                assigned_sc = port_sc_map.get(str(app_port), 1)
                if assigned_sc == sc_num:
                    # Map to NovaStar port number (user may have remapped)
                    nova_port = port_num_map.get(str(app_port), app_port)
                    if nova_port not in port_chain_counters:
                        # NovaStar convention: when the anchor replaces a
                        # visible data panel at the origin, chain 0 is
                        # consumed by the anchor so data starts at 1.
                        # When the origin was hidden (stairstepped area),
                        # the anchor doesn't displace data, so start at 0.
                        if needs_anchor and not origin_hidden_in_app:
                            port_chain_counters[nova_port] = 1
                        else:
                            port_chain_counters[nova_port] = 0
                    chain_idx = port_chain_counters[nova_port]
                    port_chain_counters[nova_port] += 1
                    filtered_panels.append({
                        'col': pa['col'],
                        'row': pa['row'],
                        'port_num': nova_port,  # NovaStar port number (1-based)
                        'chain_order': chain_idx,
                        'hidden': False,
                        'b5': 0,
                    })

            # ── Origin row adjustment ──
            # NovaStar convention: origin row (app row 0, binary row N-1)
            # has data shifted LEFT by 1 column from adjacent row port
            # boundaries.  Extensions fill gap columns.  No chain reversal
            # — the app's non-origin chain ordering is already correct.
            if layer_rows > 1:
                # Step 1: adjacent row (app row 1) port column ranges
                port_adj_cols = {}
                for p in filtered_panels:
                    if (p['row'] == 1 and not p.get('hidden', False)
                            and p['port_num'] > 0):
                        port_adj_cols.setdefault(p['port_num'], set()).add(
                            p['col'])
                port_adj_left = {pn: min(cs)
                                 for pn, cs in port_adj_cols.items()}

                if port_adj_left:
                    adj_sp = sorted(port_adj_left,
                                    key=lambda pn: port_adj_left[pn])
                    # Step 2: origin row boundaries (shifted left by 1)
                    obnds = []
                    for bi in range(len(adj_sp) - 1):
                        obnds.append(port_adj_left[adj_sp[bi + 1]] - 1)

                    def _oport(col):
                        pt = adj_sp[0]
                        for bi, bv in enumerate(obnds):
                            if col >= bv:
                                pt = adj_sp[bi + 1]
                        return pt

                    # Step 3: compute target origin-row DATA columns
                    # NovaStar convention: the origin row has (adj_vis - 1)
                    # data cols for non-anchor, or (adj_vis - 2) for
                    # hidden-anchor screens.  These are always the LEFTMOST
                    # `tgt` columns from the adjacent visible set (the
                    # origin row is shifted LEFT relative to adjacent).
                    adj_vc = set()
                    for p in filtered_panels:
                        if p['row'] == 1 and not p.get('hidden', False):
                            adj_vc.add(p['col'])
                    adj_vis = len(adj_vc)

                    if needs_anchor and origin_hidden_in_app:
                        tgt = adj_vis - 2
                    else:
                        tgt = adj_vis - 1

                    # Step 4: origin data cols = leftmost tgt adjacent cols
                    ori_dv = set(sorted(adj_vc)[:tgt])

                    # Step 5: assign origin cols to ports
                    p_oc = {}
                    for c in ori_dv:
                        pn = _oport(c)
                        p_oc.setdefault(pn, []).append(c)
                    for pn in p_oc:
                        p_oc[pn].sort()

                    # Step 6: rebuild chains per port
                    for port in adj_sp:
                        if port not in p_oc:
                            continue
                        new_oc = p_oc[port]
                        new_oc_set = set(new_oc)

                        # Separate origin / non-origin panels
                        old_oi = []
                        nori = []
                        for i, p in enumerate(filtered_panels):
                            if (p['port_num'] == port
                                    and not p.get('hidden', False)):
                                if p['row'] == 0:
                                    old_oi.append(i)
                                else:
                                    nori.append((i, p))
                        nori.sort(key=lambda x: x[1]['chain_order'])

                        # Mark old origin panels hidden
                        for idx in old_oi:
                            filtered_panels[idx] = dict(
                                filtered_panels[idx],
                                port_num=0, chain_order=0, hidden=True)

                        # Detect horizontal vs vertical serpentine on origin
                        horiz = False
                        if len(nori) >= 2:
                            a, b = nori[0][1], nori[1][1]
                            if (a['row'] == 1 and b['row'] == 1
                                    and a['col'] != b['col']):
                                horiz = True

                        # Build chain sequence
                        seq = []  # (existing_idx | None, col, row)
                        if horiz:
                            # Origin panels first, opposite direction of adj
                            if nori[0][1]['col'] < nori[1][1]['col']:
                                soc = sorted(new_oc, reverse=True)
                            else:
                                soc = sorted(new_oc)
                            for c in soc:
                                seq.append((None, c, 0))
                            for idx, p in nori:
                                seq.append((idx, p['col'], p['row']))
                        else:
                            # Vertical: cable entry at first_adj_col - 1
                            if nori:
                                ce_c = nori[0][1]['col'] - 1
                                if ce_c not in new_oc_set:
                                    fc = nori[0][1]['col']
                                    ce_c = min(new_oc,
                                               key=lambda c: abs(c - fc))
                            else:
                                ce_c = new_oc[0]
                            rem = [c for c in new_oc if c != ce_c]

                            seq.append((None, ce_c, 0))
                            for j, (idx, p) in enumerate(nori):
                                seq.append((idx, p['col'], p['row']))
                                if rem and p['row'] == 1:
                                    top = False
                                    if j + 1 < len(nori):
                                        nx = nori[j + 1][1]
                                        if (nx['row'] == 1
                                                and nx['col'] != p['col']):
                                            top = True
                                    elif j == len(nori) - 1:
                                        top = True
                                    if top:
                                        seq.append((None, rem.pop(0), 0))
                            for c in rem:
                                seq.append((None, c, 0))

                        # Apply chain numbers
                        ch = 0
                        if needs_anchor and not origin_hidden_in_app:
                            ch = 1
                        for eidx, col, row in seq:
                            if eidx is not None:
                                filtered_panels[eidx] = dict(
                                    filtered_panels[eidx], chain_order=ch)
                            else:
                                found = False
                                for i, p in enumerate(filtered_panels):
                                    if p['col'] == col and p['row'] == 0:
                                        filtered_panels[i] = {
                                            'col': col, 'row': 0,
                                            'port_num': port,
                                            'chain_order': ch,
                                            'hidden': False, 'b5': 0,
                                        }
                                        found = True
                                        break
                                if not found:
                                    filtered_panels.append({
                                        'col': col, 'row': 0,
                                        'port_num': port,
                                        'chain_order': ch,
                                        'hidden': False, 'b5': 0,
                                    })
                            ch += 1

            sc_groups[sc_num].append({
                'cols': layer['columns'],
                'rows': layer['rows'],
                'pw': layer['cabinet_width'],
                'ph': layer['cabinet_height'],
                'screen_x': layer.get('scrScreenX', layer.get('offset_x', 0)),
                'screen_y': layer.get('scrScreenY', layer.get('offset_y', 0)),
                'sc_idx': sc_num - 1,  # 0-based in the binary
                'port_start': 0,
                'screen_number': layer.get('scrScreenNumber', 1),
                'panels': filtered_panels,
            })

    # Combine all screens into one file, sorted by screen number
    all_screens = []
    for sc_num in sorted(sc_groups.keys()):
        all_screens.extend(sc_groups[sc_num])
    all_screens.sort(key=lambda s: s.get('screen_number', 1))

    if len(all_screens) == 1:
        scr_data = build_single_screen_scr(
            all_screens[0]['cols'], all_screens[0]['rows'],
            all_screens[0]['pw'], all_screens[0]['ph'],
            port_assignments=[{
                'col': p['col'], 'row': p['row'],
                'port_num': p['port_num'],
                'chain_order': p['chain_order'],
                'b5': p.get('b5', 0),
                'hidden': p.get('hidden', False),
            } for p in all_screens[0].get('panels', [])]
            or None
        )
    else:
        scr_data = build_multi_screen_scr(all_screens)

    filename = '{}.scr'.format(project_name)
    return [(filename, scr_data)]
