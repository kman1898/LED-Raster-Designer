// quick-palettes: the colour maths behind the Pixel Map tab's Quick
// Palettes section (app-quick-palettes.js) and its Preferences defaults
// (app-preferences.js). Pure functions only, no DOM, so the browser tests
// can drive them directly.
//
// A quick palette is one checkerboard pair: Color 1 a dark shade, Color 2 a
// light tint. Eight of them are built round the colour wheel, 45 degrees
// apart, in OKLCH (a perceptual colour space) so every pair reads equally
// bright: in plain HSL a yellow at the same "lightness" as a blue glows. A
// colour the screen cannot show is brought back in by lowering its chroma
// (saturation) and keeping its lightness and hue.

export const QUICK_PALETTE_COUNT = 8;
export const QUICK_PALETTE_STEP = 360 / QUICK_PALETTE_COUNT;

// The pair a new screen ships with (getPreferencesDefaults color1/color2).
export const SHIPPED_PAIR = ['#404680', '#959CB8'];

// Lightness and chroma for each colour of a pair, and how far Color 2's hue
// turns from Color 1's. Tonal is the shipped pair's own look (its OKLCH
// figures, rounded); Bold carries more colour; Split turns Color 2 40
// degrees for a two-hue pair.
export const QUICK_PALETTE_STYLES = {
    tonal: { l1: 0.42, c1: 0.085, l2: 0.71, c2: 0.045, dh: 0 },
    bold: { l1: 0.44, c1: 0.16, l2: 0.76, c2: 0.11, dh: 0 },
    split: { l1: 0.42, c1: 0.11, l2: 0.74, c2: 0.09, dh: 40 },
};

const toLinear = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
};
const fromLinear = (c) => {
    const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    return v * 255;
};

// '#RRGGBB' (or 'RRGGBB', or '#RGB') -> [r, g, b]; anything else is null.
export function parseHex(hex) {
    let h = String(hex == null ? '' : hex).trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{3}$/.test(h)) h = h.split('').map(c => c + c).join('');
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
    return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
}

export function toHex(rgb) {
    return '#' + rgb.map(v => Math.round(Math.max(0, Math.min(255, v)))
        .toString(16).padStart(2, '0')).join('').toUpperCase();
}

// [r, g, b] (0-255) -> [L, C, H]: L 0-1, C 0-~0.4, H degrees 0-360.
export function rgbToOklch(rgb) {
    const [r, g, b] = rgb.map(toLinear);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
    const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
    const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
    const H = (Math.atan2(B, A) * 180 / Math.PI + 360) % 360;
    return [L, Math.hypot(A, B), H];
}

function oklchToLinear(L, C, H) {
    const a = C * Math.cos(H * Math.PI / 180);
    const b = C * Math.sin(H * Math.PI / 180);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    return [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ];
}

const inGamut = (lin) => lin.every(x => x >= -1e-4 && x <= 1 + 1e-4);

// [L, C, H] -> '#RRGGBB', lowering C until the colour fits the screen.
export function oklchToHex(L, C, H) {
    let lin = oklchToLinear(L, C, H);
    if (!inGamut(lin)) {
        let lo = 0, hi = C;
        for (let i = 0; i < 24; i++) {
            const mid = (lo + hi) / 2;
            if (inGamut(oklchToLinear(L, mid, H))) lo = mid; else hi = mid;
        }
        lin = oklchToLinear(L, lo, H);
    }
    return toHex(lin.map(v => fromLinear(Math.max(0, Math.min(1, v)))));
}

// The OKLCH hue of a colour, in whole degrees; a grey (no hue to speak
// of) and a value that is not a colour read as the shipped pair's hue.
export function hueOf(hex) {
    const rgb = parseHex(hex);
    const shipped = rgbToOklch(parseHex(SHIPPED_PAIR[0]))[2];
    if (!rgb) return Math.round(shipped);
    const [, C, H] = rgbToOklch(rgb);
    return Math.round(C < 0.02 ? shipped : H);
}

// Turn a colour's hue by `degrees`, keeping its lightness and chroma.
// 0 hands the colour back exactly as given (upper case).
export function rotateHue(hex, degrees) {
    const rgb = parseHex(hex);
    if (!rgb) return hex;
    const d = Number(degrees) || 0;
    if (d === 0) return toHex(rgb);
    const [L, C, H] = rgbToOklch(rgb);
    return oklchToHex(L, C, ((H + d) % 360 + 360) % 360);
}

// The eight pairs round the wheel from `baseHue`, in `style`. With
// `current` (a [c1, c2] pair), slot 1 is that pair exactly: the screen's
// own colours, so the set always offers a way back.
export function generateQuickPalettes(baseHue, style, current) {
    const s = QUICK_PALETTE_STYLES[style] || QUICK_PALETTE_STYLES.tonal;
    const base = Number.isFinite(Number(baseHue)) ? Number(baseHue) : hueOf(SHIPPED_PAIR[0]);
    const out = [];
    for (let i = 0; i < QUICK_PALETTE_COUNT; i++) {
        if (i === 0 && current && parseHex(current[0]) && parseHex(current[1])) {
            out.push([toHex(parseHex(current[0])), toHex(parseHex(current[1]))]);
            continue;
        }
        const h = ((base + i * QUICK_PALETTE_STEP) % 360 + 360) % 360;
        out.push([
            oklchToHex(s.l1, s.c1, h),
            oklchToHex(s.l2, s.c2, (h + s.dh) % 360),
        ]);
    }
    return out;
}

// The eight pairs the Preferences dialog ships with: the Tonal set round
// the shipped pair, slot 1 the shipped pair itself.
export function shippedQuickPalettes() {
    return generateQuickPalettes(hueOf(SHIPPED_PAIR[0]), 'tonal', SHIPPED_PAIR);
}

// A stored list of pairs as eight checked [c1, c2] pairs: an entry that
// is not a pair of colours falls back to the shipped pair in its slot.
export function normalizeQuickPalettes(list) {
    const shipped = shippedQuickPalettes();
    const src = Array.isArray(list) ? list : [];
    return shipped.map((fallback, i) => {
        const p = Array.isArray(src[i]) ? src[i] : [];
        const a = parseHex(p[0]), b = parseHex(p[1]);
        return [a ? toHex(a) : fallback[0], b ? toHex(b) : fallback[1]];
    });
}

// WCAG contrast ratio between two colours (1 to 21).
export function contrastRatio(hexA, hexB) {
    const lum = (hex) => {
        const [r, g, b] = (parseHex(hex) || [0, 0, 0]).map(toLinear);
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const x = lum(hexA), y = lum(hexB);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
