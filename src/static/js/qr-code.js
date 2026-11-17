// qr-code: a small QR Code encoder for the IDM Locator's phone
// address (app-idm-phone.js), so the code is drawn on this computer and no
// network service ever sees the address. Byte mode, error correction level
// M (about 15% of the code can be lost and it still reads), versions 1 to
// 10 (up to 213 bytes at M: an address is a few dozen). The layout and the
// error correction follow the QR Code standard (ISO/IEC 18004);
// tests/test_idm_phone.py decodes what this draws with an independent
// reader and checks every part of it.
//
// The Reed-Solomon arithmetic, the block interleave, the alignment
// positions and the format and version bits follow the QR Code generator
// library by Project Nayuki, under the MIT License (listed in
// THIRD-PARTY-NOTICES; scripts/build_third_party_notices.py reads the
// copyright line below):
//
//   Copyright (c) Project Nayuki. (MIT License)
//   https://www.nayuki.io/page/qr-code-generator-library
//
//   Permission is hereby granted, free of charge, to any person obtaining a
//   copy of this software and associated documentation files (the
//   "Software"), to deal in the Software without restriction, including
//   without limitation the rights to use, copy, modify, merge, publish,
//   distribute, sublicense, and/or sell copies of the Software, and to
//   permit persons to whom the Software is furnished to do so, subject to
//   the following conditions:
//   - The above copyright notice and this permission notice shall be
//     included in all copies or substantial portions of the Software.
//   - The Software is provided "as is", without warranty of any kind,
//     express or implied, including but not limited to the warranties of
//     merchantability, fitness for a particular purpose and
//     noninfringement. In no event shall the authors or copyright holders
//     be liable for any claim, damages or other liability, whether in an
//     action of contract, tort or otherwise, arising from, out of or in
//     connection with the Software or the use or other dealings in the
//     Software.

const ECC_M = 0;            // the format bits' code for level M
// Level M, by version 1..10: error correction codewords per block, and
// blocks.
const ECC_PER_BLOCK = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
const BLOCKS = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
const MAX_VERSION = 10;

function bit(x, i) {
    return ((x >>> i) & 1) !== 0;
}

// Modules (bits) a version has for data and error correction.
function rawModules(ver) {
    let n = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
        const align = Math.floor(ver / 7) + 2;
        n -= (25 * align - 10) * align - 55;
        if (ver >= 7) n -= 36;
    }
    return n;
}

function dataCodewords(ver) {
    return Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[ver] * BLOCKS[ver];
}

// ── Reed-Solomon over GF(256), polynomial 0x11d ───────────────────────────

function gfMul(x, y) {
    let z = 0;
    for (let i = 7; i >= 0; i--) {
        z = (z << 1) ^ ((z >>> 7) * 0x11d);
        z ^= ((y >>> i) & 1) * x;
    }
    return z;
}

function rsDivisor(degree) {
    const out = new Array(degree).fill(0);
    out[degree - 1] = 1;
    let root = 1;
    for (let i = 0; i < degree; i++) {
        for (let j = 0; j < out.length; j++) {
            out[j] = gfMul(out[j], root);
            if (j + 1 < out.length) out[j] ^= out[j + 1];
        }
        root = gfMul(root, 0x02);
    }
    return out;
}

function rsRemainder(data, divisor) {
    const out = divisor.map(() => 0);
    for (const b of data) {
        const factor = b ^ out.shift();
        out.push(0);
        divisor.forEach((coef, i) => { out[i] ^= gfMul(coef, factor); });
    }
    return out;
}

// ── the codewords ─────────────────────────────────────────────────────────

function encodeData(bytes, ver) {
    const bits = [];
    const put = (value, len) => { for (let i = len - 1; i >= 0; i--) bits.push((value >>> i) & 1); };
    put(0x4, 4);                                  // byte mode
    put(bytes.length, ver <= 9 ? 8 : 16);
    bytes.forEach(b => put(b, 8));
    const cap = dataCodewords(ver) * 8;
    put(0, Math.min(4, cap - bits.length));       // terminator
    put(0, (8 - bits.length % 8) % 8);
    const out = [];
    for (let i = 0; i < bits.length; i += 8) {
        let b = 0;
        for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
        out.push(b);
    }
    for (let pad = 0xec; out.length < dataCodewords(ver); pad ^= 0xec ^ 0x11) out.push(pad);
    return out;
}

// The data split into blocks, each with its error correction, interleaved.
function addEcc(data, ver) {
    const numBlocks = BLOCKS[ver];
    const eccLen = ECC_PER_BLOCK[ver];
    const raw = Math.floor(rawModules(ver) / 8);
    const numShort = numBlocks - raw % numBlocks;
    const shortLen = Math.floor(raw / numBlocks);
    const div = rsDivisor(eccLen);
    const blocks = [];
    for (let i = 0, k = 0; i < numBlocks; i++) {
        const dat = data.slice(k, k + shortLen - eccLen + (i < numShort ? 0 : 1));
        k += dat.length;
        const ecc = rsRemainder(dat, div);
        if (i < numShort) dat.push(0);
        blocks.push(dat.concat(ecc));
    }
    const out = [];
    for (let i = 0; i < blocks[0].length; i++) {
        blocks.forEach((block, j) => {
            if (i !== shortLen - eccLen || j >= numShort) out.push(block[i]);
        });
    }
    return out;
}

// ── the symbol ────────────────────────────────────────────────────────────

function alignmentPositions(ver) {
    if (ver === 1) return [];
    const size = ver * 4 + 17;
    const n = Math.floor(ver / 7) + 2;
    const step = Math.ceil((ver * 4 + 4) / (n * 2 - 2)) * 2;
    const out = [6];
    for (let pos = size - 7; out.length < n; pos -= step) out.splice(1, 0, pos);
    return out;
}

const MASKS = [
    (x, y) => (x + y) % 2 === 0,
    (x, y) => y % 2 === 0,
    (x, y) => x % 3 === 0,
    (x, y) => (x + y) % 3 === 0,
    (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
    (x, y) => x * y % 2 + x * y % 3 === 0,
    (x, y) => (x * y % 2 + x * y % 3) % 2 === 0,
    (x, y) => ((x + y) % 2 + x * y % 3) % 2 === 0,
];

function build(ver, codewords, mask) {
    const size = ver * 4 + 17;
    const dark = Array.from({ length: size }, () => new Array(size).fill(false));
    const fixed = Array.from({ length: size }, () => new Array(size).fill(false));
    const set = (x, y, on) => { dark[y][x] = on; fixed[y][x] = true; };
    // timing patterns
    for (let i = 0; i < size; i++) {
        set(6, i, i % 2 === 0);
        set(i, 6, i % 2 === 0);
    }
    // finder patterns with their separators
    [[3, 3], [size - 4, 3], [3, size - 4]].forEach(([cx, cy]) => {
        for (let dy = -4; dy <= 4; dy++) {
            for (let dx = -4; dx <= 4; dx++) {
                const x = cx + dx, y = cy + dy;
                if (x < 0 || y < 0 || x >= size || y >= size) continue;
                const d = Math.max(Math.abs(dx), Math.abs(dy));
                set(x, y, d !== 2 && d !== 4);
            }
        }
    });
    // alignment patterns
    const pos = alignmentPositions(ver);
    const last = pos.length - 1;
    pos.forEach((ay, i) => pos.forEach((ax, j) => {
        if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
        for (let dy = -2; dy <= 2; dy++) {
            for (let dx = -2; dx <= 2; dx++) set(ax + dx, ay + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
        }
    }));
    // format information (level M and the mask), and the dark module
    const fdata = (ECC_M << 3) | mask;
    let rem = fdata;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const fbits = ((fdata << 10) | rem) ^ 0x5412;
    for (let i = 0; i <= 5; i++) set(8, i, bit(fbits, i));
    set(8, 7, bit(fbits, 6));
    set(8, 8, bit(fbits, 7));
    set(7, 8, bit(fbits, 8));
    for (let i = 9; i < 15; i++) set(14 - i, 8, bit(fbits, i));
    for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(fbits, i));
    for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(fbits, i));
    set(8, size - 8, true);
    // version information (7 and up)
    if (ver >= 7) {
        let r = ver;
        for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >>> 11) * 0x1f25);
        const vbits = (ver << 12) | r;
        for (let i = 0; i < 18; i++) {
            const a = size - 11 + i % 3, b = Math.floor(i / 3);
            set(a, b, bit(vbits, i));
            set(b, a, bit(vbits, i));
        }
    }
    // the codewords, two columns at a time in a zigzag from the bottom right
    let k = 0;
    for (let right = size - 1; right >= 1; right -= 2) {
        if (right === 6) right = 5;
        for (let vert = 0; vert < size; vert++) {
            for (let j = 0; j < 2; j++) {
                const x = right - j;
                const up = ((right + 1) & 2) === 0;
                const y = up ? size - 1 - vert : vert;
                if (fixed[y][x]) continue;
                if (k < codewords.length * 8) {
                    dark[y][x] = bit(codewords[k >>> 3], 7 - (k & 7));
                    k++;
                }
            }
        }
    }
    // the mask, on the data modules only
    const m = MASKS[mask];
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) if (!fixed[y][x] && m(x, y)) dark[y][x] = !dark[y][x];
    }
    return dark;
}

// The standard's penalty: long runs, 2 x 2 blocks, finder-like patterns
// and an unbalanced dark share each count against a mask.
function penalty(dark) {
    const size = dark.length;
    let score = 0;
    const line = (get) => {
        let run = 1;
        const seq = [];
        for (let i = 0; i < size; i++) seq.push(get(i));
        for (let i = 1; i <= size; i++) {
            if (i < size && seq[i] === seq[i - 1]) { run++; continue; }
            if (run >= 5) score += run - 2;
            run = 1;
        }
        const pat = [true, false, true, true, true, false, true];
        for (let i = 0; i + 7 <= size; i++) {
            if (!pat.every((v, j) => seq[i + j] === v)) continue;
            const before = i >= 4 && [1, 2, 3, 4].every(d => !seq[i - d]);
            const after = i + 11 <= size && [7, 8, 9, 10].every(d => !seq[i + d]);
            if (before || after) score += 40;
        }
    };
    for (let y = 0; y < size; y++) line(x => dark[y][x]);
    for (let x = 0; x < size; x++) line(y => dark[y][x]);
    for (let y = 0; y + 1 < size; y++) {
        for (let x = 0; x + 1 < size; x++) {
            const c = dark[y][x];
            if (c === dark[y][x + 1] && c === dark[y + 1][x] && c === dark[y + 1][x + 1]) score += 3;
        }
    }
    let n = 0;
    dark.forEach(row => row.forEach(c => { if (c) n++; }));
    const total = size * size;
    score += Math.floor(Math.abs(n * 20 - total * 10) / total) * 10;
    return score;
}

// The QR Code of `text` as rows of booleans (true: dark), the quiet zone
// not included; null when the text is too long for version 10 at level M.
export function qrMatrix(text) {
    const bytes = Array.from(new TextEncoder().encode(String(text)));
    let ver = 1;
    // byte mode: 4 bits of mode, the count, 8 bits a byte
    while (ver <= MAX_VERSION && 4 + (ver <= 9 ? 8 : 16) + bytes.length * 8 > dataCodewords(ver) * 8) ver++;
    if (ver > MAX_VERSION) return null;
    const codewords = addEcc(encodeData(bytes, ver), ver);
    let best = null, bestScore = Infinity;
    for (let mask = 0; mask < 8; mask++) {
        const m = build(ver, codewords, mask);
        const s = penalty(m);
        if (s < bestScore) { best = m; bestScore = s; }
    }
    return best;
}

// The code as an SVG string: dark squares on white, with the standard's
// four-module quiet zone; `label` names it for a screen reader.
export function qrSvg(text, label = 'QR code') {
    const m = qrMatrix(text);
    if (!m) return '';
    const quiet = 4;
    const n = m.length + quiet * 2;
    let path = '';
    m.forEach((row, y) => row.forEach((on, x) => {
        if (on) path += `M${x + quiet},${y + quiet}h1v1h-1z`;
    }));
    const safe = String(label).replace(/[<>&"]/g, '');
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n} ${n}" shape-rendering="crispEdges" role="img" aria-label="${safe}">`
        + `<rect width="${n}" height="${n}" fill="#ffffff"/><path d="${path}" fill="#000000"/></svg>`;
}
