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

    // How many panels wide the wall stands: its columns, or its rows once it
    // is turned a quarter (the footprint the bars hang on, canvas.js
    // _layerRotationGeom swaps the same two angles).
    function wallPanels(columns, rows, rotation) {
        const deg = (((Number(rotation) || 0) % 360) + 360) % 360;
        return Number(deg === 90 || deg === 270 ? rows : columns) || 0;
    }

    // How many panels a row of bars covers.
    function barPanels(bars) {
        return (Array.isArray(bars) ? bars : []).reduce((sum, n) => sum + (Number(n) || 0), 0);
    }

    // Do these bars cover a wall this many panels wide, edge to edge? An
    // empty row is no claim on the wall, so it never fails.
    function barsFit(bars, width) {
        const panels = barPanels(bars);
        return panels === 0 || panels === width;
    }

    // Dragging the edge between bars[boundary] and bars[boundary + 1] by
    // `deltaPanels` (positive = to the right): the bar the edge belongs to
    // grows and the one beside it shrinks by the same whole number of
    // panels, so the wall stays covered. Neither bar goes under 1 panel or
    // over maxSize; the move stops at the limit.
    function resizeBoundary(bars, boundary, deltaPanels, maxSize = 4) {
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
    // quad. A wider one, saved before the picker stopped at 4, reads 5-way.
    function sizeWord(size) {
        return { 1: 'Single', 2: 'Double', 3: 'Triple', 4: 'Quad' }[size] || `${size}-way`;
    }

    // The bar's name wherever it is listed: the pull list, the binder.
    function barName(size, kind) {
        return `${kind === 'footer' ? 'Footer' : 'Header'} Bar - ${sizeWord(size)}`;
    }

    // ---- placed bars --------------------------------------------------------
    //
    // A row of bars is stored as its sizes (riggingBars) and, only when the
    // bars do not run end to end from the wall's left edge, the panel each
    // one starts at (riggingBarStarts, the same length). A show saved before
    // Custom has no starts, so it reads exactly as it did. In here a row is
    // a list of { start, size }, start in panels from the row's left edge,
    // sorted left to right.

    // The stored arrays as placed bars. Starts that do not match the sizes
    // (missing, the wrong length, not whole panels) are ignored: the bars
    // then run end to end from panel 0, as every row did before.
    function placedOf(bars, starts) {
        const sizes = Array.isArray(bars) ? bars : [];
        const ok = Array.isArray(starts) && starts.length === sizes.length
            && starts.every(s => Number.isInteger(s) && s >= 0);
        let at = 0;
        const out = [];
        sizes.forEach((raw, i) => {
            const size = Number(raw);
            const start = ok ? starts[i] : at;
            at = start + (Number.isFinite(size) ? size : 0);
            if (Number.isInteger(size) && size > 0) out.push({ start, size });
        });
        return out.sort((a, b) => a.start - b.start);
    }

    // Placed bars as the two stored arrays: { bars, starts }, starts null
    // when the bars run end to end from panel 0 (the shape every older show
    // has, so it saves the way it always did).
    function storeOf(placed) {
        const list = (placed || []).filter(b => b && Number.isInteger(b.size) && b.size > 0)
            .map(b => ({ start: Math.round(b.start), size: b.size }))
            .sort((a, b) => a.start - b.start);
        let at = 0;
        let flush = true;
        for (const b of list) {
            if (b.start !== at) flush = false;
            at = b.start + b.size;
        }
        return { bars: list.map(b => b.size), starts: flush ? null : list.map(b => b.start) };
    }

    // `adds` laid into the row: every bar they overlap goes, the rest stay.
    function placeBars(placed, adds) {
        const fresh = (adds || []).filter(b => Number.isInteger(b.size) && b.size > 0);
        const hits = (b) => fresh.some(n => n.start < b.start + b.size && b.start < n.start + n.size);
        return [...(placed || []).filter(b => !hits(b)), ...fresh.map(b => ({ start: b.start, size: b.size }))]
            .sort((a, b) => a.start - b.start);
    }

    // A click on panel `panel`: one bar of `size` starting there, moved in
    // just far enough to stay on a row `width` panels wide. None when the
    // bar is wider than the row.
    function barsForClick(panel, size, width) {
        if (!Number.isInteger(size) || size <= 0 || !(width >= size)) return [];
        const start = Math.max(0, Math.min(Math.round(panel), width - size));
        return [{ start, size }];
    }

    // A drag from panel `from` to panel `to`: as many whole bars of `size`
    // as the dragged span holds, laid from the panel the drag started on
    // toward the mouse. A leftover shorter than a bar stays empty. A drag
    // shorter than one bar is a click.
    function barsForDrag(from, to, size, width) {
        if (!Number.isInteger(size) || size <= 0 || !(width >= size)) return [];
        const a = Math.max(0, Math.min(width - 1, Math.round(from)));
        const b = Math.max(0, Math.min(width - 1, Math.round(to)));
        const n = Math.floor((Math.abs(b - a) + 1) / size);
        if (n < 1) return barsForClick(a, size, width);
        const out = [];
        for (let k = 0; k < n; k++) {
            out.push(b >= a ? { start: a + k * size, size } : { start: a + 1 - (k + 1) * size, size });
        }
        return out.sort((x, y) => x.start - y.start);
    }

    // The index of the bar covering panel `panel`, or -1.
    function barAtPanel(placed, panel) {
        return (placed || []).findIndex(b => panel >= b.start && panel < b.start + b.size);
    }

    // The edge between bar i and bar i + 1 dragged by `deltaPanels`: the
    // same trade as resizeBoundary, for two bars that touch. Bars with a
    // gap between them have no shared edge and stay as they are.
    function resizeEdgeAt(placed, i, deltaPanels, maxSize = 4) {
        const list = placed || [];
        if (!Number.isInteger(i) || i < 0 || i >= list.length - 1) return list;
        const a = list[i], b = list[i + 1];
        if (a.start + a.size !== b.start) return list;
        const sizes = resizeBoundary([a.size, b.size], 0, deltaPanels, maxSize);
        if (sizes[0] === a.size) return list;
        const out = list.map(x => ({ start: x.start, size: x.size }));
        out[i].size = sizes[0];
        out[i + 1] = { start: a.start + sizes[0], size: sizes[1] };
        return out;
    }

    // Bar i dragged by its middle: it swaps places with its neighbours the
    // way moveBarWithSlot does, among the bars that touch it end to end, so
    // a gap in a custom row stays where it is. { placed, index } with where
    // the bar landed.
    function moveInBlock(placed, i, deltaPanels) {
        const list = (placed || []).map(x => ({ start: x.start, size: x.size }));
        if (!Number.isInteger(i) || i < 0 || i >= list.length) return { placed: list, index: i };
        let lo = i, hi = i;
        while (lo > 0 && list[lo - 1].start + list[lo - 1].size === list[lo].start) lo--;
        while (hi < list.length - 1 && list[hi].start + list[hi].size === list[hi + 1].start) hi++;
        const block = list.slice(lo, hi + 1).map(b => b.size);
        const moved = moveBarWithSlot(block, i - lo, deltaPanels);
        let at = list[lo].start;
        moved.bars.forEach((size, k) => { list[lo + k] = { start: at, size }; at += size; });
        return { placed: list, index: lo + moved.slot };
    }

    // ---- rows across grouped screens -----------------------------------------
    //
    // Members of a group that stand edge to edge in a row, the same panel
    // width, their bar edges lined up (the top edges for a header, the
    // bottom edges for a footer), carry ONE row of bars: a bar may straddle
    // the seam. `rects` are [{ id, x, y, w, h, panels }] in one frame (Show
    // Look workspace pixels). Returns the runs, each left to right:
    // [{ ids, offsets, panels, width }].
    function runsOf(rects, side, tol = 1) {
        const list = (rects || []).filter(r => r && r.panels > 0 && r.w > 0)
            .slice().sort((a, b) => a.x - b.x || a.y - b.y);
        const edgeY = (r) => (side === 'footer' ? r.y + r.h : r.y);
        const runs = [];
        for (const r of list) {
            const unit = r.w / r.panels;
            const run = runs.find(u => {
                const last = u.rects[u.rects.length - 1];
                return Math.abs(last.x + last.w - r.x) <= tol
                    && Math.abs(edgeY(last) - edgeY(r)) <= tol
                    && Math.abs(last.w / last.panels - unit) <= tol;
            });
            if (run) run.rects.push(r); else runs.push({ rects: [r] });
        }
        return runs.map(u => {
            let at = 0;
            const offsets = u.rects.map(r => { const o = at; at += r.panels; return o; });
            return { ids: u.rects.map(r => r.id), offsets, panels: u.rects.map(r => r.panels), width: at };
        });
    }

    // Which member of a run a bar starting at `start` belongs to (it is
    // stored, and counted, on the member it starts on): the member's index.
    function ownerIndex(run, start) {
        let k = 0;
        for (let i = 0; i < run.offsets.length; i++) if (start >= run.offsets[i]) k = i;
        return k;
    }

    // A run's placed bars handed back to its members, each in the member's
    // own panels: [placed per member, in run order].
    function distribute(run, placed) {
        const out = run.ids.map(() => []);
        for (const b of placed || []) {
            const k = ownerIndex(run, b.start);
            out[k].push({ start: b.start - run.offsets[k], size: b.size });
        }
        return out;
    }

    // The bars of a row over one of its screens (`offset`, `panels` wide),
    // each cut at that screen's edges, in its own panels: what a copy of
    // the screen alone keeps of a row that crosses a group's seam.
    function clipTo(placed, offset, panels) {
        const lo = Number(offset) || 0;
        const hi = lo + (Number(panels) || 0);
        return (placed || [])
            .filter(b => b && b.size > 0 && b.start < hi && b.start + b.size > lo)
            .map(b => {
                const s = Math.max(b.start, lo);
                return { start: s - lo, size: Math.min(b.start + b.size, hi) - s };
            })
            .sort((a, b) => a.start - b.start);
    }

    // What is wrong with a row, or null when nothing is. `spans` are the
    // members' [offset, panels]; `custom` a row laid by hand.
    //   Auto row    every member with a bar over it is covered edge to edge,
    //               nothing overlaps or runs past the row's end (one screen
    //               alone: the bars add up to the wall, the old rule).
    //   Custom row  gaps are fine; only a bar past the row's end, or two
    //               bars on one panel, is wrong.
    // { have, wall, past, overlap, gap }: `have` the bars' panels, `wall`
    // the panels of the members they claim, `past` panels past the end.
    function rowProblem(placed, width, spans, custom) {
        const list = (placed || []).slice().sort((a, b) => a.start - b.start);
        if (!list.length) return null;
        const end = Math.max(...list.map(b => b.start + b.size));
        const past = Math.max(0, end - width);
        let overlap = false;
        for (let i = 1; i < list.length; i++) {
            if (list[i].start < list[i - 1].start + list[i - 1].size) overlap = true;
        }
        const have = list.reduce((s, b) => s + b.size, 0);
        const covers = (p) => list.some(b => p >= b.start && p < b.start + b.size);
        const claimed = (spans && spans.length ? spans : [[0, width]])
            .filter(([o, n]) => list.some(b => b.start < o + n && o < b.start + b.size));
        const wall = claimed.reduce((s, [, n]) => s + n, 0);
        let gap = false;
        if (!custom) {
            for (const [o, n] of claimed) {
                for (let p = o; p < o + n; p++) if (!covers(p)) { gap = true; break; }
            }
        }
        if (!past && !overlap && !gap) return null;
        return { have, wall, past, overlap, gap, custom: !!custom };
    }

    return { cleanSizes, arrangeSymmetric, isSymmetric, fitBars, moveBar, moveBarWithSlot, resizeBoundary, tally, sizeWord, barName,
             wallPanels, barPanels, barsFit,
             placedOf, storeOf, placeBars, barsForClick, barsForDrag, barAtPanel, resizeEdgeAt, moveInBlock,
             runsOf, ownerIndex, distribute, clipTo, rowProblem };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = RiggingMath;
