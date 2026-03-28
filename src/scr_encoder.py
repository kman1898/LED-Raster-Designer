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
FOOTER = bytes(
    b'\xea\x03\xe7\x00' + b'\x00' * 128 +
    b'\x01\x00\x01\x00\x01\xe4' + b'\x00' * 35
)  # 173 bytes exactly


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

    # Check if origin panel (0,0) is hidden — set pre-record flag
    origin_hidden = False
    if port_assignments:
        for a in port_assignments:
            if a.get('col') == 0 and a.get('row') == 0 and a.get('hidden', False):
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
    records = bytearray()
    for col in range(cols):
        for row in range(rows):
            if col == 0 and row == 0:
                continue
            rec = bytearray(17)
            struct.pack_into('<HH', rec, 0, pw, ph)
            rec[4] = 1

            if (col, row) in hidden_set:
                # Hidden/blank panel: b5=0xFF, b6=1, b7=1
                rec[5] = 0xFF
                rec[6] = 1
                rec[7] = 1
            else:
                a = assign_map.get((col, row), {'port_num': 1, 'chain_order': 0, 'b5': 0})
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

    # Native format: section size = 25 + active_panels*17
    # Hidden panels are excluded entirely from the binary — NovaStar does not
    # use inactive-panel sentinels in multi-screen format.
    # (10-byte StandardScreen header + 4-byte marker + active_panels*17 records + 11-byte suffix)
    def _count_active(s):
        pmap = {(p['col'], p['row']): p for p in s.get('panels', [])}
        return sum(
            1 for col in range(s['cols']) for row in range(s['rows'])
            if not pmap.get((col, row), {}).get('hidden', False)
        )

    section_sizes = [25 + _count_active(s) * 17 for s in screens_list]

    total_sections = sum(section_sizes)

    # Transition: pw(2) + ph(2) + 01 + json_len(2) + json
    last_screen = screens_list[-1]
    transition = struct.pack('<HH', last_screen['pw'], last_screen['ph'])
    transition += bytes([0x01])
    transition += struct.pack('<H', len(json_data)) + json_data

    # Pre-record: 2 zero bytes + screen_count(1) + N×4-byte section sizes (u32LE each)
    # This places sections at 0x138 + 3 + N*4 = 0x13B + N*4 (matches native files)
    prerec = bytearray(3 + num_screens * 4)
    prerec[2] = num_screens
    for s_idx, sz in enumerate(section_sizes):
        struct.pack_into('<I', prerec, 3 + s_idx * 4, sz)

    sections_start = 0x138 + len(prerec)  # = 0x13B + N*4
    fsize = sections_start + total_sections + len(transition) + len(FOOTER)
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

        # Format A marker
        marker = b'\xff\x01\x01\x00'

        # Write records for active (non-hidden) panels only, in column-major order.
        # Hidden panels are excluded entirely — NovaStar has no hidden-panel sentinel
        # in multi-screen format and will reject files that include inactive records.
        records = bytearray()
        chain_counter = 0
        for col in range(cols):
            for row in range(rows):
                p = panel_map.get((col, row), {})
                if p.get('hidden', False):
                    continue  # skip hidden panels entirely
                rec = bytearray(17)
                struct.pack_into('<H', rec, 0, screen_x + col * pw)
                struct.pack_into('<H', rec, 2, screen_y + row * ph)
                struct.pack_into('<H', rec, 4, col)
                struct.pack_into('<H', rec, 6, row)
                struct.pack_into('<H', rec, 8, pw)
                struct.pack_into('<H', rec, 10, ph)
                rec[12] = 0x01
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
                is_hidden = pa.get('hidden', False) or app_port == 0

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
