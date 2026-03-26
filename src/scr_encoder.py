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
- Pre-record: 0x138-0x154 (screen count, section size table)
- Per-screen: 42-byte header + (panels-1)*17 records (column-major, skip origin)
- Transition: pw(2) + ph(2) + 01 + json_len(2) + json
- Footer: 173 bytes (constant)
"""
import struct
import io
import zipfile


# 173-byte footer constant (identical across all known .scr files)
FOOTER = bytes.fromhex(
    'ea03e700000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000100010001e4000000000000000000'
    '000000000000000000000000000000000000000000000000'
)


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

    # Build records: column-major order, skip origin (0,0)
    records = bytearray()
    for col in range(cols):
        for row in range(rows):
            if col == 0 and row == 0:
                continue
            a = assign_map.get((col, row), {'port_num': 1, 'chain_order': 0, 'b5': 0})
            rec = bytearray(17)
            struct.pack_into('<HH', rec, 0, pw, ph)
            rec[4] = 1
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

    # Calculate section sizes
    section_sizes = []
    for s in screens_list:
        panels = s['cols'] * s['rows']
        # Section = 42 (header) + (panels-1)*17 (records) - 15 (sentinel overlap)
        section_sizes.append(42 + (panels - 1) * 17 - 15)

    total_sections = sum(section_sizes)

    # File size = 0x155 + total_sections + transition + footer
    # Transition for multi-screen: pw(2) + ph(2) + 01 + json_len(2) + json
    last_screen = screens_list[-1]
    transition = struct.pack('<HH', last_screen['pw'], last_screen['ph'])
    transition += bytes([0x01])
    transition += struct.pack('<H', len(json_data)) + json_data

    fsize = 0x155 + total_sections + len(transition) + len(FOOTER)
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
    prerec[2] = num_screens
    # Section size table: screens × (u16 size + u16 padding)
    for s_idx in range(num_screens):
        struct.pack_into('<H', prerec, 3 + s_idx * 4, section_sizes[s_idx])
    prerec[6] = 0x00
    prerec[7] = 0x01

    # Build per-screen data
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
        panels = cols * rows

        # 42-byte screen header
        hdr = bytearray(42)
        struct.pack_into('<H', hdr, 0, cols)
        struct.pack_into('<H', hdr, 2, rows)
        hdr[4] = sc_idx
        hdr[5] = port_start
        struct.pack_into('<H', hdr, 8, screen_x)
        struct.pack_into('<H', hdr, 10, screen_y)
        struct.pack_into('<H', hdr, 16, pw)
        struct.pack_into('<H', hdr, 18, ph)
        hdr[20] = 0x01
        # Second config block
        hdr[21] = sc_idx
        hdr[22] = port_start
        struct.pack_into('<H', hdr, 25, screen_x)
        struct.pack_into('<H', hdr, 27, screen_y + ph)
        hdr[31] = 0x01
        struct.pack_into('<H', hdr, 33, pw)
        struct.pack_into('<H', hdr, 35, ph)
        hdr[37] = 0x01
        hdr[38] = sc_idx
        hdr[39] = port_start

        # Build panel lookup
        panel_map = {}
        for p in s.get('panels', []):
            if not p.get('hidden', False):
                panel_map[(p['col'], p['row'])] = p

        # Records: column-major, skip origin (0,0), skip last record (sentinel)
        records = bytearray()
        rec_count = 0
        max_records = panels - 2  # -1 for origin skip, -1 for sentinel
        for col in range(cols):
            for row in range(rows):
                if col == 0 and row == 0:
                    continue
                if rec_count >= max_records:
                    break
                p = panel_map.get((col, row), {})
                rec = bytearray(17)
                struct.pack_into('<H', rec, 0, screen_x + col * pw)
                struct.pack_into('<H', rec, 2, screen_y + row * ph)
                rec[4] = col & 0xFF
                rec[6] = row & 0xFF
                struct.pack_into('<H', rec, 8, pw)
                struct.pack_into('<H', rec, 10, ph)
                rec[12] = 0x01
                rec[13] = sc_idx
                rec[14] = port_start
                struct.pack_into('<H', rec, 15, p.get('chain_order', 0))
                records += rec
                rec_count += 1
            if rec_count >= max_records:
                break

        all_screen_data += hdr + records

    # Assemble file
    data = bytearray(header + sec1 + sec2 + prerec + all_screen_data
                      + transition + FOOTER)

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

            # Filter port assignments to only those on this sending card
            # and compute sequential chain_order per port
            # port_num in portAssignments is the app's 1-based port number
            # port_num_map maps app port -> NovaStar port number (for the binary)
            filtered_panels = []
            port_chain_counters = {}  # nova_port -> next chain index
            for pa in layer.get('portAssignments', []):
                app_port = pa.get('port', 1)  # app's 1-based port
                assigned_sc = port_sc_map.get(str(app_port), 1)
                if assigned_sc == sc_num:
                    # Map to NovaStar port number (user may have remapped)
                    nova_port = port_num_map.get(str(app_port), app_port)
                    if nova_port not in port_chain_counters:
                        port_chain_counters[nova_port] = 0
                    chain_idx = port_chain_counters[nova_port]
                    port_chain_counters[nova_port] += 1
                    filtered_panels.append({
                        'col': pa['col'],
                        'row': pa['row'],
                        'port_num': nova_port,  # NovaStar port number (1-based)
                        'chain_order': chain_idx,
                        'hidden': pa.get('hidden', False),
                        'b5': 0,
                    })

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

    # Generate one SCR file per sending card
    results = []
    for sc_num in sorted(sc_groups.keys()):
        screens = sc_groups[sc_num]
        # Sort by screen number
        screens.sort(key=lambda s: s.get('screen_number', 1))

        if len(screens) == 1:
            scr_data = build_single_screen_scr(
                screens[0]['cols'], screens[0]['rows'],
                screens[0]['pw'], screens[0]['ph'],
                port_assignments=[{
                    'col': p['col'], 'row': p['row'],
                    'port_num': p['port_num'],
                    'chain_order': p['chain_order'],
                    'b5': p.get('b5', 0),
                } for p in screens[0].get('panels', []) if not p.get('hidden', False)]
                or None
            )
        else:
            scr_data = build_multi_screen_scr(screens)

        if len(sc_groups) == 1:
            filename = '{}.scr'.format(project_name)
        else:
            filename = '{}_SC{}.scr'.format(project_name, sc_num)

        results.append((filename, scr_data))

    return results
