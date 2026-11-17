"""A small QR Code reader for the tests (tests/test_idm_phone.py): it reads
back what src/static/js/qr-code.js draws, written apart from it so a
mistake on one side does not hide the same mistake on the other.

It takes the module matrix (rows of 0/1, no quiet zone) and checks every
part a phone's reader relies on: the finder patterns, the timing patterns,
the format information (both copies, against the standard's own table of
the 32 valid words), the version information (7 and up), the error
correction of every block (all syndromes zero), and the data, which it
decodes from byte mode. Only what the encoder makes (byte mode, any level,
versions 1 to 10) is read; anything else fails loudly.
"""

# The 32 format words of the standard (level bits and mask, BCH coded and
# XORed with 101010000010010), level by level as the standard lists them
# with its level codes: L = 01, M = 00, Q = 11, H = 10.
FORMAT_WORDS = {
    ('L', 0): 0x77C4, ('L', 1): 0x72F3, ('L', 2): 0x7DAA, ('L', 3): 0x789D,
    ('L', 4): 0x662F, ('L', 5): 0x6318, ('L', 6): 0x6C41, ('L', 7): 0x6976,
    ('M', 0): 0x5412, ('M', 1): 0x5125, ('M', 2): 0x5E7C, ('M', 3): 0x5B4B,
    ('M', 4): 0x45F9, ('M', 5): 0x40CE, ('M', 6): 0x4F97, ('M', 7): 0x4AA0,
    ('Q', 0): 0x355F, ('Q', 1): 0x3068, ('Q', 2): 0x3F31, ('Q', 3): 0x3A06,
    ('Q', 4): 0x24B4, ('Q', 5): 0x2183, ('Q', 6): 0x2EDA, ('Q', 7): 0x2BED,
    ('H', 0): 0x1689, ('H', 1): 0x13BE, ('H', 2): 0x1CE7, ('H', 3): 0x19D0,
    ('H', 4): 0x0762, ('H', 5): 0x0255, ('H', 6): 0x0D0C, ('H', 7): 0x083B,
}

# The standard's block table, versions 1 to 10: per level,
# (error correction codewords per block, [(blocks, data codewords each)]).
BLOCK_TABLE = {
    'L': {1: (7, [(1, 19)]), 2: (10, [(1, 34)]), 3: (15, [(1, 55)]), 4: (20, [(1, 80)]),
          5: (26, [(1, 108)]), 6: (18, [(2, 68)]), 7: (20, [(2, 78)]), 8: (24, [(2, 97)]),
          9: (30, [(2, 116)]), 10: (18, [(2, 68), (2, 69)])},
    'M': {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
          5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
          9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])},
}

# The standard's alignment pattern centres, versions 1 to 10.
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
         7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

# Version information words, 7 to 10 (the standard's table).
VERSION_WORDS = {7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3}


class QrError(AssertionError):
    pass


def _check(cond, why):
    if not cond:
        raise QrError(why)


def _gf_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


EXP, LOG = _gf_tables()


def _syndromes(block, n_ecc):
    """The block's syndromes at alpha^0 .. alpha^(n_ecc-1): all zero for a
    block whose error correction is right."""
    out = []
    for i in range(n_ecc):
        s = 0
        for b in block:
            s = (EXP[(LOG[s] + i) % 255] if s else 0) ^ b
        out.append(s)
    return out


def _mask(m, x, y):
    return [
        (x + y) % 2 == 0,
        y % 2 == 0,
        x % 3 == 0,
        (x + y) % 3 == 0,
        (x // 3 + y // 2) % 2 == 0,
        (x * y) % 2 + (x * y) % 3 == 0,
        ((x * y) % 2 + (x * y) % 3) % 2 == 0,
        ((x + y) % 2 + (x * y) % 3) % 2 == 0,
    ][m]


def read(matrix):
    """The text a QR matrix holds, after checking it. Returns
    {'text', 'version', 'level', 'mask'}; raises QrError on any fault."""
    size = len(matrix)
    _check(all(len(r) == size for r in matrix), 'not square')
    _check((size - 17) % 4 == 0, f'size {size} is not a QR size')
    ver = (size - 17) // 4
    _check(1 <= ver <= 10, f'version {ver} is not read here')
    m = [[1 if v else 0 for v in row] for row in matrix]

    def at(x, y):
        return m[y][x]

    # finder patterns: 7 x 7 rings at three corners, a light separator
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                d = max(abs(dx), abs(dy))
                want = 0 if d == 2 else 1
                _check(at(cx + dx, cy + dy) == want, f'finder at {cx},{cy} wrong at {dx},{dy}')
    # timing patterns
    for i in range(8, size - 8):
        _check(at(i, 6) == (1 if i % 2 == 0 else 0), f'timing row at {i}')
        _check(at(6, i) == (1 if i % 2 == 0 else 0), f'timing column at {i}')
    # the dark module
    _check(at(8, size - 8) == 1, 'the dark module is light')

    # format information, both copies (bit 14 first in the standard's reading)
    first = [at(8, 0), at(8, 1), at(8, 2), at(8, 3), at(8, 4), at(8, 5), at(8, 7), at(8, 8),
             at(7, 8), at(5, 8), at(4, 8), at(3, 8), at(2, 8), at(1, 8), at(0, 8)]
    second = [at(size - 1, 8), at(size - 2, 8), at(size - 3, 8), at(size - 4, 8),
              at(size - 5, 8), at(size - 6, 8), at(size - 7, 8), at(size - 8, 8),
              at(8, size - 7), at(8, size - 6), at(8, size - 5), at(8, size - 4),
              at(8, size - 3), at(8, size - 2), at(8, size - 1)]
    # first[i] is bit i (bit 0 = least significant)
    word1 = sum(b << i for i, b in enumerate(first))
    word2 = sum(b << i for i, b in enumerate(second))
    _check(word1 == word2, f'the two format copies differ: {word1:#x} {word2:#x}')
    found = [k for k, w in FORMAT_WORDS.items() if w == word1]
    _check(found, f'format word {word1:#06x} is not one of the standard\'s 32')
    level, mask = found[0]
    _check(level in BLOCK_TABLE, f'level {level} is not read here')

    # version information
    if ver >= 7:
        w1 = 0
        w2 = 0
        for i in range(18):
            a, b = size - 11 + i % 3, i // 3
            w1 |= at(a, b) << i
            w2 |= at(b, a) << i
        _check(w1 == w2 == VERSION_WORDS[ver], f'version words {w1:#x} {w2:#x}')

    # the function modules, to skip when reading data
    fixed = [[False] * size for _ in range(size)]

    def fix(x0, y0, x1, y1):
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                fixed[y][x] = True

    fix(0, 0, 9, 9)
    fix(size - 8, 0, size, 9)
    fix(0, size - 8, 9, size)
    fix(6, 0, 7, size)
    fix(0, 6, size, 7)
    pos = ALIGN[ver]
    for ay in pos:
        for ax in pos:
            if (ax, ay) in ((6, 6), (6, pos[-1]), (pos[-1], 6)):
                continue
            # the alignment pattern itself must be right
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    want = 0 if max(abs(dx), abs(dy)) == 1 else 1
                    _check(at(ax + dx, ay + dy) == want, f'alignment at {ax},{ay}')
            fix(ax - 2, ay - 2, ax + 3, ay + 3)
    if ver >= 7:
        fix(size - 11, 0, size - 8, 6)
        fix(0, size - 11, 6, size - 8)

    # the data bits, in the standard's order: column pairs from the right,
    # up then down, skipping the timing column
    bits = []
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for y in rows:
            for x in (col, col - 1):
                if not fixed[y][x]:
                    bits.append(at(x, y) ^ (1 if _mask(mask, x, y) else 0))
        upward = not upward
        col -= 2

    n_ecc, groups = BLOCK_TABLE[level][ver]
    sizes = [d for count, d in groups for _ in range(count)]
    total = sum(sizes) + n_ecc * len(sizes)
    _check(len(bits) >= total * 8, 'too few data modules')
    codewords = [int(''.join(str(b) for b in bits[i * 8:i * 8 + 8]), 2) for i in range(total)]
    # de-interleave: data codewords column by column, then the error
    # correction codewords
    blocks = [[] for _ in sizes]
    k = 0
    for i in range(max(sizes)):
        for j, n in enumerate(sizes):
            if i < n:
                blocks[j].append(codewords[k])
                k += 1
    for i in range(n_ecc):
        for j in range(len(sizes)):
            blocks[j].append(codewords[k])
            k += 1
    data = []
    for j, block in enumerate(blocks):
        syn = _syndromes(block, n_ecc)
        _check(not any(syn), f'block {j}: error correction does not check: {syn}')
        data.extend(block[:sizes[j]])

    # byte mode
    stream = ''.join(f'{b:08b}' for b in data)
    _check(stream[:4] == '0100', f'mode {stream[:4]} is not byte mode')
    count_bits = 8 if ver <= 9 else 16
    n = int(stream[4:4 + count_bits], 2)
    start = 4 + count_bits
    raw = bytes(int(stream[start + 8 * i:start + 8 * i + 8], 2) for i in range(n))
    rest = stream[start + 8 * n:]
    _check(set(rest[:4]) <= {'0'}, 'no terminator after the data')
    return {'text': raw.decode('utf-8'), 'version': ver, 'level': level, 'mask': mask}
