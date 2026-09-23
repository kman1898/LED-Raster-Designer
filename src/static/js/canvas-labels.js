// canvas.js mixin: Layer labels and offsets, cabinet-ID numbers, and the group numbering plan / position lattice they read.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.

// A cabinet id lives inside ITS OWN cabinet, whatever the label size says -
// "cabinet ids should not be able to extend to the panel next to it even if
// the text is too large" (2026-09-15). The id's box is the cabinet inset by
// this share of its smaller side (never less than one raster px); at the
// top-left position the corner keeps its old 5 px stand-off where that is
// smaller than the pad, so a big cabinet's corner id sits where it always
// did. An id that would paint smaller than CABINET_ID_FLOOR_PX on the
// bitmap it lands on is not drawn: a 3 px smear reads as nothing, and hides
// the cabinet's colour under it. The floor is judged at the DRAW scale
// (read off the ctx), not the working view's zoom, so an export at scale 1
// still prints the ids a zoomed-out workspace does not show.
const CABINET_ID_PAD = 0.12;
const CABINET_ID_CORNER = 5;
const CABINET_ID_FLOOR_PX = 5;

Object.assign(CanvasRenderer.prototype, {
    // ── Screen groups (v0.11.0): cabinet IDs that run across the group ────
    //
    // A group is ONE screen built from more than one layer, so its cabinet IDs
    // have to read as one screen too. Per layer they are grid indices, so the
    // second member restarts at A1 / 1 and the wall carries two cabinets
    // labelled A1 - a tech reading the map cannot tell them apart.
    //
    // Both families of ID are re-derived from the cabinet's ACTUAL POSITION on
    // the wall, pooled across every member, so the label is what someone
    // standing in front of the wall counting cabinets would say and the member
    // boundaries are invisible:
    //
    //   column-row / row-column / row-col
    //       the column index is the rank of the cabinet's column among the
    //       group's distinct column positions (rows likewise) - not the
    //       member's own grid index, and not that index plus an offset:
    //       members have different cabinet sizes, so "column 3" is a different
    //       place on the wall in each of them.
    //   sequential (panel.number)
    //       reading order over the whole wall, top-to-bottom then
    //       left-to-right, rather than member after member.
    //
    // The position ranked is the cabinet's SLOT origin (the smallest x in its
    // member's column, the smallest y in its member's row), not its own x/y,
    // because a half-tile is anchored inside its slot (_build_panels) and
    // would otherwise rank as a column of its own.
    //
    // The cost of ranking positions: with mixed cabinet sizes the distinct
    // positions do not line up between members. A 128 px member contributes
    // x = 0, 128, 256... and a 64 px member 0, 64, 128..., so the pooled
    // letters advance at every cabinet edge on the wall and the big member's
    // own letters skip (A, C, E...). That is the honest reading - the letters
    // count places on the wall, which is what the person counting counts.
    //
    // Two cabinets can share a column AND a row rank only when they share a
    // slot origin, i.e. when members physically overlap. Uniqueness is a hard
    // requirement, so the plan CHECKS it rather than trusting the geometry: a
    // grid style that cannot label this group uniquely is dropped for the
    // whole group in favour of the wall's sequential numbers (one consistent
    // map, every cabinet distinct) rather than drawing two A1s or inventing a
    // sub-number.
    //
    // Hidden and blank cabinets keep today's treatment exactly: both consume a
    // number (panel.number counts every grid cell), blank ones are labelled,
    // hidden ones are not - so hidden cabinets are ranked too, and their
    // columns and rows still take their place.
    //
    // v0.11.0: positions are ranked where the cabinets DRAW, so a member
    // carrying a screen rotation is numbered in the order the eye follows it
    // across the wall rather than by where its unrotated grid would have sat.
    // See getPositionLattice.
    _groupNumberingMembers(layer) {
        const g = this._groupForLayer(layer);
        if (!g || !window.app || typeof window.app.getGroupMembers !== 'function') return [];
        const cid = this._effectiveLayerCanvasId(layer);
        // Deliberately NOT filtered on `visible`, unlike _groupDrawnMembers:
        // hiding one member must not renumber another member's cabinets. Same
        // canvas only - a position from another canvas's workspace cannot be
        // ranked against these.
        return window.app.getGroupMembers(g).filter(m => m
            && (m.type || 'screen') === 'screen'
            && Array.isArray(m.panels)
            && this._effectiveLayerCanvasId(m) === cid);
    },

    // THE WALL LATTICE - a set of members' separate grids collapsed into one
    // ordered set of column and row POSITIONS. This is the rank-position
    // mapping step 5 built for continuous cabinet numbering, extracted so it
    // has exactly ONE implementation.
    //
    // Two members of one wall do not share a grid: a 1m cabinet's row 1 and a
    // 0.5m cabinet's row 1 are different physical heights, so anything that has
    // to run ACROSS the wall - the cabinet IDs, and now a pattern applied to a
    // selection that starts on one member and finishes on the next - is
    // meaningless if it is ordered by the panels' own row/col indices. It has
    // to be ordered by WHERE EACH CABINET SITS. Every distinct column x and row
    // y any member occupies is pooled and ranked, and each cabinet then reports
    // the rank of its own slot; a cabinet spanning two lattice rows ranks by
    // its own top-left, exactly as step 5 numbers it.
    //
    // WHO CALLS IT. _groupNumberingPlan below (the cabinet IDs) and
    // app-power.js's cross-member flow patterns, through
    // `window.canvasRenderer.getPositionLattice(...)`. It lives on the renderer
    // because the ranking needs getLayerRenderOffset - two members can carry
    // different Show Look offsets, and Data Flow / Power draw at the SHOW
    // position. The canvas workspace translate is shared by every member of a
    // path scope, so it cancels out of a ranking and is deliberately left out.
    // Two copies of this would eventually disagree, and a serpentine that
    // zig-zags the wall in a different order than the IDs read is worse than no
    // serpentine at all.
    //
    //   members                    the ranked members, in the order given
    //   indexOfLayer(layerOrId)    that member's index, or -1
    //   colOfMember(index, panel)  rank by member index, when the caller
    //   rowOfMember(index, panel)  already knows it
    //   colOf(layerOrId, panel)    the cabinet's lattice column rank
    //   rowOf(layerOrId, panel)    the cabinet's lattice row rank
    //   compare(a, b)              reading order over {layer, panel} pairs
    //
    // colOf/rowOf take the panel's OWN layer, because the same {row, col} means
    // a different place on the wall in each member - that is the entire point.
    // The panel's own index is the fallback for a panel whose layer is not in
    // the list, so a caller handing over something outside the scope degrades
    // to today's behaviour rather than throwing mid-render or returning NaN.
    //
    // A single-member list is meaningful and ranks that one screen's own slots:
    // for a uniform grid the ranks then equal the panels' own indices, which is
    // why an ungrouped screen can go through the same code and come out with
    // the order it has always had.
    //
    // ROTATION. Positions are ranked where each cabinet is DRAWN, through that
    // member's own draw frame (_layerDrawFrame / _drawnPanelRect) - the same
    // mapping the marquee, the arrow handoff and the selection highlight use. A
    // wall with one member turned 90 therefore numbers, and serpentines, in the
    // order somebody walking the wall reads it. Ranking in unrotated space (what
    // this did before v0.11.0) produced an order that existed nowhere on site.
    getPositionLattice(members) {
        const list = (members || []).filter(m => m && Array.isArray(m.panels));

        // Slot origins per member, in the space this view DRAWS in: each
        // cabinet's rect through that member's own draw frame, which carries its
        // rotation and its Show Look offset. The render offset is 0 on Cabinet
        // ID today; it matters in the views that DO shift layers (Data Flow /
        // Power carry Show Look offsets), which is where the flow patterns read
        // this from.
        //
        // v0.11.0: a 90/270 turn trades a member's axes - its rows run along the
        // wall's x - so the cabinets are grouped into drawn columns and rows by
        // _drawnColKey / _drawnRowKey before their positions are pooled. Without
        // it a rotated member ranks where its grid sits rather than where it
        // draws, and a serpentine enters it at a corner that is nowhere on site.
        // The frame is hoisted per member: it is O(panels) to build.
        const key = v => Math.round(v * 100);   // pixel coords; kills float noise
        const slots = list.map(m => {
            const frame = this._layerDrawFrame(m);
            const cols = new Map();
            const rows = new Map();
            (m.panels || []).forEach(p => {
                const r = this._drawnPanelRect(frame, p);
                const ck = this._drawnColKey(frame, p);
                const rk = this._drawnRowKey(frame, p);
                const cx = cols.get(ck);
                if (cx === undefined || r.x < cx) cols.set(ck, r.x);
                const ry = rows.get(rk);
                if (ry === undefined || r.y < ry) rows.set(rk, r.y);
            });
            return { cols, rows, frame };
        });

        // Every distinct column position on the wall, in order, then rows.
        // Pooled across all N members, not just a pair.
        const rankPositions = maps => {
            const seen = new Set();
            const values = [];
            maps.forEach(map => map.forEach(v => {
                if (seen.has(key(v))) return;
                seen.add(key(v));
                values.push(v);
            }));
            values.sort((a, b) => a - b);
            const ranks = new Map();
            values.forEach((v, i) => ranks.set(key(v), i));
            return ranks;
        };
        const colRanks = rankPositions(slots.map(s => s.cols));
        const rowRanks = rankPositions(slots.map(s => s.rows));

        // The panel's own index is the fallback for a panel that is not in the
        // member we were handed - what a caller outside the scope wants, and
        // what keeps a stale one from getting NaN.
        const colOfMember = (mi, panel) => {
            const s = slots[mi];
            const x = (s && panel) ? s.cols.get(this._drawnColKey(s.frame, panel)) : undefined;
            const r = (x === undefined) ? undefined : colRanks.get(key(x));
            return (r === undefined) ? (panel ? panel.col : 0) : r;
        };
        const rowOfMember = (mi, panel) => {
            const s = slots[mi];
            const y = (s && panel) ? s.rows.get(this._drawnRowKey(s.frame, panel)) : undefined;
            const r = (y === undefined) ? undefined : rowRanks.get(key(y));
            return (r === undefined) ? (panel ? panel.row : 0) : r;
        };

        // Layer -> member index, by id so a caller holding a stale object
        // reference (or just an id) still lands on the right member.
        const byId = new Map();
        list.forEach((m, i) => byId.set(m.id, i));
        const indexOfLayer = target => {
            if (target === null || target === undefined) return -1;
            const id = (typeof target === 'object') ? target.id : target;
            const i = byId.get(id);
            return (i === undefined) ? -1 : i;
        };

        const colOf = (panelLayer, panel) => colOfMember(indexOfLayer(panelLayer), panel);
        const rowOf = (panelLayer, panel) => rowOfMember(indexOfLayer(panelLayer), panel);

        return {
            members: list,
            indexOfLayer,
            colOfMember,
            rowOfMember,
            colOf,
            rowOf,
            // Reading order over the whole wall. Row rank then column rank IS
            // ranking by slot position; the member index and then the member's
            // own grid position break any remaining tie, so the order is stable
            // and follows the order the members were given in. This is the
            // comparator the cabinet numbers below are assigned with, because
            // it is literally the same one.
            compare: (a, b) => {
                const ra = rowOf(a.layer, a.panel);
                const rb = rowOf(b.layer, b.panel);
                const ca = colOf(a.layer, a.panel);
                const cb = colOf(b.layer, b.panel);
                return (ra - rb) || (ca - cb)
                    || (indexOfLayer(a.layer) - indexOfLayer(b.layer))
                    || (a.panel.row - b.panel.row) || (a.panel.col - b.panel.col);
            },
        };
    },

    // The lattice for `layer`'s GROUP: the members this canvas ranks together,
    // in the group's own order. Null when `layer` is not in a group of two or
    // more here, which is what keeps every single-screen caller - the cabinet
    // numbering below included - on the path it always took.
    getGroupLattice(layer) {
        const members = this._groupNumberingMembers(layer);
        if (members.length < 2) return null;
        return this.getPositionLattice(members);
    },

    // The numbering `layer` should draw with, or null when it is not in a
    // group of two or more here - and then renderCabinetIDNumbers takes
    // exactly the path it always took.
    _groupNumberingPlan(layer) {
        const lattice = this.getGroupLattice(layer);
        if (!lattice) return null;
        const members = lattice.members;
        const mine = members.findIndex(m => m.id === layer.id);
        if (mine < 0) return null;

        // Sequential = reading order over the whole wall, which is exactly the
        // lattice's own comparator.
        const cells = [];
        members.forEach((m, mi) => (m.panels || []).forEach(p => cells.push({
            mi, panel: p, layer: m,
            col: lattice.colOf(m, p), row: lattice.rowOf(m, p),
        })));
        cells.sort(lattice.compare);
        const numbers = new Map();
        cells.forEach((c, i) => numbers.set(`${c.mi}:${c.panel.row},${c.panel.col}`, i + 1));

        // Can a grid style label this group uniquely? Only the cabinets that
        // actually draw a label are checked - a hidden cabinet draws none, so
        // it cannot collide with anything.
        const gridSeen = new Set();
        let gridUnique = true;
        cells.forEach(c => {
            if (!gridUnique || c.panel.hidden) return;
            const k = `${c.col},${c.row}`;
            if (gridSeen.has(k)) gridUnique = false;
            else gridSeen.add(k);
        });

        return {
            gridUnique,
            // One style for the whole wall, the FIRST member's, the same rule
            // _groupLabelPlan uses for the label config. Screen Info already
            // propagates cabinetIdStyle across a group, so this only bites on
            // members that disagreed before they were grouped - and there it
            // matters, because one member drawing A1 as column-row while
            // another draws A1 as row-column is a duplicate ID again.
            style: members[0].cabinetIdStyle || 'column-row',
            colOf: panel => lattice.colOf(layer, panel),
            rowOf: panel => lattice.rowOf(layer, panel),
            numberOf: panel => numbers.get(`${mine}:${panel.row},${panel.col}`) || panel.number,
        };
    },

    renderCabinetIDNumbers(layer) {
        if (!layer.show_numbers) return;
        
        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        const numberSize = layer.number_size || 24;
        const cabinetIdStyle = layer.cabinetIdStyle || 'column-row';
        const cabinetIdPosition = layer.cabinetIdPosition || 'center';
        const cabinetIdColor = layer.cabinetIdColor || '#ffffff';

        // v0.11.0: in a screen group the IDs run across the whole wall - see
        // _groupNumberingPlan. Null for an ungrouped layer, and every line
        // below then reads exactly as it always did.
        const plan = this._groupNumberingPlan(layer);
        // A grid style that cannot label this group uniquely is dropped for
        // the whole group in favour of the wall's sequential numbers -
        // 'sequential' is not a stored style, it is the name of the switch's
        // default arm below.
        const idStyle = plan
            ? (plan.gridUnique ? plan.style : 'sequential')
            : cabinetIdStyle;

        const ctx = this.ctx;
        ctx.fillStyle = cabinetIdColor;
        const centred = cabinetIdPosition === 'center';

        // Position-based settings
        if (centred) {
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
        } else {
            // top-left
            ctx.textAlign = 'left';
            ctx.textBaseline = 'top';
        }

        // The font is set per cabinet (each fits its own box), so set it only
        // when the size actually changes - on a wall of equal cabinets and
        // equal-width ids that is once.
        const family = projectFontFamily();
        let fontPx = -1;
        const setFont = (px) => {
            if (px === fontPx) return;
            fontPx = px;
            ctx.font = `bold ${px}px ${family}`;
        };
        // How the id's glyphs stand about their anchor, in world units, at
        // the current font: the extent above the anchor line and below it.
        // Centred, the anchor is the cabinet's centre, so the taller of the
        // two sides decides the fit; at the corner the anchor is the top
        // line and the glyphs hang below it.
        const extentOf = (text, px) => {
            const m = ctx.measureText(text);
            let asc = m.actualBoundingBoxAscent;
            let desc = m.actualBoundingBoxDescent;
            if (!Number.isFinite(asc) || !Number.isFinite(desc)) {
                asc = centred ? px / 2 : 0;
                desc = centred ? px / 2 : px;
            }
            return { w: m.width, asc, desc,
                     h: centred ? 2 * Math.max(asc, desc) : asc + desc };
        };
        // Bitmap pixels per world unit, read off the ctx so the floor is
        // judged where the ink lands: the workspace at its zoom, the export
        // canvas at its export scale.
        let drawScale = 1;
        try {
            const m = ctx.getTransform();
            drawScale = Math.hypot(m.a, m.b) || 1;
        } catch (e) { drawScale = 1; }

        // First pass: every drawn cabinet's id and its inner box. The size is
        // ONE per screen - the user's size shrunk until the widest and the
        // tallest id on the layer fit the smallest inner box on the layer
        // (a half-tile's, where there is one) - so neighbouring cabinets
        // never carry two sizes of type. Simpler than a size per cabinet
        // size, and a half-tile is rare enough to pay for.
        const sites = [];
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            if (panel.x >= this.rasterWidth || panel.y >= this.rasterHeight) return;
            
            // Calculate label based on style
            let label = '';
            const col = plan ? plan.colOf(panel) : panel.col;  // 0-indexed
            const row = plan ? plan.rowOf(panel) : panel.row;  // 0-indexed

            switch (idStyle) {
                case 'column-row':
                    // A1, B1, C1... (column letter + row number)
                    // Reads top-to-bottom by columns
                    label = this.getColumnLetter(col) + (row + 1);
                    break;
                    
                case 'row-column':
                    // A1, A2, A3... (row letter + column number)
                    // Reads left-to-right by rows
                    label = this.getColumnLetter(row) + (col + 1);
                    break;
                    
                case 'row-col':
                    // 1,1  1,2  1,3... (row number, column number)
                    // Reads left-to-right with comma notation
                    label = `${row + 1},${col + 1}`;
                    break;
                    
                default:
                    // Fallback to sequential - the wall's reading order in a
                    // group, the layer's own panel numbers on their own.
                    label = plan ? plan.numberOf(panel) : panel.number;
            }
            
            const text = String(label);

            // The id's box: the cabinet as DRAWN (a half-tile is half as
            // wide or tall, and its panel.width/height say so), inset by the
            // pad - the corner id keeps its stand-off from the top-left where
            // that is the smaller.
            const pw = panel.width, ph = panel.height;
            const pad = Math.max(1, CABINET_ID_PAD * Math.min(pw, ph));
            const inset = centred ? pad : Math.min(CABINET_ID_CORNER, pad);
            // The cabinet's own box, for the registry, in the frame the id is
            // drawn in - a rotated screen's box turns with it, exactly as
            // the id's does.
            if (this.labelProbe) this._noteLabelBox('cabinet', text, panel.x, panel.y, pw, ph);
            sites.push({ panel, text, inset, innerW: pw - inset - pad, innerH: ph - inset - pad });
        });

        // The layer's one size.
        // 1. the user's size, shrunk until the widest id fits the narrowest
        //    inner box and the tallest the shortest. Width and height scale
        //    with the font, so one measurement at the user's size gives the
        //    fitting size; a second measurement at that size catches the
        //    hinting a fractional font adds, and pulls the size in once more
        //    if it has to.
        let innerW = Infinity, innerH = Infinity;
        for (const s of sites) {
            innerW = Math.min(innerW, s.innerW);
            innerH = Math.min(innerH, s.innerH);
        }
        if (!sites.length || !(innerW > 0) || !(innerH > 0)) {
            this.ctx.restore();
            return;
        }
        const widest = (px) => {
            setFont(px);
            let w = 0, h = 0, wide = sites[0].text, tall = sites[0].text;
            for (const s of sites) {
                const e = extentOf(s.text, px);
                if (e.w > w) { w = e.w; wide = s.text; }
                if (e.h > h) { h = e.h; tall = s.text; }
            }
            return { w, h, wide, tall };
        };
        let ext = widest(numberSize);
        let px = numberSize;
        if (ext.w > innerW) px = Math.min(px, numberSize * innerW / ext.w);
        if (ext.h > innerH) px = Math.min(px, numberSize * innerH / ext.h);
        ext = widest(px);
        if (ext.w > innerW || ext.h > innerH) {
            px *= Math.min(innerW / ext.w, innerH / ext.h);
            setFont(px);
        }
        // 2. below the legibility floor ON THE BITMAP, draw nothing.
        if (px * drawScale < CABINET_ID_FLOOR_PX) {
            this.ctx.restore();
            return;
        }

        // Second pass: paint every id at the layer's size.
        for (const s of sites) {
            const panel = s.panel;
            const pw = panel.width, ph = panel.height;
            const e = extentOf(s.text, px);
            let textX, textY;
            if (centred) {
                textX = panel.x + pw / 2;
                textY = panel.y + ph / 2;
            } else {
                // top-left with small padding
                textX = panel.x + s.inset;
                textY = panel.y + s.inset;
            }
            this._noteLabelBox('cabinetId', s.text,
                               centred ? textX - e.w / 2 : textX, textY - e.asc,
                               e.w, e.asc + e.desc, { size: px });

            // 3. and whatever the measurement said, the ink stops at the
            //    cabinet's edge: the clip is in the frame the cabinet was
            //    drawn in, so a rotated screen's clip turns with it.
            ctx.save();
            ctx.beginPath();
            ctx.rect(panel.x, panel.y, pw, ph);
            ctx.clip();
            this._fillText(s.text, this.snap(textX), this.snap(textY));
            ctx.restore();
        }

        this.ctx.restore();
    },
    
    // Helper function to convert number to letter (0=A, 1=B, ... 25=Z, 26=AA, etc.)
    getColumnLetter(num) {
        let letter = '';
        while (num >= 0) {
            letter = String.fromCharCode(65 + (num % 26)) + letter;
            num = Math.floor(num / 26) - 1;
        }
        return letter;
    },

    // Wrap one line of the screen label onto as many lines as it needs to
    // stay inside `maxWidth`, measured with the font CURRENTLY set on the
    // ctx, without shrinking the type. Owner, 2026-09-23, on a 7x8 wall of
    // 256 px cabinets whose 150 px port line ran off both edges: "in the
    // example where the screen label runs off the screen we need to double
    // stack it or more aka wrap it".
    //
    // The breaks, in order, each tried only on a piece the level above
    // could not fit:
    //   1. " | "  the bar is dropped; the clauses become lines
    //   2. ", "   the comma stays on the piece it closes ("7 Mains,")
    //   3. " · "  the dot is dropped
    //   4. " "    plain words
    // Each level fills greedily: a line takes as many of its pieces as fit,
    // re-joined the way they were written. A single word wider than the
    // room stays on a line of its own - it may still overflow, and there
    // is nothing sensible to do about that. A line that fits comes back as
    // itself, so a label that fits is drawn exactly as before.
    _wrapLabelLine(text, maxWidth) {
        const s = String(text == null ? '' : text);
        const fits = (t) => this.ctx.measureText(t).width <= maxWidth;
        if (fits(s)) return [s];
        const LEVELS = [
            { sep: ' | ', keep: '', join: ' | ' },
            { sep: ', ', keep: ',', join: ' ' },
            { sep: ' · ', keep: '', join: ' · ' },
            { sep: ' ', keep: '', join: ' ' },
        ];
        const wrap = (t, level) => {
            if (fits(t) || level >= LEVELS.length) return [t];
            const { sep, keep, join } = LEVELS[level];
            const raw = t.split(sep);
            if (raw.length < 2) return wrap(t, level + 1);
            const pieces = raw.map((p, i) => (i < raw.length - 1 ? p + keep : p));
            const out = [];
            const flush = (line) => {
                if (line === '') return;
                if (fits(line)) out.push(line);
                else out.push(...wrap(line, level + 1));
            };
            let current = '';
            pieces.forEach(piece => {
                if (current === '') { current = piece; return; }
                const candidate = current + join + piece;
                if (fits(candidate)) { current = candidate; return; }
                flush(current);
                current = piece;
            });
            flush(current);
            return out;
        };
        return wrap(s, 0);
    },

    // The port line (Data) or circuit line (Power) a GROUP's consolidated
    // label carries, straight from the step-2 roll-up. One authority:
    // renderLayerLabels draws it, and _bothModeGroupNameBox measures it to
    // predict how tall the headline's stack is once it wraps. Null when
    // the view carries no such line for this group.
    _groupCenterInfoLine(gplan, groupTotals) {
        if (!gplan || !groupTotals) return null;
        const cfg = gplan.cfg;
        if (this.viewMode === 'data-flow') {
            if (!cfg.showDataFlowPortInfo) return null;
            // A group's ports come straight out of the roll-up, which adds
            // up whatever each member reports. v0.12: on a group whose
            // members are the same panel that is ONE combined walk's figure,
            // carried by the first member with every other member reporting
            // zero - so this label reads the wall's real port count and not
            // the sum of what its sections would have needed apart. On every
            // other group it is still the members' own requirements summed.
            const mains = groupTotals.portsPrimary;
            const backups = groupTotals.portsBackup;
            if (!(mains > 0)) return null;
            return `${mains} Mains, ${backups} Backups | ${mains + backups} Ports`;
        }
        if (this.viewMode === 'power') {
            if (!cfg.showPowerCircuitInfo) return null;
            // Circuits come through the roll-up the same way ports do, and
            // on a crossing group that is one combined walk's figure for the
            // same reason. Amps do NOT:
            // 200 A at 110 V and 200 A at 208 V are not the same load, so
            // when the members disagree on voltage the roll-up hands back
            // null and the label says so instead of printing a blended
            // figure nobody can act on.
            const circuits = groupTotals.circuits;
            // Split-aware and box-size-aware, per member: socaCountFor
            // reads each screen's own split points and breakout box
            // size (three tails on an L21-30, six on a soca), so the
            // group line agrees with the dock. A peer-served member
            // reports zero circuits and therefore zero boxes.
            let multis = 0;
            if (circuits > 0 && window.app
                    && typeof window.app.socaCountFor === 'function'
                    && typeof window.app.screenCircuitCount === 'function'
                    && typeof window.app.getGroupMembers === 'function') {
                (window.app.getGroupMembers(gplan.group) || []).forEach(m => {
                    if (!m || (m.type || 'screen') !== 'screen') return;
                    multis += window.app.socaCountFor(
                        m, window.app.screenCircuitCount(m));
                });
            } else if (circuits > 0) {
                multis = Math.ceil(circuits / 6);
            }
            if (groupTotals.voltageMismatch) {
                const volts = groupTotals.voltages.filter(v => v > 0).join(' / ');
                return `${multis} Multi, ${circuits} Circuits | Mixed voltage: ${volts} V`;
            }
            const amps1 = groupTotals.amps1ph || 0;
            const amps3 = groupTotals.amps3ph || 0;
            return `${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`;
        }
        return null;
    },

    renderLayerLabels(layer, groupLabelPass = false) {
        // v0.11.0: screen groups draw ONE label for the whole group. The host
        // member draws it (see _groupLabelPlan) and every peer bows out right
        // here - peers keep drawing their own cabinets, only the label
        // consolidates. `plan` is null for an ungrouped layer, so everything
        // below is unchanged for a project without groups.
        // The NAMES switch (_groupNameMode). 'screens' labels the SCREENS:
        // every member draws its whole label - name, sizes, weight, port and
        // circuit figures, info bar - against its own bounds and its own
        // stored offset, byte for byte the ungrouped path, and the group draws
        // no label at all. Drawn the old way (member names, one consolidated
        // figure set at the union) the wall's "W x H" and info bar landed
        // wherever the union's centre and bottom edge happened to fall: over
        // one member's edge, in the gap between sections, in empty raster
        // below the wall - figures that read as nobody's. So a 'screens' wall
        // has no group plan here; only the circle-and-X still spans the group.
        // In 'both' every member draws its own name and the group's
        // consolidated label moves to a separate pass hosted by the last
        // member, carrying the group's name as the wall's headline.
        const nameMode = this._groupNameMode();
        const plan = nameMode === 'screens' ? null : this._groupLabelPlan(layer);
        const memberNamePass = !!plan && nameMode === 'both' && !groupLabelPass;
        // No headline is drawn in 'screens', so no ghost of one may be left
        // to grab from the frame before the switch.
        if (nameMode === 'screens' && layer && layer._groupNameHitRect) {
            layer._groupNameHitRect = null;
        }
        if (memberNamePass && plan.host.id === layer.id) {
            this.renderLayerLabels(layer, true);
        }
        // gplan: the plan the rest of this function acts on. Null during a
        // member's own-name pass, so every line below reads exactly as it
        // does for an ungrouped layer.
        const gplan = memberNamePass ? null : plan;
        if (gplan && gplan.host.id !== layer.id) {
            if (layer._screenNameHitRect) layer._screenNameHitRect = null;
            return;
        }
        // Where the label's settings come from: the layer itself, or the
        // group's first member. This is also the layer that caches the hit
        // rect and stores the screen-name drag offset, so the one label has
        // exactly one owner no matter which member happens to draw it.
        const cfg = gplan ? gplan.cfg : layer;

        // v0.8.7.7: clear any stale screen-name hit rect from a previous
        // render; the if-block below resets it when the label is actually
        // drawn, but layers with showLabelName off (or tab-specific
        // toggles like showLabelNameCabinet) need a clean slate so a
        // mousedown doesn't catch the ghost.
        // The group label pass must NOT touch it: in 'screens'/'both' the
        // rect on cfg belongs to the first member's OWN name, drawn in that
        // member's earlier pass this same frame.
        if (!groupLabelPass) {
            if (layer && layer._screenNameHitRect) layer._screenNameHitRect = null;
            if (cfg._screenNameHitRect) cfg._screenNameHitRect = null;
        }
        // Same hygiene for the group headline's rect ('both'): cleared on
        // every group-label pass and re-set only when the headline is drawn,
        // so switching away from 'both' leaves no ghost to grab.
        if (gplan && cfg._groupNameHitRect) cfg._groupNameHitRect = null;
        if ((layer.type || 'screen') === 'image') {
            return;
        }
        // Note: Clipping for layer occlusion is handled in the render() second pass
        // We only clip to raster bounds here (translate-aware), which
        // intersects with the occlusion clip
        this.ctx.save();
        this._clipToActiveRaster();

        // v0.11.0: a group's label belongs to THE WALL, and _groupUnionBounds
        // measures the wall. The render loop has the ctx turned about the host
        // member's own centre, so cancel that before the label is positioned -
        // otherwise the wall's centre is thrown wherever one member's rotation
        // sends it. The ctx.save above pops it; an ungrouped screen's name still
        // rotates with its screen.
        if (gplan) this._unrotateLayerInPlace(layer);

        // v0.11.0: a group's label is positioned against the union of its
        // members' drawn footprints - the real shape of the wall - not one
        // member's.
        const bounds = gplan ? this._groupUnionBounds(gplan.members, layer) : this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        const bottomY = bounds.y + layerHeight;

        // v0.11.0: and its figures are the COMBINED figures, straight from the
        // step-2 roll-up. No calculation is repeated here.
        // The canvas being drawn is passed through: a group is labelled once
        // per canvas, and its figures must describe the members ON that canvas
        // rather than every member wherever it sits. Without it the label under
        // a two-section wall could carry the weight of a third section drawn
        // somewhere else entirely.
        const groupTotals = (gplan && window.app && typeof window.app.getGroupTotals === 'function')
            ? window.app.getGroupTotals(gplan.group, this._effectiveLayerCanvasId(layer))
            : null;

        // Calculate physical dimensions. For a group the pixel span is the
        // whole wall's but the mm-per-pixel conversion is the FIRST member's
        // pitch - mixed-pitch members have no single answer, and the first
        // member is the one every other label setting comes from.
        const widthMM = (cfg.panel_width_mm || 500) * (layerWidth / (cfg.cabinet_width || 1));
        const heightMM = (cfg.panel_height_mm || 500) * (layerHeight / (cfg.cabinet_height || 1));
        const widthM = widthMM / 1000;
        const heightM = heightMM / 1000;
        const widthFt = widthM * 3.28084;
        const heightFt = heightM * 3.28084;
        
        const ownActivePanels = layer.panels.filter(p => !p.blank && !p.hidden);
        const activePanels = groupTotals ? groupTotals.cabinets : ownActivePanels.length;
        const equivalentPanels = groupTotals ? groupTotals.equivalentPanels : ownActivePanels
            .reduce((sum, p) => {
                if (window.app && typeof window.app.getPanelLoadFactor === 'function') {
                    return sum + window.app.getPanelLoadFactor(layer, p);
                }
                return sum + 1;
            }, 0);
        const panelWeightValue = layer.panel_weight || 20;
        const panelWeightUnit = layer.weight_unit || 'kg';
        const panelWeightKg = panelWeightUnit === 'lb' ? (panelWeightValue / 2.20462) : panelWeightValue;
        // The roll-up already weighs each member against its OWN cabinet, so a
        // group's weight can never be one member's per-cabinet figure applied
        // to everybody's cabinets.
        const totalWeightKg = groupTotals ? groupTotals.weightKg : equivalentPanels * panelWeightKg;
        const totalWeightLb = groupTotals ? groupTotals.weightLb : totalWeightKg * 2.20462;

        // Build labels - Screen Name is separate with white background
        // Per-tab showLabelName: each view mode has its own property, falling back to global → true
        let showLabelName;
        if (this.viewMode === 'cabinet-id') {
            showLabelName = cfg.showLabelNameCabinet !== undefined ? cfg.showLabelNameCabinet
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'data-flow') {
            showLabelName = cfg.showLabelNameDataFlow !== undefined ? cfg.showLabelNameDataFlow
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'power') {
            showLabelName = cfg.showLabelNamePower !== undefined ? cfg.showLabelNamePower
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else {
            showLabelName = cfg.showLabelName !== undefined ? cfg.showLabelName : true;
        }
        // v0.11.0: the group's name, not the host member's - the wall has one
        // name on site and now one on the drawing.
        // Under the NAMES switch the group label carries its name line only
        // when the group's name is wanted: always in 'group', in 'both' as
        // the wall's headline, never in 'screens' (the members carry their
        // own, in their own passes).
        let screenName = showLabelName
            ? (groupTotals ? (groupTotals.name || cfg.name) : layer.name)
            : null;
        if (groupLabelPass && nameMode === 'screens') screenName = null;
        if (this.hideScreenNames) screenName = null;

        // Other center labels (regular style)
        const centerLines = [];

        // Other labels only in pixel-map mode.
        // A member's own-name pass draws the NAME and nothing else - the
        // sizes, weight, port and circuit figures stay consolidated on the
        // group's single label, exactly where they are in 'group' display.
        if (memberNamePass) {
            // no center lines
        } else if (this.viewMode === 'pixel-map') {
            if (cfg.showLabelSizePx) {
                centerLines.push(`W ${layerWidth} X H ${layerHeight}`);
            }
            if (cfg.showLabelSizeM) {
                centerLines.push(`W ${widthM.toFixed(2)}(m) X H ${heightM.toFixed(2)}(m)`);
            }
            if (cfg.showLabelSizeFt) {
                const useFractional = cfg.useFractionalInches || false;
                
                if (useFractional) {
                    // FRACTIONAL MODE: e.g., 2' 2 7/8"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    const widthInWhole = Math.floor(widthInchesDecimal);
                    const widthInRemainder = widthInchesDecimal - widthInWhole;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    const heightInWhole = Math.floor(heightInchesDecimal);
                    const heightInRemainder = heightInchesDecimal - heightInWhole;
                    
                    // Convert decimal to fraction (1/16ths precision)
                    const toFraction = (decimal) => {
                        if (decimal < 0.03125) return ''; // Less than 1/16
                        const sixteenths = Math.round(decimal * 16);
                        // Simplify common fractions
                        if (sixteenths === 16) return '1'; // Whole inch
                        if (sixteenths === 8) return ' 1/2';
                        if (sixteenths === 4) return ' 1/4';
                        if (sixteenths === 12) return ' 3/4';
                        if (sixteenths === 2) return ' 1/8';
                        if (sixteenths === 6) return ' 3/8';
                        if (sixteenths === 10) return ' 5/8';
                        if (sixteenths === 14) return ' 7/8';
                        return ` ${sixteenths}/16`;
                    };
                    
                    const widthFrac = toFraction(widthInRemainder);
                    const heightFrac = toFraction(heightInRemainder);
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInWhole}${widthFrac}" X H ${heightFtTotal}' ${heightInWhole}${heightFrac}"`);
                } else {
                    // DECIMAL MODE: e.g., 2' 2.5"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInchesDecimal.toFixed(1)}" X H ${heightFtTotal}' ${heightInchesDecimal.toFixed(1)}"`);
                }
            }
            if (cfg.showLabelWeight) {
                centerLines.push(`Weight ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
            }
        } else if (this.viewMode === 'data-flow') {
            if (cfg.showDataFlowPortInfo && groupTotals) {
                // The wall's port line, from the roll-up (_groupCenterInfoLine).
                const line = this._groupCenterInfoLine(gplan, groupTotals);
                if (line) centerLines.push(line);
            } else if (cfg.showDataFlowPortInfo && window.app) {
                // Always recompute from current layer state. Cached `_portsRequired`
                // is only refreshed for the currently-selected layer by
                // `updatePortCapacityDisplay`, so other layers' labels would go
                // stale until clicked. `renderDataFlowArrows` ran just above and
                // populated fresh `_autoPortsRequired` on this layer.
                // Both sides converged on the same lesson: ONE authority for
                // "how many ports does this screen need". Upstream's
                // getLayerPortsRequired is the group-aware one (a member fully
                // served by a peer's crossing path needs zero of its own), so
                // it is the one the canvas asks; the rack-side screenPortCount
                // is being reconciled onto it rather than kept as a rival.
                let portsRequired = typeof window.app.getLayerPortsRequired === 'function'
                    ? (window.app.getLayerPortsRequired(layer) || 0) : 0;
                if (portsRequired > 0) {
                    const mains = portsRequired;
                    const backups = portsRequired;
                    centerLines.push(`${mains} Mains, ${backups} Backups | ${mains + backups} Ports`);
                }
            }
        } else if (this.viewMode === 'power') {
            if (cfg.showPowerCircuitInfo && groupTotals) {
                // The wall's circuit line, from the roll-up (_groupCenterInfoLine).
                const line = this._groupCenterInfoLine(gplan, groupTotals);
                if (line) centerLines.push(line);
            } else if (cfg.showPowerCircuitInfo && window.app) {
                // Ungrouped: recompute from current layer state rather than
                // trusting `_powerCircuitsRequired` (only refreshed for the
                // currently-selected layer). `screenCircuitCount` is the shared
                // authority, so the badge, the Power tab, the soca plan and the
                // report all say the same number on a custom-routed screen.
                let circuits = typeof window.app.screenCircuitCount === 'function'
                    ? window.app.screenCircuitCount(layer)
                    : 0;
                if (circuits <= 0 && Array.isArray(layer._powerCircuits)) {
                    circuits = layer._powerCircuits.filter(c => Array.isArray(c) && c.length > 0).length;
                }
                const voltage = parseFloat(layer.powerVoltage) || 0;
                const panelWatts = parseFloat(layer.panelWatts) || 0;
                const equivalentPanels = Array.isArray(layer.panels)
                    ? layer.panels
                        .filter(p => !p.hidden)
                        .reduce((sum, p) => {
                            if (typeof window.app.getPanelLoadFactor === 'function') {
                                return sum + window.app.getPanelLoadFactor(layer, p);
                            }
                            return sum + 1;
                        }, 0)
                    : 0;
                const totalWatts = panelWatts * equivalentPanels;
                let amps1 = voltage > 0 ? (totalWatts / voltage) : 0;
                let amps3 = voltage > 0 ? (totalWatts / (voltage * 1.73)) : 0;
                // A group member labelling itself (the 'screens' display)
                // reads the same circuit authority the roll-up does, and on a
                // crossing wall that authority hands the wall's ONE combined
                // walk to the first member and zero to every peer. The amps
                // must say the same thing the circuits do: a peer-served
                // member draws no line at all (its cabinets are on the
                // neighbour's circuits, counted there - exactly what the
                // Data label already does for ports), and the member that
                // carries every circuit of the wall carries the wall's load,
                // so its amps come from the roll-up rather than from its own
                // cabinets alone. A member whose circuits are its own keeps
                // its own figure.
                let peerServed = false;
                const screensPlan = (nameMode === 'screens') ? this._groupLabelPlan(layer) : null;
                if (screensPlan && typeof window.app.getGroupTotals === 'function') {
                    if (circuits <= 0) {
                        peerServed = true;
                    } else {
                        const gt = window.app.getGroupTotals(
                            screensPlan.group, this._effectiveLayerCanvasId(layer));
                        if (gt && gt.circuits === circuits && !gt.voltageMismatch) {
                            amps1 = gt.amps1ph || 0;
                            amps3 = gt.amps3ph || 0;
                        }
                    }
                }
                // Split-aware: a multi broken at a chosen boundary is two
                // multis, and this line must agree with the soca panel.
                const multis = circuits > 0
                    ? (typeof window.app.socaCountFor === 'function'
                        ? window.app.socaCountFor(layer, circuits)
                        : Math.ceil(circuits / 6))
                    : 0;
                if (!peerServed) {
                    centerLines.push(`${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`);
                }
            }
        }
        
        // Build Info label clauses (separate bar, at bottom) - only in pixel-map
        // mode. v0.10.7: emit discrete clauses instead of one long string so the
        // draw step can pack them into as many lines as the screen width allows,
        // keeping the whole info bar bound inside the layer instead of spilling
        // past both edges on a narrow screen.
        const infoParts = [];
        if (!memberNamePass && this.viewMode === 'pixel-map' && cfg.showLabelInfo) {
            const aspectRatio = layerWidth / layerHeight;
            const aspectRatioStr = `${aspectRatio.toFixed(2)}`;
            // v0.11.0: a group has no single Columns X Rows - that is the whole
            // reason it is more than one layer - so it reports how many screens
            // it is built from instead of quoting one member's grid.
            if (groupTotals) {
                infoParts.push(`${groupTotals.memberCount} Screens`);
            } else {
                infoParts.push(`${layer.columns} Columns X ${layer.rows} Rows`);
            }
            infoParts.push(`${activePanels} Cabinets Total`);
            infoParts.push(`Resolution: ${layerWidth} X ${layerHeight}`);
            infoParts.push(`Aspect Ratio: ${aspectRatioStr}`);
            infoParts.push(`Weight: ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
        }
        
        // Use absolute pixel sizes - no scaling with zoom
        let fontSize = cfg.labelsFontSize || 30;
        const padding = 6;

        // Info label uses independent slider value
        const infoFontSize = cfg.infoLabelSize || 14;
        const infoLineHeight = infoFontSize + 4;
        
        // Screen name uses tab-specific size and position settings.
        // Where the name's drag offset lives: the cfg layer, except for the
        // group headline in 'both' - there the first member's fields already
        // position the first member's OWN name, and one stored offset cannot
        // place two labels, so the headline's offsets ride the group object
        // under the same field names.
        const nameCfg = (groupLabelPass && nameMode === 'both') ? gplan.group : cfg;
        let screenNameSize = fontSize; // Default for pixel-map
        let screenNameOffsetX = 0;
        let screenNameOffsetY = 0;

        if (this.viewMode === 'pixel-map') {
            // v0.8.7.7: Pixel Map screen-name size stays tied to the
            // legacy labelsFontSize slider (the default for pixel-map),
            // but the X/Y offset is now read from per-view fields so the
            // user can Shift+Alt+drag the name out of the center stack.
            screenNameOffsetX = nameCfg.screenNameOffsetXPixelMap || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYPixelMap || 0;
        } else if (this.viewMode === 'cabinet-id') {
            screenNameSize = cfg.screenNameSizeCabinet || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXCabinet || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYCabinet || 0;
        } else if (this.viewMode === 'data-flow') {
            screenNameSize = cfg.screenNameSizeDataFlow || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXDataFlow || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYDataFlow || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'power') {
            screenNameSize = cfg.screenNameSizePower || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXPower || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYPower || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'show-look') {
            // v0.8.7.7.3: Show Look gets its own grabbable screen-name offset
            // so the label can be repositioned (and edge-clamped) here too.
            screenNameOffsetX = nameCfg.screenNameOffsetXShowLook || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYShowLook || 0;
        }

        const screenNameLineHeight = screenNameSize + 4;
        // The centre lines' lead, from the font they are DRAWN in - on Data
        // and Power that is the screen-name size the branch above just put
        // in fontSize, not the Pixel Map slider. Taken before that branch,
        // a 150 px port line was spaced (and boxed) as 30 px type; one line
        // hid it, the wrapped second line landed on the first.
        const lineHeight = fontSize + 4;

        // 2026-09-23: the room a label line has - the screen's drawn width
        // (the whole wall's, for a group) less a pad each side, in the same
        // world units the text is measured in, so zoom cancels out. Every
        // line wider than this is wrapped (_wrapLabelLine) at its own size:
        // the port/circuit and size/weight lines here at the centre-line
        // font, the name below at its own font. The wrapped lines replace
        // the originals in place, so everything downstream - the block's
        // height, its vertical centring, the plate and the text - counts
        // real lines. A line that fits comes back unchanged.
        const maxLabelWidth = Math.max(layerWidth - padding * 2, 1);

        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        if (centerLines.length > 0) {
            const wrapped = [];
            centerLines.forEach(line => wrapped.push(...this._wrapLabelLine(line, maxLabelWidth)));
            centerLines.splice(0, centerLines.length, ...wrapped);
        }
        let nameLines = [];
        if (screenName) {
            this.ctx.font = `bold ${screenNameSize}px ${projectFontFamily()}`;
            nameLines = this._wrapLabelLine(screenName, maxLabelWidth);
            this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        }

        // Calculate total height of ALL center labels (screen name + other labels)
        let totalCenterHeight = 0;
        let screenNameHeight = 0;

        if (screenName) {
            screenNameHeight = nameLines.length * screenNameLineHeight + padding * 2;
            totalCenterHeight += screenNameHeight;
            if (centerLines.length > 0) {
                totalCenterHeight += 5; // Gap between screen name and other labels
            }
        }
        
        if (centerLines.length > 0 && this.viewMode === 'pixel-map') {
            totalCenterHeight += centerLines.length * lineHeight + padding * 2;
        }
        
        // Start Y position so that ALL labels are centered vertically
        let currentY = centerY - totalCenterHeight / 2;
        

        
        // Render Screen Name with WHITE background and BLACK text
        let infoAnchorY = null;
        // v0.8.7.7.2: the offset actually *applied* to the screen name after
        // the out-of-bounds clamp below. The center/info label group must use
        // this same value (not the raw stored offset) so it never diverges
        // from the name, otherwise a name that snapped back to center leaves
        // the size/info bar flung off-bounds where it gets clipped away.
        let _appliedNameOffsetX = 0;
        let _appliedNameOffsetY = 0;
        if (screenName) {
            // Set the name font up-front so we can measure the label box and
            // clamp it fully inside the layer before drawing.
            this.ctx.font = `bold ${screenNameSize}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';

            // The plate is as wide as the widest of the name's lines and as
            // tall as all of them: one line, and this is the old geometry.
            let nameTextWidth = 0;
            nameLines.forEach(line => {
                nameTextWidth = Math.max(nameTextWidth, this.ctx.measureText(line).width);
            });
            const nameWidth = nameTextWidth + padding * 2;
            const nameHeight = nameLines.length * screenNameLineHeight + padding * 2;

            // Baseline (un-offset) anchor for this view mode. Pixel Map stacks
            // the name above the size/info lines; the other tabs center it.
            const baseX = centerX;
            const baseY = (this.viewMode === 'pixel-map')
                ? (currentY + screenNameHeight / 2)
                : centerY;

            // Desired position = baseline + the user's drag offset. Offsets are
            // stored in *visual* space; on a mirrored (Back-view) canvas the
            // wrapping scale(-1,1) would flip X, so negate offsetX to undo it.
            const _visualOffsetX = this._mirror ? -screenNameOffsetX : screenNameOffsetX;
            let screenNameX = baseX + _visualOffsetX;
            let screenNameY = baseY + screenNameOffsetY;

            // v0.8.7.7.3: clamp the label box to the layer's edges on EVERY tab
            // (Pixel Map, Cabinet ID, Data, Power) instead of snapping back to
            // center when the drag overshoots. Pinning to the edge lets a name
            // sit at the top of a panel (above an overlapping window layer)
            // while keeping the whole label group on-screen. The applied
            // (post-clamp) delta drives the size/info bar so the group never
            // diverges. If the box is larger than the layer, fall back to
            // centering on that axis.
            const _clamp = (v, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.min(Math.max(v, lo), hi));
            screenNameX = _clamp(screenNameX, bounds.x + nameWidth / 2, bounds.x + layerWidth - nameWidth / 2);
            screenNameY = _clamp(screenNameY, bounds.y + nameHeight / 2, bounds.y + layerHeight - nameHeight / 2);

            _appliedNameOffsetX = screenNameX - baseX;
            _appliedNameOffsetY = screenNameY - baseY;

            // The 'both' display keeps the group's headline AND the member
            // names on the wall at once, and they must never sit on top of
            // each other - the wall's main section centres exactly where the
            // headline does. Resolved the way the label stack already
            // resolves its own collisions: the headline keeps its place and
            // the member name steps BELOW it, with the stack's own 5px gap.
            // Applied after the offset bookkeeping above so the step is a
            // draw-time dodge, never healed into the stored offsets; skipped
            // while this very name is being dragged so it tracks the cursor
            // out from under the headline.
            if (memberNamePass && nameMode === 'both'
                    && !(this.isDraggingScreenName && window.app && window.app.currentLayer
                        && window.app.currentLayer.id === layer.id)) {
                const gBox = this._bothModeGroupNameBox(plan, layer);
                if (gBox
                        && screenNameX + nameWidth / 2 > gBox.x1
                        && screenNameX - nameWidth / 2 < gBox.x2
                        && screenNameY + nameHeight / 2 > gBox.y1
                        && screenNameY - nameHeight / 2 < gBox.y2) {
                    screenNameY = _clamp(gBox.y2 + 5 + nameHeight / 2,
                        bounds.y + nameHeight / 2,
                        bounds.y + layerHeight - nameHeight / 2);
                }
            }

            const nameX = screenNameX - nameWidth / 2;
            const nameY = screenNameY - nameHeight / 2;

            // v0.8.7.7: cache the label rect in workspace (un-mirrored)
            // coords so a plain mousedown can hit-test it and start a
            // screen-name drag without needing a Shift modifier. Includes
            // the layer's canvas workspace offset and the per-layer Show
            // Look translate (this._renderDx / this._renderDy) so the
            // rect lines up with where the label is actually drawn on
            // screen across multi-canvas / Show Look views.
            if (!this.exportMode) {
                const _wsOff = (typeof this._layerCanvasOffset === 'function')
                    ? this._layerCanvasOffset(layer) : { wx: 0, wy: 0 };
                const _ldx = (typeof this._renderDx === 'number') ? this._renderDx : 0;
                const _ldy = (typeof this._renderDy === 'number') ? this._renderDy : 0;
                // v0.11.0: cached on `cfg`, so a group's single label has a
                // single owner for the plain-click drag hit-test. The 'both'
                // headline gets its own key on the same owner: the ordinary
                // key belongs to that member's own name in that display.
                const _nameRect = {
                    x1: _wsOff.wx + _ldx + nameX,
                    y1: _wsOff.wy + _ldy + nameY,
                    x2: _wsOff.wx + _ldx + nameX + nameWidth,
                    y2: _wsOff.wy + _ldy + nameY + nameHeight,
                    viewMode: this.viewMode,
                };
                if (groupLabelPass) cfg._groupNameHitRect = _nameRect;
                else cfg._screenNameHitRect = _nameRect;
            }

            // Clip to layer bounds so labels don't overflow the screen edge
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw WHITE background
            this.ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
            const snappedNameRect = this.snapRect(nameX, nameY, nameWidth, nameHeight);
            this.ctx.fillRect(snappedNameRect.x, snappedNameRect.y, snappedNameRect.width, snappedNameRect.height);

            // Draw BLACK text - each of the name's lines centred on the
            // plate; a single line sits at the plate's centre exactly as
            // before the wrap existed.
            this.ctx.fillStyle = '#000000';
            let nameLineY = screenNameY - nameHeight / 2 + padding + screenNameLineHeight / 2;
            nameLines.forEach(line => {
                this._fillText(line, this.snap(screenNameX), this.snap(nameLineY));
                nameLineY += screenNameLineHeight;
            });

            this.ctx.restore();
            
            // Reset font for other labels
            this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
            if (this.viewMode === 'pixel-map') {
                currentY += screenNameHeight;
                if (centerLines.length > 0) {
                    currentY += 5; // Gap before other labels
                }
            } else {
                infoAnchorY = nameY + nameHeight + 5;
            }
        }

        // v0.8.7.7: when the user has dragged the screen-name label off
        // its default center position, the other identification labels
        // (port/circuit stats above, "Columns × Rows • Cabinets..." info
        // bar at the bottom) shift by the same offset so the whole label
        // group moves as one unit. Falls back to 0/0 when the layer has
        // no offset for the current view OR no screen name is shown.
        // v0.8.7.7.3: the size/info labels follow the name's *applied*
        // (post-clamp) offset on every tab, so the whole label group always
        // moves as a single unit and can never be clipped off-bounds on its
        // own. _appliedNameOffset is already in visual space (it accounts for
        // Back-view mirroring), so no extra mirror compensation is needed.
        let _labelGroupOffsetX = 0;
        let _labelGroupOffsetY = 0;
        if (screenName) {
            _labelGroupOffsetX = _appliedNameOffsetX;
            _labelGroupOffsetY = _appliedNameOffsetY;

            // v0.8.7.7.3: HEAL a runaway stored offset back to the clamped
            // value. The older snap-to-center clamp let the *stored* offset
            // balloon far past the layer (e.g. a name dragged behind a
            // now-hidden window could reach -1200 on an 840px screen) while
            // the label visually stayed put. That corrupt value persisted in
            // saved files and made the label feel unmovable on the next drag.
            // Writing the post-clamp value back here self-corrects those
            // offsets on the very next render, including right after a file
            // load, so re-dragging always starts from where the label
            // actually sits. Skipped while THIS layer's name is being dragged
            // (so we don't fight the live gesture) and in export.
            const _isDraggingThisName = groupLabelPass
                ? this.isDraggingGroupName
                : (this.isDraggingScreenName
                    && window.app && window.app.currentLayer
                    && window.app.currentLayer.id === cfg.id);
            if (!this.exportMode && !_isDraggingThisName) {
                // Stored offsets are in logical space; _appliedNameOffsetX is
                // in visual space (mirror already applied), so convert X back.
                // Healed onto whichever object the offsets were read from -
                // the layer, or the group for the 'both' headline.
                const _healX = this._mirror ? -_appliedNameOffsetX : _appliedNameOffsetX;
                const _healY = _appliedNameOffsetY;
                const _heal = (fx, fy) => {
                    if (Math.abs((nameCfg[fx] || 0) - _healX) > 0.5) nameCfg[fx] = _healX;
                    if (Math.abs((nameCfg[fy] || 0) - _healY) > 0.5) nameCfg[fy] = _healY;
                };
                if (this.viewMode === 'pixel-map') _heal('screenNameOffsetXPixelMap', 'screenNameOffsetYPixelMap');
                else if (this.viewMode === 'cabinet-id') _heal('screenNameOffsetXCabinet', 'screenNameOffsetYCabinet');
                else if (this.viewMode === 'data-flow') _heal('screenNameOffsetXDataFlow', 'screenNameOffsetYDataFlow');
                else if (this.viewMode === 'power') _heal('screenNameOffsetXPower', 'screenNameOffsetYPower');
                else if (this.viewMode === 'show-look') _heal('screenNameOffsetXShowLook', 'screenNameOffsetYShowLook');
            }
        }
        
        // Render other center labels with dark background (regular style)
        if (centerLines.length > 0) {
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            
            // Measure text for background
            let maxWidth = 0;
            centerLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });
            
            const bgWidth = maxWidth + padding * 2;
            const bgHeight = centerLines.length * lineHeight + padding * 2;
            // v0.8.7.7: shift the center-info group horizontally by the
            // same offset the screen-name moved (Y is already tracked
            // via infoAnchorY for non-pixel-map, and via _labelGroupOffsetY
            // applied below for pixel-map).
            const bgX = (centerX + _labelGroupOffsetX) - bgWidth / 2;
            // Data / Power: the lines hang under the name plate; with no
            // name drawn (2026-09-23) the block is centred on the wall on
            // its own instead of hanging its top edge from the centre.
            const bgY = (this.viewMode === 'pixel-map'
                ? currentY + _labelGroupOffsetY
                : (infoAnchorY ?? (centerY - bgHeight / 2)));

            // Clip to layer bounds so labels don't bleed through higher layers
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw dark background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedBgRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedBgRect.x, snappedBgRect.y, snappedBgRect.width, snappedBgRect.height);

            // Draw white text
            this.ctx.fillStyle = cfg.labelsColor || '#ffffff';
            let yPos = bgY + padding + lineHeight / 2;
            centerLines.forEach(line => {
                this._fillText(line, this.snap(centerX + _labelGroupOffsetX), this.snap(yPos));
                yPos += lineHeight;
            });

            this.ctx.restore();
        }
        
        // Render Info label at bottom with background.
        if (infoParts.length > 0) {
            // Use world coordinates directly (transform is already applied)
            this.ctx.font = `${infoFontSize}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';

            // v0.10.7: greedily pack the clauses into lines that stay within the
            // layer's inner width, joined by " • ", so the info bar wraps and
            // stacks upward from the bottom edge instead of overflowing the
            // sides of a narrow screen. Wide screens still collapse to one line.
            const sep = ' • ';
            const maxLineWidth = Math.max(layerWidth - padding * 2, infoFontSize * 4);
            const infoLines = [];
            let currentLine = '';
            infoParts.forEach(part => {
                const candidate = currentLine ? currentLine + sep + part : part;
                if (currentLine && this.ctx.measureText(candidate).width > maxLineWidth) {
                    infoLines.push(currentLine);
                    currentLine = part;
                } else {
                    currentLine = candidate;
                }
            });
            if (currentLine) infoLines.push(currentLine);

            // Measure text for background
            let maxWidth = 0;
            infoLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });

            const bgWidth = maxWidth + padding * 2;
            const bgHeight = infoLines.length * infoLineHeight + padding * 2;
            // v0.8.7.7: bottom-anchored info bar follows the screen-name
            // offset so the whole label group moves together when the
            // user drags.
            const bgX = (centerX + _labelGroupOffsetX) - bgWidth / 2;
            const bgY = (bottomY + _labelGroupOffsetY) - bgHeight - padding;

            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedInfoRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedInfoRect.x, snappedInfoRect.y, snappedInfoRect.width, snappedInfoRect.height);

            // Draw text
            this.ctx.fillStyle = cfg.labelsColor || '#ffffff';
            let yPos = bgY + padding + infoLineHeight;
            infoLines.forEach(line => {
                this._fillText(line, this.snap(centerX + _labelGroupOffsetX), this.snap(yPos));
                yPos += infoLineHeight;
            });
        }
        
        // Restore context (remove clipping)
        this.ctx.restore();
    },
    
    renderLayerOffsets(layer) {
        // Only render offsets in pixel-map mode
        if (this.viewMode !== 'pixel-map') {
            return;
        }
        
        if (!layer.showOffsetTL && !layer.showOffsetTR && !layer.showOffsetBL && !layer.showOffsetBR) {
            return;
        }
        
        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        // v0.9.3: use the rotated footprint so the corner X,Y readouts sit at the
        // rotated screen's corners and report that orientation's coordinates.
        const bounds = this.getLayerFootprintBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;

        // Calculate actual corner positions
        // Since pixels are zero-indexed:
        // - Top-left starts at offset_x, offset_y (e.g., 0, 0)
        // - Top-right is at offset_x + width - 1 (e.g., 0 + 1024 - 1 = 1023)
        // - Bottom-left is at offset_y + height - 1 (e.g., 0 + 640 - 1 = 639)
        // - Bottom-right is at both -1 (e.g., 1023, 639)
        const tlX = bounds.x;
        const tlY = bounds.y;
        const trX = bounds.x + layerWidth - 1;  // Account for zero-indexing
        const trY = bounds.y;
        const blX = bounds.x;
        const blY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        const brX = bounds.x + layerWidth - 1;   // Account for zero-indexing
        const brY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        
        const corners = [
            { x: tlX, y: tlY, text: `X ${tlX}, Y ${tlY}`, show: layer.showOffsetTL, align: 'left', baseline: 'top', offsetX: 5, offsetY: 5 },
            { x: trX, y: trY, text: `X ${trX}, Y ${trY}`, show: layer.showOffsetTR, align: 'right', baseline: 'top', offsetX: -5, offsetY: 5 },
            { x: blX, y: blY, text: `X ${blX}, Y ${blY}`, show: layer.showOffsetBL, align: 'left', baseline: 'bottom', offsetX: 5, offsetY: -5 },
            { x: brX, y: brY, text: `X ${brX}, Y ${brY}`, show: layer.showOffsetBR, align: 'right', baseline: 'bottom', offsetX: -5, offsetY: -5 }
        ];
        
        // Use absolute pixel sizes - no scaling with zoom
        const fontSize = layer.labelsFontSize || 30;
        const padding = 4;
        
        this.ctx.font = `${fontSize}px ${projectFontFamily()}`;
        
        corners.forEach(corner => {
            if (!corner.show) return;
            
            // Skip if corner is outside raster bounds
            if (corner.x < 0 || corner.x >= this.rasterWidth || corner.y < 0 || corner.y >= this.rasterHeight) {
                return;
            }
            
            // Use world coordinates directly (transform is already applied)
            const worldX = corner.x + corner.offsetX;
            const worldY = corner.y + corner.offsetY;
            
            // Measure text for background
            const metrics = this.ctx.measureText(corner.text);
            const textWidth = metrics.width;
            const textHeight = fontSize;
            
            let bgX, bgY;
            if (corner.align === 'left') {
                bgX = worldX;
            } else {
                bgX = worldX - textWidth - padding * 2;
            }
            
            if (corner.baseline === 'top') {
                bgY = worldY;
            } else {
                bgY = worldY - textHeight - padding * 2;
            }
            
            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedCornerRect = this.snapRect(bgX, bgY, textWidth + padding * 2, textHeight + padding * 2);
            this.ctx.fillRect(snappedCornerRect.x, snappedCornerRect.y, snappedCornerRect.width, snappedCornerRect.height);
            
            // Draw text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            this.ctx.textAlign = corner.align;
            this.ctx.textBaseline = corner.baseline;
            
            const textX = corner.align === 'left' ? worldX + padding : worldX - padding;
            const textY = corner.baseline === 'top' ? worldY + padding : worldY - padding;

            this._fillText(corner.text, this.snap(textX), this.snap(textY));
        });
        
        this.ctx.restore();
    },
});
