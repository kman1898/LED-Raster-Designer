// mtp-polarity: where an MTP trunk delivers each fiber at its far end, by
// its polarity (owner, 2026-11-18). A plain module with no DOM, so its
// math runs under node too (tests/js/mtp_polarity.test.mjs).
//
// A link's strands are stored in the PROCESSOR order: the position each
// fiber takes in the MTP at the processor end. The far end (the breakout
// box's end) gets each fiber at the position this map gives. Every MTP
// trunk carries a polarity, Type A, B or C; a cable with none is Type A,
// what Neutrik and touring stock ship as.
//
// THE DOCUMENTED MAPS, n the position at the processor end:
//   12 fiber  A: n -> n                (Neutrik opticalCON MTP12, BDA 649,
//                                       "Type A: 1-1")
//             B: n -> 13 - n           (Panduit 00078EFL-DC)
//             C: each pair swaps, 1 <-> 2, 3 <-> 4 ...  (Panduit 00078EFL-DC)
//   24 fiber, two rows, 1-12 on top and 13-24 on the bottom:
//             A: n -> n + 12 for n <= 12, n - 12 past it (Neutrik opticalCON
//                MTP24, BDA 524, "Type A:2-2", leg 1 -> leg 13; L-com
//                MPFF24OM5AZ)
//             B: n -> 25 - n           (L-com MPMM24OM4BR)
//             C: Type A's row swap, then the pair swap, so 1 -> 14 and
//                2 -> 13 (one maker's sheet only)
//   16 fiber  B: n -> 17 - n
//   32 fiber (2 x 16) B: each row reverses on its own, 1-16 -> 16..1 and
//             17-32 -> 32..17
//
// ANYTHING ELSE IS NOT GUESSED: 48, 72 and every other count, 16 or 32 in
// Type A or C, and 8 fiber in any type. The far end then reads
// MTP_SEE_MAP and the binder prints no number for it.
//
// 8 FIBER: the app numbers an 8-strand MTP 1-8, as it numbers every cable.
// A Base-8 MTP uses ferrule positions 1-4 and 9-12 with 5-8 empty (Panduit:
// 8 fiber A n -> n, B n -> 13 - n on those positions), so its legs are not
// the app's 1-8. It reads MTP_SEE_MAP until the owner rules on it.

export const MTP_POLARITIES = ['A', 'B', 'C'];

// What the far end reads where no map is documented.
export const MTP_SEE_MAP = 'see cable map';

// A cable's polarity: its own, or Type A where it has none (an older show).
export function mtpPolarity(cable) {
    const p = cable && cable.polarity;
    return MTP_POLARITIES.includes(p) ? p : 'A';
}

// "Type A"
export function mtpPolarityWord(polarity) {
    return `Type ${MTP_POLARITIES.includes(polarity) ? polarity : 'A'}`;
}

// The two fibers of a duplex pair trade places: 1 <-> 2, 3 <-> 4.
const pairSwap = (n) => (n % 2 ? n + 1 : n - 1);
// A 24's two rows of 12 trade places: 1 <-> 13.
const rowSwap = (n) => (n <= 12 ? n + 12 : n - 12);

// Where the fiber at position `n` of the processor end arrives at the far
// end of a `count`-fiber MTP of `polarity`, or null where that is not
// documented (never a guess).
export function mtpFarPosition(n, count, polarity) {
    const num = Number(n);
    const total = Number(count);
    if (!Number.isInteger(num) || !Number.isInteger(total) || num < 1 || num > total) return null;
    const p = MTP_POLARITIES.includes(polarity) ? polarity : 'A';
    if (total === 12) {
        if (p === 'A') return num;
        if (p === 'B') return 13 - num;
        return pairSwap(num);
    }
    if (total === 24) {
        if (p === 'A') return rowSwap(num);
        if (p === 'B') return 25 - num;
        return pairSwap(rowSwap(num));
    }
    if (total === 16 && p === 'B') return 17 - num;
    if (total === 32 && p === 'B') return num <= 16 ? 17 - num : 49 - num;
    return null;
}

// Whether a `count`-fiber MTP of `polarity` has a documented map.
export function mtpMapDocumented(count, polarity) {
    return mtpFarPosition(1, count, polarity) !== null;
}

// A link's legs AT THE BREAKOUT, in the order they plug in there, from its
// strands in the processor order - or null where the map is not documented.
//
// THE SEND/RECEIVE SWAP (owner, 2026-11-18). A duplex link's two fibers are
// send and receive: what the processor sends on its first must reach the
// box's receive, its second. A TAC carries each leg straight through, so
// its pair is shown flipped at the box (2 · 1 for a 1 · 2 link). An MTP
// does the same ON TOP OF the far-end map: the leg in the box's first place
// is the one carrying the processor's SECOND fiber, so the legs read the
// far positions in reverse. MTP-24 Type A: the processor's 1 · 2 arrive on
// 13 and 14, and the breakout reads 14 · 13.
//
// NEVER A DOUBLE SWAP. Type B and Type C already cross a pair inside the
// trunk: a 12-fiber Type B delivers 1, 2 on 12, 11 and a Type C on 2, 1, so
// the far end's pair already has the processor's second fiber in its first
// place. Read the same way, the box gets that pair as delivered, 11 · 12
// (Type B) and 1 · 2 (Type C), in the far end's own order, with no swap
// added on top: swapping it again would put send onto send. One rule
// covers every type - the box's first place takes the leg the processor's
// second fiber arrives on - so the swap is the trunk's or the breakout's,
// never both (Neutrik NWP04: the pair flips once, at one fan-out).
// A BiDi link's one strand is its one leg.
export function mtpLegsAtBreakout(strands, count, polarity) {
    const list = (strands || []).map(Number);
    const far = list.map(n => mtpFarPosition(n, count, polarity));
    if (far.some(f => f === null)) return null;
    return far.reverse();
}
