"""
NovaStar SCR File Decoder
Parses .scr binary files and returns structured screen/layer data.

All real NovaStar SCR files share this structure:
  - DSCI header at offset 0
  - Screen info block at offset 0xB6:
      offset 0:   version (uint16LE)
      offset 2:   CRC (uint16LE)
      offset 132: screen count (uint8)
      offset 133: section size table (uint32LE × screen_count)
      offset 133 + screen_count×4: section data

Each section uses one of two formats, detected by bytes 10-13:
  Format A (bytes 10-13 == FF 01 01 00):
    [10-byte StandardScreen header][FF010100][records][11-byte suffix]
    overhead = 25, records start at section_offset + 14

  Format B (any other bytes 10-13):
    [10-byte StandardScreen header][records]
    overhead = 10, records start at section_offset + 10

StandardScreen header (10 bytes):
  Type(1)  VMode(1)  X(2)  Y(2)  Cols(2)  Rows(2)

17-byte panel record:
  X(2)  Y(2)  XInPort(2)  YInPort(2)  Width(2)  Height(2)
  Active(1)  Sender(1)  Port(1)  ConnectIndex(2)

All panels are present in the section (including col=0,row=0 origin).
"""

import struct

BLOCK_START = 0xB6
SCREENCOUNT_OFFSET = 132
SECTIONLEN_OFFSET = 133

RECORD_SIZE = 17
FORMAT_A_MARKER = b'\xff\x01\x01\x00'
FORMAT_A_OVERHEAD = 25   # 14-byte header + 11-byte suffix
FORMAT_B_OVERHEAD = 10   # 10-byte StandardScreen header only


def decode_scr(data: bytes) -> dict:
    """
    Decode a NovaStar SCR file.

    Returns:
        dict with key 'screens': list of screen dicts, each containing:
            screen_idx:   int
            x, y:         int  (screen position in NovaStar raster)
            cols, rows:   int  (cabinet grid dimensions)
            panel_width:  int  (dominant cabinet pixel width)
            panel_height: int  (dominant cabinet pixel height)
            panels:       list of panel dicts (see _decode_section)

    Raises ValueError for files that cannot be decoded.
    """
    if len(data) < BLOCK_START + 140:
        raise ValueError('File too small to be a valid SCR file')

    screen_count = data[BLOCK_START + SCREENCOUNT_OFFSET]
    if screen_count == 0 or screen_count > 64:
        raise ValueError(f'Unexpected screen count: {screen_count}')

    section_sizes = []
    for i in range(screen_count):
        offset = BLOCK_START + SECTIONLEN_OFFSET + i * 4
        sz = struct.unpack_from('<I', data, offset)[0]
        if sz == 0 or sz > len(data):
            raise ValueError(f'Invalid section size at screen {i}: {sz}')
        section_sizes.append(sz)

    sec_offset = BLOCK_START + SECTIONLEN_OFFSET + screen_count * 4
    screens = []

    for s_idx in range(screen_count):
        size = section_sizes[s_idx]
        if sec_offset + size > len(data):
            break
        screen = _decode_section(data, sec_offset, size, s_idx)
        if screen is not None:
            screens.append(screen)
        sec_offset += size

    if not screens:
        raise ValueError('No valid screens found in SCR file')

    return {'screen_count': screen_count, 'screens': screens}


def _decode_section(data: bytes, offset: int, size: int, s_idx: int):
    """
    Decode one screen section.

    Returns screen dict or None if the section is invalid/empty.
    """
    if size < FORMAT_B_OVERHEAD:
        return None

    # 10-byte StandardScreen header
    screen_x = struct.unpack_from('<H', data, offset + 2)[0]
    screen_y = struct.unpack_from('<H', data, offset + 4)[0]
    cols = struct.unpack_from('<H', data, offset + 6)[0]
    rows = struct.unpack_from('<H', data, offset + 8)[0]

    if cols == 0 or rows == 0 or cols > 512 or rows > 512:
        return None

    # Detect format A vs B
    if (offset + 14 <= len(data) and
            data[offset + 10:offset + 14] == FORMAT_A_MARKER):
        rec_start = offset + 14
        n_panels = (size - FORMAT_A_OVERHEAD) // RECORD_SIZE
    else:
        rec_start = offset + 10
        n_panels = (size - FORMAT_B_OVERHEAD) // RECORD_SIZE

    if n_panels <= 0:
        return None

    panels = []
    pw_counts = {}
    ph_counts = {}

    for p_idx in range(n_panels):
        off = rec_start + p_idx * RECORD_SIZE
        if off + RECORD_SIZE > len(data):
            break

        x = struct.unpack_from('<H', data, off)[0]
        y = struct.unpack_from('<H', data, off + 2)[0]
        col = struct.unpack_from('<H', data, off + 4)[0]
        row = struct.unpack_from('<H', data, off + 6)[0]
        width = struct.unpack_from('<H', data, off + 8)[0]
        height = struct.unpack_from('<H', data, off + 10)[0]
        sender = data[off + 13]
        port = data[off + 14]
        chain = struct.unpack_from('<H', data, off + 15)[0]

        if 0 < width < 4096:
            pw_counts[width] = pw_counts.get(width, 0) + 1
        if 0 < height < 4096:
            ph_counts[height] = ph_counts.get(height, 0) + 1

        panels.append({
            'col': col,
            'row': row,
            'x': x,
            'y': y,
            'width': width,
            'height': height,
            'sender': sender,
            'port': port,
            'chain_order': chain,
        })

    if not panels:
        return None

    pw = max(pw_counts, key=pw_counts.get) if pw_counts else 128
    ph = max(ph_counts, key=ph_counts.get) if ph_counts else 128

    return {
        'screen_idx': s_idx,
        'x': screen_x,
        'y': screen_y,
        'cols': cols,
        'rows': rows,
        'panel_width': pw,
        'panel_height': ph,
        'panels': panels,
    }
