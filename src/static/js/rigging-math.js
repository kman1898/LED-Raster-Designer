// The Rigging tab's bar-fitting math: how a wall `total` panels wide is
// covered by header bars of the sizes the user picked. Plain functions, no
// DOM, so tests/test_rigging_math.py can run the file under node.
// Classic script: defines the global RiggingMath, loads before the app.
const RiggingMath = (() => {
    function cleanSizes(sizes) {
        const ok = (Array.isArray(sizes) ? sizes : []).filter(n => Number.isInteger(n) && n > 0);
        return Array.from(new Set(ok)).sort((a, b) => a - b);
    }

    // The sizes laid out left to right as symmetric as they can be: sizes
    // that appear an even number of times become mirrored pairs (largest
    // nearest the middle); one leftover size sits dead centre; two or more
    // leftovers become the outer bookends.
    function arrangeSymmetric(sizes) {
        const counts = new Map();
        for (const s of sizes) counts.set(s, (counts.get(s) || 0) + 1);

        const pairSizes = [];
        const leftoverSizes = [];
        for (const [size, count] of counts.entries()) {
            for (let i = 0; i < Math.floor(count / 2); i++) pairSizes.push(size);
            if (count % 2 === 1) leftoverSizes.push(size);
        }
        pairSizes.sort((a, b) => b - a);
        leftoverSizes.sort((a, b) => b - a);

        const coreLeft = [];
        const coreRight = [];
        for (const size of pairSizes) {
            coreLeft.unshift(size);
            coreRight.push(size);
        }

        let center = [];
        const outerLeft = [];
        const outerRight = [];
        const remaining = [...leftoverSizes];
        while (remaining.length >= 2) {
            outerLeft.unshift(remaining.shift());
            outerRight.push(remaining.shift());
        }
        if (remaining.length === 1) center = remaining;

        return [...outerLeft, ...coreLeft, ...center, ...coreRight, ...outerRight];
    }

    // A single (a 1-panel bar) costs this much more than any other bar, so
    // the tables below minimise singles first and bars second.
    const SINGLE_COST = 10000;

    // Coin-change tables for 0..total: the cheapest way to make each width
    // (fewest singles, then fewest bars) and the last bar of that answer.
    // Greedy fails here (sizes 3,4,5,6 and a width of 7 would take a 6 and
    // strand a 1).
    function _fewestBarsTable(total, valid) {
        const cost = new Array(total + 1).fill(Infinity);
        const lastSize = new Array(total + 1).fill(0);
        cost[0] = 0;
        for (let n = 1; n <= total; n++) {
            for (const size of valid) {
                const step = size === 1 ? SINGLE_COST + 1 : 1;
                if (size <= n && cost[n - size] + step < cost[n]) {
                    cost[n] = cost[n - size] + step;
                    lastSize[n] = size;
                }
            }
        }
        const singles = (n) => Math.floor(cost[n] / SINGLE_COST);
        const bars = (n) => cost[n] % SINGLE_COST;
        return { cost, lastSize, singles, bars };
    }

    function _barsFor(n, table) {
        const bars = [];
        for (let left = n; left > 0; left -= table.lastSize[left]) bars.push(table.lastSize[left]);
        return bars;
    }

    function isSymmetric(bars) {
        return bars.every((b, i) => b === bars[bars.length - 1 - i]);
    }

    // The header bars for a wall `total` panels wide, left to right, or null
    // when the sizes cannot make that width at all. In order of priority:
    //   1. as few singles (1-panel bars) as the width allows - a mirror
    //      layout is never worth extra singles (19 wide with 1s and 2s takes
    //      one single, not three);
    //   2. a mirror image where one exists at that many singles: the same
    //      bars either side of the middle, at most one dead centre (8 wide
    //      with every size is 4 + 4, not 6 + 2);
    //   3. the fewest bars.
    // When no mirror exists the singles stand at the left, then the rest in
    // the most balanced order (19 wide with 1s and 2s is 1, then nine 2s).
    function fitBars(total, sizes) {
        const valid = cleanSizes(sizes);
        if (!Number.isInteger(total) || total <= 0 || valid.length === 0) return null;

        const table = _fewestBarsTable(total, valid);
        if (table.cost[total] === Infinity) return null;
        const fewestSingles = table.singles(total);

        // A mirror: each side is `half` panels wide, plus an optional centre
        // bar (an odd width needs one of an odd size).
        let best = null;
        for (const centre of [0, ...valid]) {
            const rest = total - centre;
            if (rest < 0 || rest % 2 !== 0) continue;
            const half = rest / 2;
            if (table.cost[half] === Infinity) continue;
            const singles = 2 * table.singles(half) + (centre === 1 ? 1 : 0);
            if (singles !== fewestSingles) continue;
            const count = 2 * table.bars(half) + (centre ? 1 : 0);
            if (!best || count < best.count) best = { count, centre, half };
        }

        if (best) {
            // Smallest bar outermost, largest nearest the middle.
            const side = _barsFor(best.half, table).sort((a, b) => a - b);
            const mirrored = [...side].reverse();
            return [...side, ...(best.centre ? [best.centre] : []), ...mirrored];
        }
        const bars = _barsFor(total, table);
        const singles = bars.filter(b => b === 1);
        return [...singles, ...arrangeSymmetric(bars.filter(b => b !== 1))];
    }

    // Dragging bar `index` by `deltaPanels` panels (negative = left): the
    // bars keep their sizes and only change places, so the wall stays
    // covered edge to edge. The dragged bar swaps with a neighbour once its
    // leading edge passes that neighbour's middle, so a long bar can still
    // reach either end of the wall.
    function moveBar(bars, index, deltaPanels) {
        return moveBarWithSlot(bars, index, deltaPanels).bars;
    }

    // The same, with where the dragged bar ended up: { bars, slot }.
    function moveBarWithSlot(bars, index, deltaPanels) {
        if (!Array.isArray(bars) || !Number.isInteger(index) || index < 0 || index >= bars.length) {
            return { bars, slot: index };
        }
        const span = bars[index];
        let left = 0;
        for (let i = 0; i < index; i++) left += bars[i];
        const dragLeft = left + deltaPanels;
        const dragRight = dragLeft + span;
        let slot = 0;
        let pos = 0;
        for (let i = 0; i < bars.length; i++) {
            const mid = pos + bars[i] / 2;
            pos += bars[i];
            if (i === index) continue;
            // a bar to the left stays left until the dragged bar's left edge
            // crosses its middle; a bar to the right joins the left once the
            // dragged bar's right edge crosses its middle
            if (i < index ? dragLeft >= mid : dragRight > mid) slot++;
        }
        const rest = bars.filter((_, i) => i !== index);
        return { bars: [...rest.slice(0, slot), span, ...rest.slice(slot)], slot };
    }

    // How many bars in all, and how many of each size, across any number of
    // screens' bar lists: { total, bySize: { 4: 6, 2: 2 } }.
    function tally(barLists) {
        const bySize = {};
        let total = 0;
        for (const bars of barLists || []) {
            for (const size of Array.isArray(bars) ? bars : []) {
                if (!Number.isInteger(size) || size <= 0) continue;
                bySize[size] = (bySize[size] || 0) + 1;
                total++;
            }
        }
        return { total, bySize };
    }

    // Dragging the edge between bars[boundary] and bars[boundary + 1] by
    // `deltaPanels` (positive = to the right): the bar the edge belongs to
    // grows and the one beside it shrinks by the same whole number of
    // panels, so the wall stays covered. Neither bar goes under 1 panel or
    // over maxSize; the move stops at the limit.
    function resizeBoundary(bars, boundary, deltaPanels, maxSize = 6) {
        if (!Array.isArray(bars) || !Number.isInteger(boundary) || boundary < 0 || boundary >= bars.length - 1) return bars;
        const a = bars[boundary];
        const b = bars[boundary + 1];
        const lo = Math.max(1 - a, b - maxSize);
        const hi = Math.min(maxSize - a, b - 1);
        if (lo > hi) return bars;
        const d = Math.max(lo, Math.min(hi, Math.round(deltaPanels)));
        if (!d) return bars;
        const out = bars.slice();
        out[boundary] = a + d;
        out[boundary + 1] = b - d;
        return out;
    }

    // What a bar of this many panels is called: single, double, triple,
    // then 4-way, 5-way, 6-way.
    function sizeWord(size) {
        return { 1: 'Single', 2: 'Double', 3: 'Triple' }[size] || `${size}-way`;
    }

    // The bar's name wherever it is listed: the pull list, the binder.
    function barName(size, kind) {
        return `${kind === 'footer' ? 'Footer' : 'Header'} Bar - ${sizeWord(size)}`;
    }

    return { cleanSizes, arrangeSymmetric, isSymmetric, fitBars, moveBar, moveBarWithSlot, resizeBoundary, tally, sizeWord, barName };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = RiggingMath;
