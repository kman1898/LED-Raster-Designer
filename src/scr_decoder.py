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

import math
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


def _derive_grid_from_pixel_positions(data: bytes, rec_start: int, n_panels: int):
    """
    For newer Format B sections where the StandardScreen header cols/rows are
    invalid (0 or >512), derive grid dimensions from panel records.

    Two sub-formats are handled:

    Pixel-position variant (e.g. Test 3 section 0):
      off+8 = cabinet X pixel position, off+10 = cabinet Y pixel position.
      pw/ph derived from GCD of consecutive sorted differences.

    Row-index variant (e.g. Test 3 section 1):
      off+8 = cabinet X pixel position, off+10 = row index (0-based sequential).
      pw from GCD of X diffs; rows = max row index + 1;
      ph from the u16 at off+14 (panel size field in this format variant).

    Returns (cols, rows, pw, ph, y_are_indices) or None if derivation fails.
    """
    xs = []
    ys = []
    for p_idx in range(n_panels):
        off = rec_start + p_idx * RECORD_SIZE
        xs.append(struct.unpack_from('<H', data, off + 8)[0])
        ys.append(struct.unpack_from('<H', data, off + 10)[0])

    xs_unique = sorted(set(xs))
    ys_unique = sorted(set(ys))

    if len(xs_unique) < 2 or len(ys_unique) < 2:
        return None

    x_diffs = [xs_unique[i + 1] - xs_unique[i] for i in range(len(xs_unique) - 1)]
    y_diffs = [ys_unique[i + 1] - ys_unique[i] for i in range(len(ys_unique) - 1)]

    pw = x_diffs[0]
    for d in x_diffs[1:]:
        pw = math.gcd(pw, d)

    if pw < 16 or pw > 512:
        return None

    cols = xs_unique[-1] // pw + 1
    if cols < 1 or cols > 512:
        return None

    ph_gcd = y_diffs[0]
    for d in y_diffs[1:]:
        ph_gcd = math.gcd(ph_gcd, d)

    if 16 <= ph_gcd <= 512:
        # Pixel-position variant: Y values are cabinet Y pixel positions
        rows = ys_unique[-1] // ph_gcd + 1
        ph = ph_gcd
        y_are_indices = False
    elif all(d == 1 for d in y_diffs):
        # Row-index variant: Y values are sequential 0-based row indices
        rows = ys_unique[-1] + 1
        # Panel height is stored at off+14 in this format
        ph_votes = {}
        for p_idx in range(n_panels):
            off = rec_start + p_idx * RECORD_SIZE
            val = struct.unpack_from('<H', data, off + 14)[0]
            ph_votes[val] = ph_votes.get(val, 0) + 1
        ph_candidate = max(ph_votes, key=ph_votes.get) if ph_votes else 0
        ph = ph_candidate if 16 <= ph_candidate <= 512 else pw
        y_are_indices = True
    else:
        return None

    if rows < 1 or rows > 512:
        return None

    return cols, rows, pw, ph, y_are_indices


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

    # Detect format A vs B.
    # Format A: 10-byte header + 4-byte marker + records (+ optional suffix).
    #   Records start at offset+14.
    # Format B: 10-byte header only, records immediately follow.
    #   Records start at offset+10.
    #
    # Strategy: if bytes 10-13 are non-zero (a potential marker is present) AND
    # the first record from offset+14 has plausible panel dimensions (pw/ph in 16-4096),
    # treat as Format A. Otherwise use Format B.
    _marker = data[offset + 10:offset + 14]
    _use_format_a = False
    if _marker != b'\x00\x00\x00\x00' and offset + 14 + RECORD_SIZE <= len(data):
        _test_pw = struct.unpack_from('<H', data, offset + 14 + 8)[0]
        _test_ph = struct.unpack_from('<H', data, offset + 14 + 10)[0]
        if 16 <= _test_pw <= 4096 and 16 <= _test_ph <= 4096:
            _use_format_a = True

    if _use_format_a:
        rec_start = offset + 14
        n_panels = (size - 14) // RECORD_SIZE
    else:
        rec_start = offset + 10
        n_panels = (size - FORMAT_B_OVERHEAD) // RECORD_SIZE

    if n_panels <= 0:
        return None

    # If header cols/rows are invalid, try to derive from pixel positions in records
    header_valid = (1 <= cols <= 512 and 1 <= rows <= 512)
    derived_pw = None
    derived_ph = None
    y_are_indices = False

    if not header_valid:
        result = _derive_grid_from_pixel_positions(data, rec_start, n_panels)
        if result is None:
            return None
        cols, rows, derived_pw, derived_ph, y_are_indices = result

    panels = []
    pw_counts = {}
    ph_counts = {}

    for p_idx in range(n_panels):
        off = rec_start + p_idx * RECORD_SIZE
        if off + RECORD_SIZE > len(data):
            break

        if derived_pw is not None:
            # Newer format: off+8 = cabinet X pixel position
            x_pix = struct.unpack_from('<H', data, off + 8)[0]
            y_val = struct.unpack_from('<H', data, off + 10)[0]
            col = x_pix // derived_pw
            if y_are_indices:
                # off+10 is a 0-based row index, not a pixel position
                row = y_val
                y_pix = row * derived_ph
            else:
                row = y_val // derived_ph
                y_pix = y_val
            x = x_pix
            y = y_pix
            width = derived_pw
            height = derived_ph
            sender = data[off + 13]
            port = data[off + 14]
            chain = struct.unpack_from('<H', data, off + 15)[0]
        else:
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

    if derived_pw is not None:
        pw = derived_pw
        ph = derived_ph
    else:
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
