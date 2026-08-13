"""Decode a real NovaStar .scr, re-encode it, and diff the bytes.

Why this exists
---------------
SCR export was abandoned because it could never be made right, and the only
signal available was "does NovaLCT accept the file" - one bit, arrived at
slowly, through a GUI. That tells you nothing about WHERE you are wrong.

Re-encoding a file NovaStar itself produced gives a gradient instead: a byte
count, and the record field each differing byte lands in. Every bug found so
far was found this way, and one of them (a hardcoded section marker) cost a
cabinet in NovaLCT while looking like 3 harmless bytes.

The reference corpus is the user's own show files, which are NOT in the repo -
they are production drawings. Point LRD_SCR_CORPUS at a directory of .scr files
to run those checks:

    LRD_SCR_CORPUS=~/Desktop/LRD_SCR python3 -m pytest tests/test_scr_roundtrip.py -v

Without it, the corpus tests skip and the format-arithmetic tests below still
run, so this file cannot rot silently.

What is known, as of writing
----------------------------
* Every section seen is: 14-byte header + N x 17-byte records + suffix.
  The suffix is 11 bytes on 2026-era files and 13 on 2025-era ones, giving
  section overheads of 25 and 27. Nothing else differs between them.
* Some older files (2025 Rezz, 2025 Nocturnal) use a 16-BYTE record instead.
  Those are not supported; decode_scr rejects them rather than guessing.
* One 2026 file re-encodes byte-for-byte identical. The rest differ only in
  the record's byte 12 and the file checksums - see RESIDUAL_FIELDS.
"""

import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scr_decoder import (  # noqa: E402
    decode_scr, BLOCK_START, SCREENCOUNT_OFFSET, SECTIONLEN_OFFSET,
    RECORD_SIZE, SECTION_HEADER_SIZE, FORMAT_A_OVERHEAD, FORMAT_B_OVERHEAD,
)
from scr_encoder import build_multi_screen_scr  # noqa: E402


# ── the format arithmetic (always runs) ──────────────────────────────────

def test_the_two_overheads_are_header_plus_suffix():
    """25 and 27 are not arbitrary: same 14-byte header, same 17-byte records,
    an 11- or 13-byte suffix. An earlier value of 10 encoded a layout no real
    file uses - it divided evenly on 2025 files by coincidence and decoded
    every field 4 bytes off, which is how a cabinet width turned up in the
    Active byte."""
    assert FORMAT_A_OVERHEAD == SECTION_HEADER_SIZE + 11
    assert FORMAT_B_OVERHEAD == SECTION_HEADER_SIZE + 13


@pytest.mark.parametrize('size,expected', [
    (25 + 198 * RECORD_SIZE, FORMAT_A_OVERHEAD),
    (27 + 181 * RECORD_SIZE, FORMAT_B_OVERHEAD),
    (25 + 952 * RECORD_SIZE, FORMAT_A_OVERHEAD),
    (27 + 53 * RECORD_SIZE, FORMAT_B_OVERHEAD),
])
def test_overhead_is_decidable_from_the_size_alone(size, expected):
    """A section is a header plus a whole number of records, so only one
    overhead can divide evenly. That is what picks the layout - not the bytes
    at 10-13, which are per-section data (sending card, first port) and carry
    zeros often enough that sniffing them was a coin flip."""
    fits = [oh for oh in (FORMAT_A_OVERHEAD, FORMAT_B_OVERHEAD)
            if size > oh and (size - oh) % RECORD_SIZE == 0]
    assert fits == [expected], f'size {size} fits {fits}, expected only {expected}'


# ── the round trip (needs the corpus) ────────────────────────────────────

CORPUS = os.environ.get('LRD_SCR_CORPUS')
_files = sorted(Path(CORPUS).glob('*.scr')) if CORPUS and Path(CORPUS).is_dir() else []


def _sections(data):
    """(marker, suffix_len) per section, straight from the file."""
    n = data[BLOCK_START + SCREENCOUNT_OFFSET]
    sizes = [struct.unpack_from('<I', data, BLOCK_START + SECTIONLEN_OFFSET + i * 4)[0]
             for i in range(n)]
    off = BLOCK_START + SECTIONLEN_OFFSET + n * 4
    out = []
    for sz in sizes:
        suffix = 11 if (sz - FORMAT_A_OVERHEAD) % RECORD_SIZE == 0 else 13
        # The terminator record - last one in the section - is not uniform
        # across files, so it is read rather than assumed.
        n_rec = (sz - SECTION_HEADER_SIZE - suffix) // RECORD_SIZE
        t_off = off + SECTION_HEADER_SIZE + (n_rec - 1) * RECORD_SIZE
        out.append({'offset': off, 'size': sz,
                    'marker': data[off + 10:off + 14], 'suffix_len': suffix,
                    'terminator': {'active': data[t_off + 12], 'sender': data[t_off + 13],
                                   'port': data[t_off + 14],
                                   'chain': struct.unpack_from('<H', data, t_off + 15)[0]}})
        off += sz
    return out


def _to_encoder_input(decoded, secs):
    """Decoder output -> encoder input.

    The two conventions here were established by measurement, not assumption:
    the encoder takes 1-BASED ports (the file stores 0-based), and rows are
    rotated by (row + 1) % rows. Getting either wrong took a round trip from
    0.6% to 7-8% differing bytes.
    """
    import collections
    screens = []
    for i, sc in enumerate(decoded['screens']):
        real = [p for p in sc['panels'] if p['sender'] != 255]
        card = (collections.Counter(p['sender'] for p in real).most_common(1)[0][0]
                if real else 0)
        rows = sc['rows']
        screens.append({
            'cols': sc['cols'], 'rows': rows,
            'pw': sc['panel_width'], 'ph': sc['panel_height'],
            'screen_x': sc['x'], 'screen_y': sc['y'],
            'sc_idx': card, 'port_start': 0,
            'marker': secs[i]['marker'], 'suffix_len': secs[i]['suffix_len'],
            'terminator': secs[i]['terminator'],
            'panels': [{
                'col': p['col'], 'row': (p['row'] + 1) % rows,
                'port_num': p['port'] + 1, 'chain_order': p['chain_order'],
                'hidden': p['sender'] == 255,
                'x': p['x'], 'y': p['y'], 'w': p['width'], 'h': p['height'],
            } for p in sc['panels']],
        })
    return screens


# Record byte -> field. Byte 12 and the file checksums are the only places a
# difference is currently understood and tolerated; a difference anywhere else
# means a real regression, so the test names the field rather than comparing
# against a percentage that would drift.
_FIELD = {0: 'X', 1: 'X', 2: 'Y', 3: 'Y', 4: 'XinPort', 5: 'XinPort',
          6: 'YinPort', 7: 'YinPort', 8: 'Width', 9: 'Width',
          10: 'Height', 11: 'Height', 12: 'Active', 13: 'Sender',
          14: 'Port', 15: 'ConnectIdx', 16: 'ConnectIdx'}
RESIDUAL_FIELDS = {'Active', 'file-header', 'section-suffix'}


def _classify(i, secs):
    for s in secs:
        if s['offset'] <= i < s['offset'] + s['size']:
            rs = s['offset'] + SECTION_HEADER_SIZE
            if i < rs:
                return 'section-header'
            k = i - rs
            n_rec = (s['size'] - SECTION_HEADER_SIZE - s['suffix_len']) // RECORD_SIZE
            if k // RECORD_SIZE >= n_rec:
                return 'section-suffix'
            return _FIELD[k % RECORD_SIZE]
    return 'file-header'


@pytest.mark.skipif(not _files, reason='set LRD_SCR_CORPUS to a directory of .scr files')
@pytest.mark.parametrize('path', _files, ids=lambda p: p.stem)
def test_reencode_reproduces_the_original(path):
    data = path.read_bytes()
    decoded = decode_scr(data)
    secs = _sections(data)
    out = build_multi_screen_scr(_to_encoder_input(decoded, secs))

    assert len(out) == len(data), (
        f'{path.name}: re-encoded to {len(out)} bytes, original is {len(data)}. '
        'A length change means the section or footer sizing is wrong, which is '
        'a structural bug rather than a field-level one.')

    diffs = [i for i in range(len(data)) if data[i] != out[i]]
    import collections
    kinds = collections.Counter(_classify(i, secs) for i in diffs)
    unexpected = {k: v for k, v in kinds.items() if k not in RESIDUAL_FIELDS}
    assert not unexpected, (
        f'{path.name}: {len(diffs)} bytes differ, and these are in fields that '
        f'should round-trip exactly: {unexpected}. '
        f'(Tolerated, still unexplained: {dict(kinds)})')
