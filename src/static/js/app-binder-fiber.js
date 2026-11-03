// app-binder-fiber: the binder's FIBER page - every fiber link of the show
// on one sheet, processor to breakout box (owner, 2026-11-03: "on the
// binder i like the idea of just a fiber page if fiber is used. So it can
// all be shown together processor to breakout").
//
// ONE PAGE PER SHOW, IN ADDITION. It prints only where a link of the show
// is on a fiber cable, after the hardware sheets (series 4), and runs onto
// a second sheet only when it must. The processor pages keep their Fiber
// connections tables and strand maps and the box sheets their fiber rows:
// this page gathers them, it replaces none of them.
//
// THE PAGE IS MOCKUP #5 (picked 2026-11-03, "i like the compactness of
// 5"), all of it on one sheet:
//   the DRAWING  - processors on the left, breakout boxes on the right, one
//                  row per link, the columns exactly as picked: PROCESSOR |
//                  OUTPUT | AT THE PROCESSOR | CABLE | EXTENSION | AT THE
//                  BREAKOUT | BREAKOUT BOX ("keep it as it is actually").
//                  The cable's line carries a pill with its name, kind and
//                  length; an extension at the box end is the dashed line
//                  after the dot, its kind and length over it; the strands
//                  stand in a plug at each end, swatched, in the order they
//                  plug in there (a TAC pair flipped, an MTP or an
//                  opticalCON the same order, crossing inside). A loop's
//                  two boxes are outlined together. Where the processors do
//                  not fit one column the drawing splits into TWO columns
//                  side by side ("two drawings of columns if have that much
//                  fiber").
//   the STRAND MAPS - one per cable, a link to a row: the strands at the
//                  processor, the output, the breakout and the strands at
//                  the breakout, under a band per processor; the spares on
//                  a line of their own.
//   the PULL LIST - the fiber cables and extensions to pull, the show pull
//                  list's own rows.
//
// NOTHING IS READ TWICE. Every link, strand and name comes from the rows
// the processor pages print (_bFiberConnectionRows: its cells, and the
// `link` / `fiber` it carries for this page), the strand map title and the
// strand names from the same helpers, and the pull rows are the show pull
// list's (book.list.totals, the user's pull-sheet edits included). The
// page can never disagree with the processor pages or the pull sheet.
//
// The layout is the binder's own fill (_bFillScale): the drawing and the
// tables laid out at their base sizes, then the whole drawing area scaled
// up as far as it holds them, so a small show draws big ("always prefer a
// bigger drawing"). Every combination of one or two drawing columns and
// one to three table columns is tried, and the largest drawing wins. What
// does not fit at 1 continues on a "(cont.)" sheet, the drawing first.
import { LEDRasterApp } from './app-core.js';
import { BINDER_STYLE } from './app-binder.js';

const { INK, RULE, FAINT, MUTED, SZ, FILL_CAP, BUBBLE_H, BAND_BG,
        COL_W, COL_GAP, DATA_COL_W, GROUP_H, TH_H, ROW_H, SWATCH_W } = BINDER_STYLE;

// The drawing's type, in page px at 200 px/in (inches, as the binder's SZ):
// a little under the tables' cell, as the mockup drew it.
const DZ = { name: 26, model: 22, small: 19, tab: 21, strand: 21, pill: 20, ext: 20, box: 24, note: 19 };
// A strand's line in a plug; a row is its plug's lines and ROW_PAD, never
// under two lines (a duplex pair).
const LH = 28;
const ROW_PAD = 16;
const MIN_LINES = 2;
// The gap between one processor and the next, and between the two
// drawing columns.
const PROC_GAP = 24;
const DRAW_GAP = 70;
// The tab an output or an input stands in, a plug's inner pad, the swatch,
// the short lead from a tab to its plug.
const TAB_H = 36;
const PAD = 12;
const SW = 20;
const LEAD = 14;
// The cable's pill: its height, its pad, and the run of line it keeps
// clear on either side.
const PILL_H = 36;
const PILL_PAD = 16;
const RUN = 22;
// The extension's dot, its dash.
const DOT = 7;
const DASH = [10, 6];
// The drawing's head (the column headings), and the gap over the bubble.
const HEAD_H = TH_H;
const HEAD_GAP = 10;
const BUBBLE_GAP = 16;
// The blocks' widths, held between these.
const PROC_W = [200, 440];
const BOX_W = [180, 420];
// The least two drawing columns may be scaled to, to stay on one sheet.
const TWO_MIN = 0.8;
// Warnings ("no length") in the colour palette; ink on the press.
const WARN = '#b00000';

class _BinderFiber {

    // Whether the show uses fiber: a link of any box (or a QD-S's own) on
    // a fiber cable. The page prints for nothing else, and the export
    // dialog offers its tick only then.
    binderUsesFiber() {
        if (typeof this._fiberAllBoxes !== 'function' || typeof this.fiberBoxLinks !== 'function') return false;
        return this._fiberAllBoxes().some(({ box }) => this.fiberBoxLinks(box).some(l => l.cable));
    }

    // ---- the facts ----------------------------------------------------------

    // Every processor that feeds a breakout box, in tray order, with its
    // linked rows from the processor page's own table:
    //   [{ proc, title, model, backup, redundancy, rows: [row] }]
    // a row being _bFiberConnectionRows' - cells, parts, `link`, `fiber` -
    // with the box it lands on. An output nothing is plugged into is not a
    // link and is not drawn ("not used" stays the processor page's).
    _bfProcessors() {
        const out = [];
        for (const proc of this._processorsResolved || []) {
            const title = this._bProcessorTitle(proc);
            // (an input with nothing picked is the processor page's "no
            // fiber picked"; it is no link to draw)
            const rows = this._bFiberConnectionRows(proc, title).filter(r => r.link && (r.link.cable || r.link.copper));
            if (!rows.length) continue;
            const backup = (proc.backupUnit && proc.backupUnit.name) || '';
            out.push({ proc, title, backup, rows,
                       model: proc.deviceName && proc.deviceName !== title ? proc.deviceName : '',
                       redundancy: this._bfRedundancy(proc, backup) });
        }
        return out;
    }

    // The processor's redundancy in the tray's words: a fixed pairing as
    // its row reads it ("Loops A to B, C to D"), else the processor page's
    // line, without the backup unit it already names; nothing when off.
    _bfRedundancy(proc, backup) {
        const level = typeof this._procRedundancyLevel === 'function' ? this._procRedundancyLevel(proc) : 'off';
        if (level === 'off' && !backup) return '';
        if (level === 'fixed' && typeof this._dockLoopText === 'function') return this._dockLoopText(proc);
        const text = this._bRedundancyText(proc);
        return backup ? text.replace(/ · backed up by .*$/, '') : text;
    }

    // The breakout box's second line: the box a loop's far box loops from
    // ("loop of XD A"), a port-by-port backup's mains, else the screens its
    // ports feed. '' for a card cabled on links of its own (a QD-S).
    _bfBoxNote(box) {
        if (!box || box.linkHost) return '';
        const pair = typeof this.fiberLoopPair === 'function' ? this.fiberLoopPair(box) : null;
        if (pair && pair.far === box) return `loop of ${this._bBoxTitle(pair.near)}`;
        const hit = this._fiberAllBoxes().find(b => b.box.id === box.id);
        const card = hit && hit.card;
        if (card && this.boxLoopMixed(box)) return this.boxLoopText(box, card.cvts || [], b => this._bBoxTitle(b));
        if (!card || typeof this._portOccupants !== 'function') return '';
        const names = [];
        for (const port of box.ports || []) {
            for (const o of this._portOccupants(card.id, port.number)) {
                const name = String((o && o.name) || '').trim();
                if (name && !names.includes(name)) names.push(name);
            }
        }
        return names.join(', ');
    }

    // The cable's pill: "TAC A · TAC 24 · 500'" - its name, its kind (and
    // strand count), its length or "no length"; copper its kind and
    // length, "Cat6A · 150'"; a link with nothing picked says so.
    _bfPill(row) {
        const l = row.link;
        if (l.copper) {
            const ft = this.parseCableLength(l.copper.ft);
            const has = Number.isFinite(ft) && ft > 0;
            return { text: [l.copper.copper, has ? this.pullLengthText(ft) : 'no length'].join(' · '),
                     warn: !has || !!this.copperOverText(l.copper) };
        }
        const cable = l.cable;
        if (!cable) return { text: 'no fiber picked', warn: false, none: true };
        const kind = this.fiberCableIsStranded(cable) ? `${this.fiberKindWord(cable.kind)} ${cable.strands}`
            : this.fiberKindWord(cable.kind);
        const ft = this.parseCableLength(cable.ft);
        const has = Number.isFinite(ft) && ft > 0;
        const parts = [cable.name || '', kind, has ? this.pullLengthText(ft) : 'no length']
            .filter((t, i, a) => t && a.indexOf(t) === i);
        return { text: parts.join(' · '), warn: !has };
    }

    // The extension's label over its dashed line, "Fan-out 30'", "Fan-out
    // · no length" - the processor page's words without their "ext".
    _bfExtLabel(row) {
        const ext = row.fiber && row.fiber.ext;
        if (!ext || !ext.length) return null;
        const text = String(ext[0].text).replace(/^ext /, '');
        return { text, warn: /no length$/.test(text) };
    }

    // A plug's lines: the strands as they plug in there, swatched; MTP and
    // opticalCON add "crosses inside" at the breakout; copper reads
    // "copper"; a link with nothing picked has no plug.
    _bfPlug(row, end) {
        const f = row.fiber;
        if (!f) return row.link.copper ? [{ text: 'copper', swatch: null, muted: true }] : [];
        const list = (end === 'p' ? f.atProcessor : f.atBreakout).map(p => ({ text: p.text, swatch: p.swatch || null }));
        if (end === 'b' && f.crosses) list.push({ text: 'crosses inside', swatch: null, muted: true });
        return list;
    }

    // The page's facts, as the tests and the sheet read them:
    //   { procs: [{ title, model, backup, redundancy,
    //               links: [{ output, cable, atProcessor, breakout,
    //                         atBreakout, extension, box, input }] }],
    //     cables: [{ id, title, rows: [...], spare }], pull: [row] }
    binderFiberPage(book) {
        const procs = this._bfProcessors();
        const list = book && book.list ? book.list : this.buildPullSheet();
        return {
            procs: procs.map(p => ({
                title: p.title, model: p.model, backup: p.backup, redundancy: p.redundancy,
                links: p.rows.map(r => ({
                    output: r.cells[0], cable: this._bfPill(r).text,
                    atProcessor: this._bfPlug(r, 'p').map(x => x.text),
                    breakout: r.cells[3],
                    atBreakout: this._bfPlug(r, 'b').map(x => x.text),
                    extension: (this._bfExtLabel(r) || {}).text || '',
                    box: this._bBoxTitle(r.link.box), input: r.link.title,
                    cableId: r.link.cable ? r.link.cable.id : null,
                    strands: ((r.link.link && r.link.link.strands) || []).map(Number),
                })),
            })),
            cables: this._bfStrandMapSpecs(procs).map(s => ({
                id: s.cable.id, title: s.title, spare: s.spare,
                rows: s.rows.map(r => (r.band !== undefined ? { band: r.band } : { cells: r.cells })),
            })),
            pull: this._bfPullRows(list).map(r => ({ type: r.type, length: r.length, qty: r.qty, label: r.label || '' })),
        };
    }

    // ---- the tables ---------------------------------------------------------

    // A strand map per cable some link takes, in the order the drawing
    // first reaches each (tray order, as the processor pages carry them;
    // the show's own order between cables first reached on one link): a
    // band per processor ("S1 · SX40"), then each of its links on the
    // cable - the strands at the processor, the output, the breakout, the
    // strands at the breakout - as the Fiber connections rows read them;
    // the strands no link takes as one line, "13 Blue/Black to 24
    // Aqua/Black · spare (12)".
    _bfStrandMapSpecs(procs) {
        const out = [];
        // a pair on one line, as the compact page was picked ("i like the
        // compactness of 5"); "crosses inside" under it
        const pair = (list) => list.map(x => ({ text: x.text, swatch: x.swatch || null }));
        for (const cable of this.getFiberCables()) {
            const rows = [];
            for (const p of procs) {
                const mine = p.rows.filter(r => r.fiber && r.link.cable && r.link.cable.id === cable.id);
                if (!mine.length) continue;
                rows.push({ band: [p.title, p.model].filter(Boolean).join(' · ') });
                for (const r of mine) {
                    const at = pair(r.fiber.atBreakout)
                        .concat(r.fiber.crosses ? [{ text: 'crosses inside', brk: true }] : []);
                    rows.push({ cells: [r.cells[2], r.cells[0], r.cells[3], at.map(x => x.text).join(' · ')],
                                parts: { 0: pair(r.fiber.atProcessor), 3: at } });
                }
            }
            if (!rows.length) continue;
            const used = this.fiberStrandUsers(cable.id);
            const spare = [];
            for (let n = 1; n <= (cable.strands || 0); n++) if (!used.has(n)) spare.push(n);
            out.push({ cable, title: this._bStrandMapTitle(cable), rows, spare: this._bfSpareText(spare, cable) });
        }
        const order = procs.flatMap(p => p.rows).map(r => r.link.cable && r.link.cable.id);
        const at = (spec) => order.indexOf(spec.cable.id);
        return out.map((spec, i) => ({ spec, i })).sort((a, b) => (at(a.spec) - at(b.spec)) || (a.i - b.i))
            .map(x => x.spec);
    }

    // The spare strands as runs by name: "13 Blue/Black to 24 Aqua/Black ·
    // spare (12)", "3 Green, 7 Red to 8 Black · spare (3)"; '' where none.
    _bfSpareText(spare, cable) {
        if (!spare.length) return '';
        const runs = [];
        for (const n of spare) {
            const last = runs[runs.length - 1];
            if (last && last[1] === n - 1) last[1] = n;
            else runs.push([n, n]);
        }
        const name = (n) => this.fiberStrandName(n, cable);
        return runs.map(([a, b]) => (a === b ? name(a) : `${name(a)} to ${name(b)}`)).join(', ')
            + ` · spare (${spare.length})`;
    }

    // The show pull list's fiber rows: each fiber cable a link takes and
    // each extension, by the type the pull list gives them - its rows as
    // they stand, merged, counted and edited as the pull sheet has them.
    _bfPullRows(list) {
        const types = new Set();
        for (const { box } of this._fiberAllBoxes()) {
            for (const l of this.fiberBoxLinks(box)) {
                if (!l.cable) continue;
                types.add(this.fiberCableTypeText(l.cable));
                const ext = this.fiberLinkExtension(l);
                if (ext) types.add(this.fiberExtensionType(ext, l.cable));
            }
        }
        return ((list && list.totals) || []).filter(r => r && types.has(r.type));
    }

    // The tables as blocks, measured at `width`: the strand maps, then the
    // pull list.
    _bfTableBlocks(book, specs, pull, width) {
        // each column's share: its whole content's width; in a table
        // narrower than that, the strand columns give up the room first
        // (a pair goes onto two lines) and the output and the breakout
        // keep theirs on one line where they can
        const shares = (s) => {
            if (!s.need) return null;
            const w = s.need.slice();
            let over = w.reduce((a, b) => a + b, 0) - width;
            for (const i of [0, 3]) {
                if (over <= 0) break;
                const give = Math.min(over, Math.max(0, w[i] - s.least[i]));
                w[i] -= give;
                over -= give;
            }
            return w;
        };
        const need = (s, i, dflt) => { const w = shares(s); return w && w[i] > 0 ? w[i] : dflt; };
        const blocks = specs.map(s => {
            const lines = this._bTableLines(book, {
                title: s.title, width, shrink: true, rows: s.rows,
                // each column's share its content's whole width
                // (_bfTableNatural), so a pair and a breakout stay on one
                // line wherever the table is that wide
                cols: [{ title: 'at the processor', w: need(s, 0, 1.2), list: 3, parts: true, headShrink: true },
                       { title: 'output', w: need(s, 1, 0.7), list: 2, headShrink: true },
                       { title: 'breakout', w: need(s, 2, 1), list: 2, words: 'on', headShrink: true },
                       { title: 'at the breakout', w: need(s, 3, 1.2), list: 3, parts: true, headShrink: true }],
            });
            if (s.spare) lines.push(...this._bfNoteLines(book, s.spare, width));
            return { lines };
        });
        const cols = this._bPullCableCols('gear').slice(1);
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Fiber cables · pull list', width, cols, whole: true,
            rows: pull.length ? pull.map(r => ({ cells: [...this._bPullCableCells(r), this._bQty(r.qty), r.label || ''] }))
                : [{ cells: ['none', '', '', ''] }],
        }) });
        return blocks;
    }

    // A muted line under a table (its spares), wrapped at its words.
    _bfNoteLines(book, text, width) {
        const lines = this._bWrap(book, text, SZ.cell, 400, width - 24, 4);
        return lines.map((t, i) => ({ h: i ? ROW_H - 8 : ROW_H, draw: (ctx, x, y) => {
            this._bText(book, t, x + 12, y + (i ? 19 : 27), { size: SZ.cell, color: MUTED });
            if (i === lines.length - 1) { ctx.fillStyle = FAINT; ctx.fillRect(x, y + (i ? ROW_H - 8 : ROW_H) - 2, width, 2); }
        } }));
    }

    // The tables' natural width: every row on one line - a strand pair
    // side by side, the breakout whole - and the pull list's rows whole.
    // The sheet gives them that where it has the room, else what it has
    // (they wrap), never under COL_W.
    _bfTableNatural(book, specs, pull) {
        const ctx = book.measureCtx;
        const padX = 12;
        const head = (t) => { ctx.font = this._bFont(SZ.th, 700); return ctx.measureText(this._bCaps(t)).width + padX * 2; };
        // a strand list on its lines, or (`one`) its widest strand alone
        const partsW = (parts, one = false) => {
            ctx.font = this._bFont(SZ.cell, 400);
            const gap = ctx.measureText(' ').width;
            let w = 0, line = 0;
            for (const p of this._bPartPieces(parts || [])) {
                const pw = (p.swatch ? SWATCH_W : 0) + ctx.measureText(p.text).width;
                line = p.brk || !line || one ? pw : line + gap + pw;
                w = Math.max(w, line);
            }
            return w + padX * 2;
        };
        const textW = (t) => { ctx.font = this._bFont(SZ.cell, 400); return ctx.measureText(String(t || '')).width + padX * 2; };
        let need = 0;
        for (const s of specs) {
            const cell = [head('at the processor'), head('output'), head('breakout'), head('at the breakout')];
            const least = cell.slice();
            for (const r of s.rows) {
                if (r.band !== undefined) continue;
                least[0] = Math.max(least[0], partsW(r.parts[0], true));
                least[3] = Math.max(least[3], partsW(r.parts[3], true));
                cell[0] = Math.max(cell[0], partsW(r.parts[0]));
                cell[1] = Math.max(cell[1], textW(r.cells[1]));
                cell[2] = Math.max(cell[2], textW(r.cells[2]));
                cell[3] = Math.max(cell[3], partsW(r.parts[3]));
            }
            s.need = cell;
            s.least = [least[0], cell[1], cell[2], least[3]];
            need = Math.max(need, cell.reduce((a, b) => a + b, 0));
        }
        const pullCols = this._bPullCableCols('gear').slice(1);
        const rows = pull.map(r => ({ cells: [...this._bPullCableCells(r), this._bQty(r.qty), r.label || ''] }));
        need = Math.max(need, this._bColNeeds(book, pullCols, rows, padX, true).reduce((a, b) => a + b, 0));
        return Math.max(COL_W, Math.ceil(need) + 2);
    }

    // ---- the drawing's geometry ---------------------------------------------

    _bfW(book, text, size, weight = 400) {
        const ctx = book.measureCtx;
        ctx.font = this._bFont(size, weight);
        return ctx.measureText(String(text == null ? '' : text)).width;
    }

    // The drawing's columns, measured from everything they must hold - each
    // at least as wide as its heading - and every processor as a GROUP of
    // rows: { cols: { x: {...}, w }, groups: [{ p, rows, h, lines }] }.
    _bfGeometry(book, procs) {
        const head = (t) => this._bfW(book, this._bCaps(t), SZ.th, 700) + 16;
        const max = (list, f) => list.reduce((m, x) => Math.max(m, f(x)), 0);
        const rows = procs.flatMap(p => p.rows);
        // the processor block: its name (with its backup), model, redundancy
        const procNat = max(procs, p => Math.max(this._bfW(book, p.title, DZ.name, 700),
                                                 p.backup ? this._bfW(book, `and ${p.backup}`, DZ.name, 700) : 0,
                                                 this._bfW(book, p.model, DZ.model),
                                                 this._bfW(book, p.redundancy, DZ.small)));
        const PW = Math.max(head('processor'), Math.min(PROC_W[1], Math.max(PROC_W[0], procNat + PAD * 2)));
        const TW = Math.max(head('output'), max(rows, r => this._bfW(book, r.cells[0], DZ.tab)) + PAD * 2, 80);
        const plugW = (r, end) => {
            const ps = this._bfPlug(r, end);
            const sw = ps.some(x => x.swatch) ? SW + 8 : 0;
            return ps.length ? max(ps, x => (x.swatch || !x.muted ? sw : 0)
                + this._bfW(book, x.text, x.muted ? DZ.small : DZ.strand)) + PAD * 2 : 0;
        };
        const GW = Math.max(head('at the processor'), head('at the breakout'),
                            max(rows, r => Math.max(plugW(r, 'p'), plugW(r, 'b'))));
        const pillW = max(rows, r => this._bfW(book, this._bfPill(r).text, DZ.pill, 700)) + PILL_PAD * 2;
        const CW = Math.max(head('cable'), pillW + RUN * 2);
        const EW = Math.max(head('extension'), 130,
                            max(rows, r => { const e = this._bfExtLabel(r); return e ? this._bfW(book, e.text, DZ.ext, e.warn ? 700 : 400) + 24 : 0; }));
        const XW = Math.max(60, max(rows, r => this._bfW(book, r.link.title, DZ.tab)) + PAD * 2);
        // (a box is as wide as its name, its note a little past it at
        // most - a long list of screens wraps or is cut, never widens the
        // drawing)
        const boxNat = max(rows, r => {
            const t = this._bfW(book, this._bBoxTitle(r.link.box), DZ.box, 700);
            return Math.max(t, Math.min(this._bfW(book, this._bfBoxNote(r.link.box), DZ.note), Math.max(t, 140) * 1.3));
        });
        const BW = Math.max(head('breakout box') - XW, Math.min(BOX_W[1], Math.max(BOX_W[0], boxNat + PAD * 2)));
        const x = {};
        x.P0 = 0; x.P1 = PW;
        x.T0 = x.P1; x.T1 = x.T0 + TW;
        x.G0 = x.T1 + LEAD; x.G1 = x.G0 + GW;
        x.C0 = x.G1; x.C1 = x.C0 + CW;
        x.J = x.C1; x.E1 = x.J + EW;
        x.Q0 = x.E1; x.Q1 = x.Q0 + GW;
        x.X0 = x.Q1 + LEAD; x.X1 = x.X0 + XW;
        x.B0 = x.X1; x.B1 = x.B0 + BW;
        // a processor's rows, each its plug's lines; the block as tall as
        // its words need, its rows spread to meet it
        const groups = procs.map(p => {
            const name = this._bWrap(book, p.backup ? `${p.title} and ${p.backup}` : p.title, DZ.name, 700, PW - PAD * 2, 3);
            const red = p.redundancy ? this._bWrap(book, p.redundancy, DZ.small, 400, PW - PAD * 2, 2) : [];
            const words = name.length * 32 + (p.model ? 30 : 0) + red.length * 25 + PAD * 2 + 8;
            const hs = p.rows.map(r => Math.max(MIN_LINES, this._bfPlug(r, 'p').length, this._bfPlug(r, 'b').length) * LH + ROW_PAD);
            const sum = hs.reduce((a, b) => a + b, 0);
            const grow = sum < words ? (words - sum) / hs.length : 0;
            return { p, rows: p.rows, hs: hs.map(h => h + grow), h: Math.max(sum, words), name, red };
        });
        return { x, w: x.B1, groups };
    }

    // The groups split into k columns of whole processors, in order, the
    // tallest as short as it can be: [[group]], and the tallest's height.
    _bfColumns(groups, k) {
        const H = (list) => list.reduce((s, g) => s + g.h, 0) + Math.max(0, list.length - 1) * PROC_GAP;
        if (k <= 1 || groups.length < 2) return { cols: [groups], h: H(groups) };
        let best = null;
        for (let cut = 1; cut < groups.length; cut++) {
            const a = groups.slice(0, cut), b = groups.slice(cut);
            const h = Math.max(H(a), H(b));
            if (!best || h < best.h) best = { cols: [a, b], h };
        }
        return best;
    }

    // A processor too tall for a column, cut into pieces of whole rows that
    // fit `colH`; each piece after the first says it continues.
    _bfFitGroups(groups, colH) {
        const out = [];
        for (const g of groups) {
            if (g.h <= colH) { out.push(g); continue; }
            let piece = null;
            g.rows.forEach((r, i) => {
                const h = g.hs[i];
                if (!piece || piece.h + h > colH) {
                    piece = { ...g, rows: [], hs: [], h: 0, cont: !!piece || !!g.cont };
                    out.push(piece);
                }
                piece.rows.push(r);
                piece.hs.push(h);
                piece.h += h;
            });
        }
        return out;
    }

    // ---- the sheets ---------------------------------------------------------

    // The Fiber page: nothing where the show uses no fiber; otherwise the
    // layout that draws the drawing largest, all on one sheet where it
    // fits at the binder's base size. A drawing too tall for one column
    // splits into two side by side, and those two may stand a little
    // smaller than the base (TWO_MIN) to keep the page on one sheet - Matt's
    // two columns "of processors side by side". Past that it continues.
    _bFiberSheets(book) {
        if (!this.binderUsesFiber()) return;
        const procs = this._bfProcessors();
        if (!procs.length) return;
        const da = book.geo.da;
        const geo = this._bfGeometry(book, procs);
        const specs = this._bfStrandMapSpecs(procs);
        const pull = this._bfPullRows(book.list);
        const natural = this._bfTableNatural(book, specs, pull);
        const frame = GROUP_H + HEAD_H + HEAD_GAP;
        const under = BUBBLE_GAP + BUBBLE_H;
        // every layout, the tables BESIDE the drawing (as wide as their
        // rows ask where the sheet has the room, else as wide as it has -
        // they wrap) or UNDER it, across the sheet, for a drawing short
        // and wide; the largest kept - two drawing columns only where one
        // does not hold the drawing at 1
        const tries = [];
        const consider = (k, t, under_, split, drawW, drawH) => {
            const room = under_ ? da.w : da.w - drawW - COL_GAP * 2;
            const TW = Math.floor(Math.min(natural, (room - (t - 1) * COL_GAP) / t));
            if (TW < COL_W) return false;
            const blocks = this._bfTableBlocks(book, specs, pull, TW);
            if (t > blocks.length) return false;
            const tables = this._bSpread(blocks, t);
            const tablesH = tables ? Math.max(...tables.cols.map(c => c.h)) : 0;
            const w = under_ ? Math.max(drawW, t * TW + (t - 1) * COL_GAP) : drawW + COL_GAP * 2 + t * TW + (t - 1) * COL_GAP;
            const h = under_ ? drawH + BUBBLE_GAP + tablesH : Math.max(drawH, GROUP_H + tablesH);
            const s = Math.floor(Math.min(FILL_CAP, da.w / w, da.h / h) * 1000) / 1000;
            tries.push({ k, t, TW, scale: s, split, tables, extent: { w, h }, under: under_ });
            return true;
        };
        for (let k = 1; k <= Math.min(2, geo.groups.length); k++) {
            const split = this._bfColumns(geo.groups, k);
            const drawW = k * geo.w + (k - 1) * DRAW_GAP;
            const drawH = frame + split.h + under;
            for (let t = 1; t <= 3; t++) if (!consider(k, t, false, split, drawW, drawH)) break;
            for (let t = 1; t <= 4; t++) if (!consider(k, t, true, split, drawW, drawH)) break;
        }
        const pick = (list) => list.reduce((best, x) => (!best || x.scale > best.scale * 1.01 ? x : best), null);
        const oneFits = tries.some(x => x.k === 1 && x.scale >= 1);
        const best = pick(tries.filter(x => x.scale >= 1))
            || (!oneFits && pick(tries.filter(x => x.k === 2 && x.scale >= TWO_MIN)));
        if (best) {
            this._bfPage(book, { scale: best.scale, extent: best.extent, cols: best.split.cols,
                                 tables: best.tables, tableCols: best.t, TW: best.TW, geo, cont: false, first: true,
                                 under: best.under });
            return;
        }
        // Too much for one sheet: the drawing first - two columns at TWO_MIN
        // or more where one will not hold it - the tables beside it as far
        // as they go, the rest on the next sheet at 1.
        const s2 = Math.floor(Math.min(1, da.w / (2 * geo.w + DRAW_GAP)) * 1000) / 1000;
        const two = geo.groups.length > 1 && s2 >= TWO_MIN;
        const oneColH = da.h - frame - under;
        const oneHolds = geo.groups.reduce((h, g, i) => h + g.h + (i ? PROC_GAP : 0), 0) <= oneColH;
        const S = two && !oneHolds ? s2 : 1;
        const n = two && !oneHolds ? 2 : 1;
        const colH = da.h / S - frame - under;
        // (the tables as wide as the room beside the drawing leaves, where
        // that is a table's width)
        const beside = Math.floor(da.w / S - (n * geo.w + (n - 1) * DRAW_GAP) - COL_GAP * 2);
        const TW = Math.min(natural, beside >= COL_W ? beside : DATA_COL_W);
        let groups = this._bfFitGroups(geo.groups, colH);
        let rest = this._bfTableBlocks(book, specs, pull, TW);
        let first = true;
        while (groups.length || rest.length) {
            const cols = [];
            const scale = groups.length ? S : 1;
            let i = 0;
            for (let c = 0; c < n && i < groups.length; c++) {
                const col = [];
                let h = 0;
                while (i < groups.length && (!col.length || h + PROC_GAP + groups[i].h <= colH)) {
                    h += (col.length ? PROC_GAP : 0) + groups[i].h;
                    col.push(groups[i++]);
                }
                cols.push(col);
            }
            groups = groups.slice(i);
            const drawW = cols.length ? cols.length * geo.w + (cols.length - 1) * DRAW_GAP + COL_GAP * 2 : 0;
            const across = Math.floor((da.w / scale - drawW + COL_GAP) / (TW + COL_GAP));
            let tables = null;
            if (across >= 1 && rest.length && !groups.length) {
                tables = this._bPack(rest, da.h / scale - GROUP_H, across);
                rest = tables.rest;
            }
            this._bfPage(book, { scale, extent: { w: da.w / scale, h: da.h / scale }, cols, tables,
                                 tableCols: tables ? tables.cols.length : 0, TW, geo, cont: !first, first });
            first = false;
            if (!cols.length && (!tables || !tables.cols.length)) break;
        }
    }

    // One Fiber sheet: the head, the drawing's columns, the bubble under
    // the first, the tables to the right - all at the sheet's fill scale.
    _bfPage(book, L) {
        const da = book.geo.da;
        const cont = L.cont ? ' (cont.)' : '';
        const titles = L.cols.flat().map(g => g.p.title).filter((t, i, a) => a.indexOf(t) === i);
        const view = L.cols.length && L.first ? ++book.views : null;
        const drawW = L.cols.length ? L.cols.length * L.geo.w + (L.cols.length - 1) * DRAW_GAP : 0;
        const tableX = da.x + (drawW && !L.under ? drawW + COL_GAP * 2 : 0);
        const fiber = { drawCols: L.cols.length, procs: L.cols.map(c => c.map(g => g.p.title + (g.cont ? ' (cont.)' : ''))),
                        tableCols: L.tableCols || 0, tableW: L.TW, drawW: L.geo.w, under: !!L.under };
        this._bPage(book, {
            kind: 'fiber', title: `Fiber${cont}`, sheetTitle: `FIBER${cont.toUpperCase()}`,
            subject: 'Fiber', layout: 'fiber', cols: L.cols.length + (L.tableCols || 0),
            scale: L.scale, extent: L.extent, names: titles, view, fiber,
        }, (page, scaled) => scaled(() => {
            const w = Math.max(drawW, tableX - da.x + (L.tableCols ? L.tableCols * L.TW + (L.tableCols - 1) * COL_GAP : 0));
            let tableY = da.y + GROUP_H;
            this._bGroupHead(book, `Fiber${cont}`, da.x, da.y, w);
            const top = da.y + GROUP_H;
            let low = top;
            L.cols.forEach((col, i) => {
                const x = da.x + i * (L.geo.w + DRAW_GAP);
                low = Math.max(low, this._bfDrawColumn(book, L.geo, col, x, top));
            });
            if (view) {
                this._bViewBubble(book, view, 'Fiber · processor to breakout box', da.x + 20, low + BUBBLE_GAP,
                                  'One row per link. Dashed: the extension at the breakout box end. A TAC pair flips between its ends.',
                                  Math.max(drawW, 900) - 20);
            }
            if (L.under) tableY = low + BUBBLE_GAP + BUBBLE_H + BUBBLE_GAP;
            if (L.tables) {
                L.tables.cols.forEach((col, i) => {
                    const x = tableX + i * (L.TW + COL_GAP);
                    for (const it of col.items) it.line.draw(book.ctx, x, tableY + it.y, L.TW);
                });
            }
            if (book.log && book.page && book.page.painting) {
                book.log.fiber = { ...fiber, scale: L.scale,
                                   drawX: L.cols.map((c, i) => this._bLogXY(book, da.x + i * (L.geo.w + DRAW_GAP), top)[0]),
                                   tableX: L.tables ? this._bLogXY(book, tableX, tableY)[0] : null,
                                   tableY: L.tables ? this._bLogXY(book, tableX, tableY)[1] : null,
                                   under: !!L.under };
            }
        }));
    }

    // ---- the drawing --------------------------------------------------------

    // One column of the drawing at (x0, y0): its headings, then each
    // processor's block and its rows. Returns the foot of what it drew.
    _bfDrawColumn(book, geo, groups, x0, y0) {
        const ctx = book.ctx;
        const X = geo.x;
        const heads = [['processor', X.P0, X.P1], ['output', X.T0, X.T1], ['at the processor', X.G0, X.G1],
                       ['cable', X.C0, X.C1], ['extension', X.J, X.E1], ['at the breakout', X.Q0, X.Q1],
                       ['breakout box', X.X0, X.B1]];
        for (const [t, a, b] of heads) {
            this._bText(book, t, x0 + (a + b) / 2, y0 + 28, { size: SZ.th, weight: 700, upper: true, align: 'center',
                                                            maxWidth: b - a + 12, shrink: true });
        }
        ctx.fillStyle = RULE;
        ctx.fillRect(x0, y0 + HEAD_H - 4, geo.w, 3);
        let y = y0 + HEAD_H + HEAD_GAP;
        groups.forEach((g, gi) => {
            if (gi) y += PROC_GAP;
            this._bfDrawGroup(book, geo, g, x0, y);
            y += g.h;
        });
        return y;
    }

    _bfDrawGroup(book, geo, g, x0, top) {
        const ctx = book.ctx;
        const X = geo.x;
        const ink = (warn) => (warn && book.meta.palette !== 'printer' ? WARN : INK);
        // the processor's block: its name (and its backup), model, redundancy
        ctx.strokeStyle = INK;
        ctx.lineWidth = 3;
        ctx.setLineDash([]);
        ctx.strokeRect(x0 + X.P0, top, X.P1 - X.P0, g.h);
        const cx = x0 + (X.P0 + X.P1) / 2;
        const name = g.cont ? [...g.name.slice(0, -1), `${g.name[g.name.length - 1]} (cont.)`] : g.name;
        const blockH = name.length * 32 + (g.p.model ? 30 : 0) + g.red.length * 25;
        let ty = top + (g.h - blockH) / 2 + 24;
        const maxWidth = X.P1 - X.P0 - PAD * 2;
        for (const t of name) { this._bText(book, t, cx, ty, { size: DZ.name, weight: 700, align: 'center', maxWidth, shrink: true }); ty += 32; }
        if (g.p.model) { ty -= 2; this._bText(book, g.p.model, cx, ty, { size: DZ.model, align: 'center', maxWidth, shrink: true }); ty += 30; }
        for (const t of g.red) { this._bText(book, t, cx, ty, { size: DZ.small, color: MUTED, align: 'center', maxWidth, shrink: true }); ty += 25; }
        // the rows
        const ys = [];
        let y = top;
        g.rows.forEach((r, i) => { ys.push({ y, h: g.hs[i], yc: y + g.hs[i] / 2 }); y += g.hs[i]; });
        g.rows.forEach((r, i) => {
            const { y: ry, h, yc } = ys[i];
            const pill = this._bfPill(r);
            const ext = this._bfExtLabel(r);
            const plugP = this._bfPlug(r, 'p');
            const plugB = this._bfPlug(r, 'b');
            // the output and the input, each in its tab
            this._bfTab(book, x0 + X.T0, x0 + X.T1, yc, r.cells[0]);
            this._bfTab(book, x0 + X.X0, x0 + X.X1, yc, r.link.title);
            // the leads from the tabs to the plugs, and the cable between
            ctx.strokeStyle = INK;
            ctx.setLineDash([]);
            const line = (a, b, width, dash) => {
                if (b - a < 1) return;
                ctx.lineWidth = width;
                ctx.setLineDash(dash || []);
                ctx.beginPath();
                ctx.moveTo(a, yc);
                ctx.lineTo(b, yc);
                ctx.stroke();
                ctx.setLineDash([]);
            };
            if (!pill.none) {
                line(x0 + X.T1, x0 + X.G0, 3);
                line(x0 + X.Q1, x0 + X.X0, 3);
                const pw = this._bfW(book, pill.text, DZ.pill, 700) + PILL_PAD * 2;
                const pc = x0 + (X.C0 + X.C1) / 2;
                const end = ext ? x0 + X.J : x0 + X.Q0;
                const copper = !!r.link.copper;
                line(x0 + X.G1, pc - pw / 2, copper ? 3 : 4.5);
                line(pc + pw / 2, end, copper ? 3 : 4.5);
                this._bwRound(ctx, pc - pw / 2, yc - PILL_H / 2, pw, PILL_H, PILL_H / 2, '#ffffff', INK, 2.5);
                this._bText(book, pill.text, pc, yc + DZ.pill * 0.36, { size: DZ.pill, weight: 700, align: 'center',
                                                                       color: ink(pill.warn) });
                if (ext) {
                    ctx.strokeStyle = INK;
                    line(x0 + X.J, x0 + X.Q0, 2.5, DASH);
                    this._bwSolid(ctx, x0 + X.J, yc, DOT, INK);
                    this._bText(book, ext.text, x0 + (X.J + X.Q0) / 2, yc - 9,
                                { size: DZ.ext, weight: ext.warn ? 700 : 400, align: 'center', color: ink(ext.warn),
                                  maxWidth: X.Q0 - X.J - 12, shrink: true });
                }
                this._bfPlugDraw(book, x0 + X.G0, x0 + X.G1, ry, h, plugP);
                this._bfPlugDraw(book, x0 + X.Q0, x0 + X.Q1, ry, h, plugB);
            } else {
                this._bText(book, pill.text, x0 + (X.G0 + X.Q1) / 2, yc + DZ.pill * 0.36,
                            { size: DZ.pill, color: MUTED, align: 'center' });
            }
        });
        // the breakout boxes: a box over its rows, a loop's two boxes
        // outlined together
        const segs = [];
        g.rows.forEach((r, i) => {
            const box = r.link.box;
            const last = segs[segs.length - 1];
            if (last && last.box === box) { last.to = i; return; }
            segs.push({ box, from: i, to: i });
        });
        const outlines = [];
        segs.forEach((s, j) => {
            const prev = segs[j - 1];
            const pair = prev && typeof this.fiberLoopPair === 'function' ? this.fiberLoopPair(s.box) : null;
            if (pair && pair.near === prev.box && pair.far === s.box && outlines.length) {
                outlines[outlines.length - 1].push(s);
            } else outlines.push([s]);
        });
        for (const o of outlines) {
            const a = ys[o[0].from], b = ys[o[o.length - 1].to];
            const bx = x0 + X.B0, bw = X.B1 - X.B0;
            ctx.strokeStyle = INK;
            ctx.lineWidth = 3;
            ctx.setLineDash([]);
            ctx.strokeRect(bx, a.y + 4, bw, b.y + b.h - a.y - 8);
            o.forEach((s, k) => {
                const sa = ys[s.from], sb = ys[s.to];
                if (k) { ctx.fillStyle = FAINT; ctx.fillRect(bx + 12, sa.y - 1, bw - 24, 2); }
                // the name, and under it the note on the lines the box
                // has room for
                const mid = (sa.y + sb.y + sb.h) / 2;
                const room = bw - PAD * 2;
                const note = this._bfBoxNote(s.box);
                const fit = Math.max(1, Math.floor((sb.y + sb.h - sa.y - 52) / 22));
                const lines = note ? this._bWrap(book, note, DZ.note, 400, room, fit) : [];
                let ty = mid - (26 + lines.length * 22) / 2 + 21;
                this._bText(book, this._bBoxTitle(s.box), bx + PAD, ty,
                            { size: DZ.box, weight: 700, maxWidth: room, shrink: true });
                for (const t of lines) {
                    ty += 22;
                    this._bText(book, t, bx + PAD, ty + 2, { size: DZ.note, color: MUTED, maxWidth: room, shrink: true });
                }
            });
        }
    }

    // A tab: a grey box on the row's middle, its words centred.
    _bfTab(book, a, b, yc, text) {
        const ctx = book.ctx;
        ctx.fillStyle = book.meta.palette === 'printer' ? '#ffffff' : BAND_BG;
        ctx.fillRect(a, yc - TAB_H / 2, b - a, TAB_H);
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.strokeRect(a, yc - TAB_H / 2, b - a, TAB_H);
        this._bText(book, text, (a + b) / 2, yc + DZ.tab * 0.36, { size: DZ.tab, align: 'center', maxWidth: b - a - 8, shrink: true });
    }

    // A plug: a rounded box over the row, its strands a line each - the
    // swatch, then the name - stood as one block on the plug's middle.
    _bfPlugDraw(book, a, b, ry, h, list) {
        if (!list.length) return;
        const ctx = book.ctx;
        this._bwRound(ctx, a, ry + 5, b - a, h - 10, 8, '#ffffff', RULE, 2);
        const lead = list.some(x => x.swatch) ? SW + 8 : 0;
        const top = ry + (h - list.length * LH) / 2;
        list.forEach((x, i) => {
            const base = top + i * LH + LH / 2 + DZ.strand * 0.36;
            const tx = a + PAD;
            if (x.swatch) {
                const sy = top + i * LH + (LH - SW) / 2;
                ctx.fillStyle = x.swatch.base || '#777777';
                ctx.fillRect(tx, sy, SW, SW);
                if (x.swatch.tracer) {
                    ctx.fillStyle = x.swatch.tracer;
                    ctx.fillRect(tx, sy + SW * 0.36, SW, SW * 0.28);
                }
                ctx.strokeStyle = INK;
                ctx.lineWidth = 1.5;
                ctx.strokeRect(tx, sy, SW, SW);
            }
            this._bText(book, x.text, tx + (x.muted && !x.swatch ? 0 : lead), base,
                        { size: x.muted ? DZ.small : DZ.strand, color: x.muted ? MUTED : INK,
                          maxWidth: b - a - PAD * 2 - lead, shrink: true });
        });
    }
}

for (const k of Object.getOwnPropertyNames(_BinderFiber.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_BinderFiber.prototype, k));
    }
}
