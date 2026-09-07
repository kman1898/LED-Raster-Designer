// app-pull-list: the pull list, built ONCE from the project and read by
// every paper that lists cable - the pull-sheet workbook now, the binder
// packet next.
//
// The user's own pull sheet (Google Sheets, exported to xlsx) is the shape
// this feeds: POSITIONS side by side, each a list of (Cable Type, Length,
// Qty, Label, Notes) rows in the GEAR LIST vocabulary, then TOTALS built
// from every position. Rulings (2026-09-06):
//
//   * a POSITION is a screen GROUP ("the beach location should be the
//     groupings"); an ungrouped screen is its own position, named after it.
//   * the thing a multi or an L21-30 breakout is, is a BOX. Its home run is
//     a property of the box and is said once - one `Multi` row per box on a
//     distro, whatever it feeds, two plan entries on one (distro, number)
//     being one box.
//   * a circuit's cable is the connector's NAME as the type (`Tru-1` for
//     True1 - the sheet's spelling - else powerCON / Edison / L6-20) plus
//     its length; a 2fer / 3fer is `<connector> 2fer` EA; a box on a distro
//     takes one `<connector> Breakout` EA.
//   * data: `Ether-con` + length for a loose CAT port cable, one
//     `Ether-con Snake` row per snake (qty 1, "6-way" in Notes - snakes of
//     different way counts are never merged), lengths as the snake's ONE
//     home run.
//   * JUMPERS: side-by-side cabinets link directly; each time a run steps
//     to another ROW a long jumper is needed - one per row step within a
//     run, counted per port (data) and per circuit (power). Names and
//     lengths are per project (project.pullSheet), defaults "Data Jump" 6'
//     and "Tru-1 Power Jump" 6'.
//   * a breakout box's FIBER TRUNK is one row per box, said once however
//     many ports ride it: its type (the box's fiberType, "Fiber" untyped)
//     and its length (fiberFt), both typed in the box's ⚙ (2026-09-07);
//     a box without a length has no row. `unmodelled` is empty.
//
//   * EDITS (2026-09-06, "edit in the app and then export a whole file i can
//     share"): buildPullList() is the engine, recomputed from the show every
//     time; project.pullSheetEdits holds the user's deltas on top - a qty /
//     label / notes override or a hide on an engine row (keyed by its
//     `type|length`, per position), and free rows added to a position.
//     buildPullSheet() = applyPullSheetEdits(buildPullList()) is what BOTH
//     exports read (the workbook and the binder's pull pages), so an edit
//     rides into every paper. An override on a row the show no longer
//     produces stays in the store, is flagged stale in the editor, and is
//     never exported. See app-pull-sheet-editor.js for the modal.
//
// Lengths print as `100'`, each-items as `EA`; quantities are integers;
// Label is the short names covered ("SR 1-4", "SNAKE A", "SR1-1, SR1-6");
// Notes are blank unless a rule above says otherwise. Sorting follows the
// sheet's own Apps Script: type A-Z with numbers inside a name compared as
// numbers, then length ascending, EA last.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const PULL_SHEET_DEFAULTS = {
    dataJumpName: 'Data Jump',
    dataJumpLength: 6,
    powerJumpName: 'Tru-1 Power Jump',
    powerJumpLength: 6,
    rev: '1.0',
};

// The sheet's spelling of each power connector. True1 is the only one the
// GEAR LIST spells differently from the app.
const POWER_CONNECTOR_SHEET_NAMES = { True1: 'Tru-1' };

class _PullList {

    // ---- project settings -------------------------------------------------

    getPullSheetDefaults() {
        return { ...PULL_SHEET_DEFAULTS };
    }

    // The project's pull-sheet settings, defaults filled in. Never returns
    // the stored object itself: readers must not mutate the project.
    getPullSheetSettings() {
        const stored = (this.project && this.project.pullSheet) || {};
        const out = { ...PULL_SHEET_DEFAULTS };
        for (const k of Object.keys(PULL_SHEET_DEFAULTS)) {
            if (stored[k] === undefined || stored[k] === null) continue;
            out[k] = stored[k];
        }
        return out;
    }

    // One setting, one history entry, one project POST. Lengths are feet
    // (a blank or non-number falls back to the default). Returns true when
    // something changed.
    setPullSheetSetting(key, value, action = 'Edit Pull Sheet Settings') {
        if (!this.project || !(key in PULL_SHEET_DEFAULTS)) return false;
        let v = value;
        if (/Length$/.test(key)) {
            const n = parseFloat(v);
            v = Number.isFinite(n) && n > 0 ? n : PULL_SHEET_DEFAULTS[key];
        } else {
            v = String(v == null ? '' : v).trim() || PULL_SHEET_DEFAULTS[key];
        }
        const current = this.getPullSheetSettings()[key];
        if (current === v) return false;
        if (!this.project.pullSheet) this.project.pullSheet = {};
        this.project.pullSheet[key] = v;
        // Project-level state, same doctrine as distros: snapshot after the
        // mutation, then persist. save_project merges top-level keys and
        // restore_project keeps whatever the file carries, so the setting
        // rides the project through undo, save and reload.
        this.saveState(action);
        this._persistPullSheetSettings();
        return true;
    }

    _persistPullSheetSettings() {
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pullSheet: this.project.pullSheet || {} }),
        }).catch(() => {});
        this._pullSheetPushQueue = (this._pullSheetPushQueue || Promise.resolve()).then(send);
        return this._pullSheetPushQueue;
    }

    // ---- vocabulary --------------------------------------------------------

    // "100'" for feet, "EA" for each-items, "" for a length nobody typed.
    pullLengthText(ft) {
        if (ft === 'EA') return 'EA';
        const n = Number(ft);
        if (!Number.isFinite(n) || n <= 0) return '';
        return `${Number.isInteger(n) ? n : +n.toFixed(1)}'`;
    }

    // What paper calls a breakout box (a CVT, a Tessera XD): its model and
    // the name somebody typed - "CVT4K-S SR" - the way a card is "H9 SR";
    // unnamed, the resolved title the dock wears ("CVT4K-S A").
    pullBoxTitle(box) {
        if (!box) return '';
        const name = String(box.name || '').trim();
        const device = String(box.deviceName || '').trim();
        if (name && device && !name.toLowerCase().startsWith(device.toLowerCase())) {
            return `${device} ${name}`;
        }
        return box.displayTitle || name || device;
    }

    // A box's fiber trunk as a line: "12 Tac Fiber 250'" (the type, or
    // "Fiber" when untyped, and the length), or '' with no length.
    pullBoxFiberText(box) {
        const ft = Number(box && box.fiberFt);
        if (!Number.isFinite(ft) || ft <= 0) return '';
        return `${(box.fiberType || '').trim() || 'Fiber'} ${this.pullLengthText(ft)}`;
    }

    pullPowerConnectorName(appName) {
        const name = String(appName || '').trim();
        return POWER_CONNECTOR_SHEET_NAMES[name] || name;
    }

    // The sheet's word for a data connector id, or null where the catalog
    // is silent (no plug is guessed).
    pullDataConnectorWord(connectorId) {
        if (connectorId === 'cat') return 'Ether-con';
        if (connectorId === 'fiber') return 'Fiber';
        return null;
    }

    // Natural compare for the sort: numbers inside a name read as numbers
    // (3G SDI before 12G SDI, Tru-1 2fer before Tru-1 3fer), case-blind.
    _pullNaturalCompare(a, b) {
        const split = s => String(s || '').toLowerCase().match(/\d+|\D+/g) || [];
        const pa = split(a), pb = split(b);
        for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
            if (pa[i] === undefined) return -1;
            if (pb[i] === undefined) return 1;
            const na = /^\d+$/.test(pa[i]), nb = /^\d+$/.test(pb[i]);
            if (na && nb) {
                const d = parseInt(pa[i], 10) - parseInt(pb[i], 10);
                if (d) return d;
            } else if (pa[i] !== pb[i]) {
                return pa[i] < pb[i] ? -1 : 1;
            }
        }
        return 0;
    }

    // Length order: numbers ascending, a blank after them, EA last.
    _pullLengthRank(length) {
        if (length === 'EA') return [2, 0];
        const n = parseFloat(String(length || '').replace(/'/g, ''));
        if (Number.isFinite(n)) return [0, n];
        return [1, 0];
    }

    _pullSortRows(rows) {
        return rows.slice().sort((a, b) =>
            this._pullNaturalCompare(a.type, b.type)
            || (() => {
                const ra = this._pullLengthRank(a.length), rb = this._pullLengthRank(b.length);
                return (ra[0] - rb[0]) || (ra[1] - rb[1]);
            })());
    }

    // Merge rows sharing (type, length): quantities add, labels and notes
    // union in first-seen order. Output is sorted.
    _pullMergeRows(rows) {
        const byKey = new Map();
        for (const r of rows) {
            if (!r || !r.type) continue;
            const key = `${r.type} ${r.length}`;
            let hit = byKey.get(key);
            if (!hit) {
                hit = { type: r.type, length: r.length, qty: 0, _labels: [], _notes: [] };
                byKey.set(key, hit);
            }
            hit.qty += Number(r.qty) || 0;
            if (!hit.side && r.side) hit.side = r.side;
            for (const l of (r._labels || (r.label ? [r.label] : []))) {
                if (l && !hit._labels.includes(l)) hit._labels.push(l);
            }
            for (const n of (r._notes || (r.notes ? [r.notes] : []))) {
                if (n && !hit._notes.includes(n)) hit._notes.push(n);
            }
        }
        return this._pullSortRows([...byKey.values()]
            .filter(r => r.qty > 0)
            .map(r => ({
                type: r.type, length: r.length, qty: r.qty,
                label: this._pullCompressNames(r._labels),
                notes: r._notes.join('; '),
                side: r.side || 'power',
                _labels: r._labels, _notes: r._notes,
            })));
    }

    // Short names covered: names ending in a number fold into ranges per
    // prefix ("SR1", "SR2", "SR3", "SR4" -> "SR 1-4"); anything else is
    // listed as typed. A list still longer than eight pieces after folding
    // (a wall's worth of circuit labels) is said as its ends and a count.
    _pullCompressNames(names) {
        const list = (names || []).filter(Boolean);
        if (!list.length) return '';
        const groups = new Map();      // prefix -> numbers
        const plain = [];
        for (const n of list) {
            const m = String(n).match(/^(.*?)(\d+)$/);
            // A circuit label like SR1-1 keeps its own text: folding its
            // tail number would read as a range of tails, not circuits.
            if (!m || /[-–]\d+$/.test(n)) { plain.push(String(n)); continue; }
            const prefix = m[1].trim();
            const arr = groups.get(prefix) || [];
            arr.push(parseInt(m[2], 10));
            groups.set(prefix, arr);
        }
        const out = [];
        for (const [prefix, nums] of groups) {
            const sorted = [...new Set(nums)].sort((a, b) => a - b);
            const runs = [];
            for (const n of sorted) {
                const last = runs[runs.length - 1];
                if (last && n === last[1] + 1) last[1] = n;
                else runs.push([n, n]);
            }
            const text = runs.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(', ');
            out.push(prefix ? `${prefix} ${text}` : text);
        }
        const pieces = [...out, ...plain];
        if (pieces.length > 8) return `${list[0]} … ${list[list.length - 1]} (${list.length})`;
        return pieces.join(', ');
    }

    // ---- the row-step rule -------------------------------------------------

    // How many long jumpers one run needs: a step between consecutive
    // cabinets that changes ROW (or crosses to another member's cabinet -
    // its rows are a different lattice, and the hop is a jump either way).
    _pullRowSteps(panels, layers) {
        let steps = 0;
        for (let i = 1; i < panels.length; i++) {
            const a = panels[i - 1], b = panels[i];
            if (!a || !b) continue;
            const la = layers && layers[i - 1] ? layers[i - 1] : null;
            const lb = layers && layers[i] ? layers[i] : null;
            if ((la || null) !== (lb || null) || a.row !== b.row) steps++;
        }
        return steps;
    }

    // ---- positions ---------------------------------------------------------

    // Screens the list counts: every visible screen layer, in layer order.
    // Hidden screens are off the wall the way getGroupTotals treats them.
    _pullScreens() {
        return ((this.project && this.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen' && l.visible !== false);
    }

    // The positions: one per screen group (its name, its visible members in
    // group order), one per ungrouped screen, in order of first appearance
    // down the layer list.
    pullPositions() {
        const out = [];
        const seenGroups = new Set();
        for (const layer of this._pullScreens()) {
            const group = (typeof this.getGroupOfLayer === 'function')
                ? this.getGroupOfLayer(layer) : null;
            if (group) {
                if (seenGroups.has(group.id)) continue;
                seenGroups.add(group.id);
                const members = (this.getGroupMembers(group) || [])
                    .filter(l => l.visible !== false);
                out.push({ name: group.name || layer.name || '', groupId: group.id,
                           layers: members.length ? members : [layer] });
            } else {
                out.push({ name: layer.name || `Screen ${layer.id}`, groupId: null,
                           layers: [layer] });
            }
        }
        return out;
    }

    // ---- per-screen readings -----------------------------------------------

    // The port runs of one screen: [{ num, label, panels, layers }].
    _pullPortRuns(layer) {
        const runs = [];
        if ((layer.flowPattern || 'tl-h') === 'custom' && layer.customPortPaths) {
            Object.keys(layer.customPortPaths)
                .map(n => parseInt(n, 10))
                .filter(n => Number.isFinite(n))
                .sort((a, b) => a - b)
                .forEach(n => {
                    const resolved = this.getResolvedPathPanels(layer, layer.customPortPaths[n] || []);
                    if (!resolved.length) return;
                    runs.push({ num: n, panels: resolved.map(r => r.panel),
                                layers: resolved.map(r => r.layer) });
                });
        } else {
            const byPort = new Map();
            const items = (typeof this.calculatePortAssignments === 'function')
                ? this.calculatePortAssignments(layer) : [];
            const layerOf = id => (id == null ? layer
                : (this.project.layers || []).find(l => l.id === id) || layer);
            items.forEach(it => {
                if (!it || !it.panel || it.panel.hidden) return;
                let run = byPort.get(it.port);
                if (!run) { run = { num: it.port, panels: [], layers: [] }; byPort.set(it.port, run); }
                run.panels.push(it.panel);
                run.layers.push(layerOf(it.layerId));
            });
            [...byPort.keys()].sort((a, b) => a - b).forEach(n => runs.push(byPort.get(n)));
        }
        runs.forEach(r => {
            r.label = (typeof this.getPortLabelText === 'function')
                ? this.getPortLabelText(layer, r.num, 'primary') : `P${r.num}`;
        });
        return runs;
    }

    // ---- the list ----------------------------------------------------------

    // The one authority. Shape:
    //   { positions: [{ name, layerIds, rows }], totals: [rows],
    //     byScreen: { [layerId]: { name, rows, boxes, gangs: {twofer, threefer},
    //                              ports, snakes, jumpers: {data, power} } },
    //     hardware: [{ kind: 'distro'|'processor', id, name, rows }],
    //     settings, unmodelled: [strings] }
    // where a row is { type, length, qty, label, notes }.
    buildPullList() {
        const settings = this.getPullSheetSettings();
        const distros = (typeof this.getDistros === 'function') ? this.getDistros() : [];
        const distroById = new Map(distros.map(d => [d.id, d]));
        const byScreen = {};
        const hardwareRows = new Map();   // key -> { kind, id, name, rows: [] }
        const hw = (kind, id, name) => {
            const key = `${kind}:${id}`;
            let rec = hardwareRows.get(key);
            if (!rec) { rec = { kind, id, name, rows: [] }; hardwareRows.set(key, rec); }
            return rec;
        };
        // Said once, wherever first met: a box on a distro (shared boxes
        // hold circuits of several screens) and a snake (its ports can feed
        // several screens).
        const boxesSeen = new Set();
        const snakesSeen = new Set();
        const fiberSeen = new Set();      // a box's fiber trunk, said once
        // The tail cache is a per-tick memo keyed by layer object; a build
        // that follows an edit in the same tick must not read stale names.
        this._circuitTailCache = null;

        const positions = this.pullPositions().map(pos => {
            const rows = [];
            for (const layer of pos.layers) {
                const scr = this._pullScreenList(layer, {
                    settings, distroById, boxesSeen, snakesSeen, fiberSeen, hw,
                });
                byScreen[layer.id] = scr;
                rows.push(...scr.rows);
            }
            return {
                name: pos.name,
                groupId: pos.groupId,
                layerIds: pos.layers.map(l => l.id),
                rows: this._pullMergeRows(rows),
            };
        });
        const totals = this._pullMergeRows(positions.flatMap(p => p.rows));
        const hardware = [...hardwareRows.values()].map(h => ({
            kind: h.kind, id: h.id, name: h.name, rows: this._pullMergeRows(h.rows),
        }));
        // `side` rides along for the binder, which lists a screen's power
        // cable apart from its data cable; the workbook ignores it.
        const strip = r => ({ type: r.type, length: r.length, qty: r.qty,
                              label: r.label, notes: r.notes, side: r.side || 'power' });
        positions.forEach(p => { p.rows = p.rows.map(strip); });
        hardware.forEach(h => { h.rows = h.rows.map(strip); });
        Object.values(byScreen).forEach(s => { s.rows = this._pullMergeRows(s.rows).map(strip); });
        return {
            positions,
            totals: totals.map(strip),
            byScreen,
            hardware,
            settings,
            // Nothing the show can carry is left off the list now: a
            // breakout box's fiber trunk rides its own fiberType / fiberFt.
            unmodelled: [],
        };
    }

    // One screen's share: its raw rows (merged later by the caller) and the
    // per-screen readings the packet prints.
    _pullScreenList(layer, ctx) {
        const { settings, distroById, boxesSeen, snakesSeen, fiberSeen, hw } = ctx;
        const rows = [];
        // Rows are power until the data walk below flips the switch: the
        // binder prints a screen's power cable and data cable apart.
        let side = 'power';
        const row = (type, length, qty, label, notes) => {
            const r = { type, length, qty, label: label || '', notes: notes || '', side };
            rows.push(r);
            return r;
        };
        const out = {
            name: layer.name || '', rows, boxes: [], gangs: { twofer: 0, threefer: 0 },
            ports: [], snakes: [], jumpers: { data: 0, power: 0 },
        };

        // ---- power: boxes, breakouts, circuit cables, gangs, jumpers ----
        const breakout = this.getPowerBreakout(layer);
        const screenConn = this.pullPowerConnectorName(breakout.connector);
        const plan = this.getSocaPlan(layer);
        const boxes = new Map();    // "distroId|number" -> box
        for (const s of plan) {
            const key = s.distroId ? `${s.distroId}|${s.number}` : `off|${layer.id}|${s.soca}`;
            let box = boxes.get(key);
            if (!box) {
                const d = s.distroId ? distroById.get(s.distroId) || null : null;
                const typed = d ? this.distroBoxType(d, s.number).type : null;
                box = {
                    key, name: s.name, number: s.number,
                    distroId: s.distroId || null, distro: d ? d.name : null,
                    type: typed ? typed.name : null,
                    typeId: typed ? typed.id : null,
                    homeRun: s.length || null,
                    connector: d
                        ? this.pullPowerConnectorName(
                            this.cableConnectorName(this.boxTailConnector(d, s.number, layer)))
                        : screenConn,
                    circuits: [],
                    shared: false,
                };
                boxes.set(key, box);
            } else if (!box.homeRun && s.length) {
                box.homeRun = s.length;
            }
            for (const leg of s.legs) {
                const cable = this.powerCircuitCable(layer, leg.circuit);
                box.circuits.push({
                    num: leg.circuit, label: leg.label, tail: leg.leg,
                    tiles: leg.tiles, amps: leg.amps,
                    cable: cable ? cable.text : null,
                    cableFt: cable ? cable.ft : null,
                    cableConnector: cable ? this.pullPowerConnectorName(cable.name) : null,
                });
                if (cable) {
                    row(cable.name ? this.pullPowerConnectorName(cable.name) : 'Power Cable',
                        this.pullLengthText(cable.ft), 1, leg.label);
                }
            }
        }
        for (const box of boxes.values()) {
            out.boxes.push(box);
            if (!box.distroId) continue;
            const seenKey = box.key;
            if (boxesSeen.has(seenKey)) { box.shared = true; continue; }
            boxesSeen.add(seenKey);
            const distroName = box.distro || '';
            const boxLabel = `${distroName}${box.number}`;
            const isL2130 = String(box.typeId || '').startsWith('l2130');
            const homeType = isL2130 ? 'L21-30' : 'Multi';
            const r = row(homeType, this.pullLengthText(box.homeRun), 1, boxLabel,
                          box.homeRun ? '' : 'no length');
            const breakoutType = isL2130
                ? `L21-30 ${box.connector} Breakout` : `${box.connector} Breakout`;
            const b = row(breakoutType, 'EA', 1, boxLabel);
            const hrec = hw('distro', box.distroId, distroName);
            hrec.rows.push({ ...r }, { ...b });
        }
        // Gangs: a circuit made of two runs is a 2fer, three a 3fer.
        for (const c of this.screenCircuits(layer)) {
            const ways = Array.isArray(c.runIds) ? c.runIds.length : 1;
            const label = this.getPowerCircuitLabel(layer, c.num);
            if (ways === 2) { out.gangs.twofer++; row(`${screenConn} 2fer`, 'EA', 1, label); }
            else if (ways >= 3) { out.gangs.threefer++; row(`${screenConn} 3fer`, 'EA', 1, label); }
            // Jumpers: one per row step within each run of the circuit.
            const runs = Array.isArray(c.branches) && c.branches.length ? c.branches : [c.panels];
            let off = 0;
            for (const run of runs) {
                const layers = c.layers ? c.layers.slice(off, off + run.length) : null;
                off += run.length;
                out.jumpers.power += this._pullRowSteps(run, layers);
            }
        }
        if (out.jumpers.power > 0) {
            row(settings.powerJumpName, this.pullLengthText(settings.powerJumpLength),
                out.jumpers.power, layer.name);
        }

        // ---- data: port cables, snakes, jumpers ----
        side = 'data';
        const asg = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        for (const run of this._pullPortRuns(layer)) {
            out.jumpers.data += this._pullRowSteps(run.panels, run.layers);
            const cable = (typeof this.dataPortCableForScreen === 'function')
                ? this.dataPortCableForScreen(layer, run.num) : null;
            const port = { num: run.num, label: run.label, cable: null, snake: null, box: null };
            out.ports.push(port);
            // The breakout box delivering this port, if one does: its fiber
            // trunk is one row - the fiber's type (or "Fiber"), its length,
            // the box's title - said once however many ports ride it. A box
            // without a length has no row; the binder's band says so.
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const owner = placed && placed.cardId && typeof this._dataPortOwner === 'function'
                ? this._dataPortOwner(placed.cardId, placed.port) : null;
            if (owner && owner.kind === 'cvt') {
                const box = owner.rec;
                port.box = this.pullBoxTitle(box);
                const fiberText = this.pullBoxFiberText(box);
                if (fiberText && !fiberSeen.has(box.id)) {
                    fiberSeen.add(box.id);
                    const proc = (this.project.processors || []).find(p => p.id === owner.procId) || null;
                    const r = row((box.fiberType || '').trim() || 'Fiber',
                                  this.pullLengthText(box.fiberFt), 1, port.box);
                    if (proc) hw('processor', proc.id, proc.name || proc.deviceName || proc.id).rows.push({ ...r });
                }
            }
            if (!cable) continue;
            const proc = cable.owner
                ? ((this.project.processors || []).find(p => p.id === cable.owner.procId) || null)
                : null;
            const procName = proc ? (proc.name || proc.deviceName || proc.id) : '';
            if (cable.kind === 'snake') {
                const s = cable.snake;
                const connId = this.dataPortConnectorId(cable.owner, s.connector);
                const word = this.pullDataConnectorWord(connId);
                const ways = (s.ports || []).length;
                const snakeKey = `${cable.owner.kind}:${cable.owner.id}:${s.id}`;
                port.snake = s.name || '';
                if (snakesSeen.has(snakeKey)) continue;
                snakesSeen.add(snakeKey);
                out.snakes.push({ name: s.name || '', ways, ft: s.ft || null,
                                  connector: connId || null, owner: cable.owner.kind,
                                  ownerId: cable.owner.id });
                const type = word ? `${word} Snake` : 'Snake';
                const ft = Number(s.ft);
                const r = row(type, this.pullLengthText(ft), 1, s.name || '',
                              [`${ways}-way`, (Number.isFinite(ft) && ft > 0) ? '' : 'no length']
                                  .filter(Boolean).join('; '));
                if (proc) hw('processor', proc.id, procName).rows.push({ ...r });
            } else {
                const word = this.pullDataConnectorWord(cable.id);
                port.cable = cable.text;
                const r = row(word || 'Data Cable', this.pullLengthText(cable.ft), 1, run.label);
                if (proc) hw('processor', proc.id, procName).rows.push({ ...r });
            }
        }
        if (out.jumpers.data > 0) {
            row(settings.dataJumpName, this.pullLengthText(settings.dataJumpLength),
                out.jumpers.data, layer.name);
        }
        return out;
    }

    // ---- the edits ---------------------------------------------------------
    //
    // project.pullSheetEdits = { positions: { [positionKey]: {
    //     rows:  [{ key, qty?, label?, notes?, removed? }],   // engine rows
    //     added: [{ type, length, qty, label, notes, side? }] // free rows
    // } } }
    // positionKey is the group id for a grouped position, `layer:<id>` for a
    // loose screen; key is the engine row's `type|length`, which is stable
    // across a wall change (the count moves, the override still applies).

    pullPositionKey(pos) {
        if (!pos) return '';
        if (pos.groupId != null && pos.groupId !== '') return String(pos.groupId);
        const id = Array.isArray(pos.layerIds) ? pos.layerIds[0] : pos.layerId;
        return `layer:${id}`;
    }

    pullRowKey(row) {
        return `${row && row.type != null ? row.type : ''}|${row && row.length != null ? row.length : ''}`;
    }

    // The stored edits, never the store itself (readers must not mutate).
    getPullSheetEdits() {
        const stored = (this.project && this.project.pullSheetEdits) || {};
        const positions = {};
        for (const [k, v] of Object.entries(stored.positions || {})) {
            if (!v || typeof v !== 'object') continue;
            positions[k] = {
                rows: Array.isArray(v.rows) ? v.rows.map(r => ({ ...r })) : [],
                added: Array.isArray(v.added) ? v.added.map(r => ({ ...r })) : [],
            };
        }
        return { positions };
    }

    pullSheetHasEdits() {
        const e = this.getPullSheetEdits();
        return Object.values(e.positions).some(p => p.rows.length || p.added.length);
    }

    // The live store for one position (created on demand when `create`).
    _pullPositionEdits(positionKey, create) {
        if (!this.project) return null;
        if (!this.project.pullSheetEdits || typeof this.project.pullSheetEdits !== 'object') {
            if (!create) return null;
            this.project.pullSheetEdits = { positions: {} };
        }
        const store = this.project.pullSheetEdits;
        if (!store.positions || typeof store.positions !== 'object') store.positions = {};
        let pos = store.positions[positionKey];
        if (!pos && create) { pos = { rows: [], added: [] }; store.positions[positionKey] = pos; }
        if (pos) {
            if (!Array.isArray(pos.rows)) pos.rows = [];
            if (!Array.isArray(pos.added)) pos.added = [];
        }
        return pos || null;
    }

    // Drop empty entries so the store says only what was changed.
    _pullPruneEdits() {
        const store = this.project && this.project.pullSheetEdits;
        if (!store || !store.positions) return;
        for (const [k, pos] of Object.entries(store.positions)) {
            pos.rows = (pos.rows || []).filter(r => r && r.key
                && (r.removed || r.qty !== undefined || r.label !== undefined || r.notes !== undefined));
            pos.added = (pos.added || []).filter(Boolean);
            if (!pos.rows.length && !pos.added.length) delete store.positions[k];
        }
        if (!Object.keys(store.positions).length) delete this.project.pullSheetEdits;
    }

    _pullQtyValue(v) {
        const n = Math.round(Number(v));
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    // A free row's side, for the binder's power / data split: a data word
    // in the type makes it data, everything else is power.
    pullGuessSide(type) {
        return /ether|cat\b|fiber|fibre|sdi|hdmi|data|snake|opt|sfp|tac/i.test(String(type || ''))
            ? 'data' : 'power';
    }

    // Engine list in, the list the papers print out: overrides overlaid,
    // hidden rows dropped, added rows appended, totals recomputed. A key
    // no edit touches keeps the engine's totals row verbatim (its folded
    // labels); a touched key is rebuilt from the edited position rows.
    applyPullSheetEdits(list) {
        const edits = this.getPullSheetEdits();
        const out = { ...list, positions: [], totals: (list.totals || []).slice() };
        const touched = new Set();
        const touchedRows = [];
        let any = false;
        for (const pos of list.positions || []) {
            const pe = edits.positions[this.pullPositionKey(pos)];
            const rows = [];
            for (const r of pos.rows || []) {
                const key = this.pullRowKey(r);
                const e = pe ? pe.rows.find(x => x.key === key) : null;
                if (!e) { rows.push({ ...r }); continue; }
                any = true;
                touched.add(key);
                if (e.removed) continue;
                const row = { ...r };
                const qty = this._pullQtyValue(e.qty);
                if (qty !== null) row.qty = qty;
                if (e.label !== undefined && e.label !== null) row.label = String(e.label);
                if (e.notes !== undefined && e.notes !== null) row.notes = String(e.notes);
                rows.push(row);
                touchedRows.push(row);
            }
            for (const a of (pe ? pe.added : [])) {
                const type = String(a && a.type || '').trim();
                const qty = this._pullQtyValue(a && a.qty);
                if (!type || qty === null) continue;
                any = true;
                const row = {
                    type, length: String(a.length || '').trim(), qty,
                    label: String(a.label || ''), notes: String(a.notes || ''),
                    side: a.side === 'data' || a.side === 'power' ? a.side : this.pullGuessSide(type),
                    added: true,
                };
                touched.add(this.pullRowKey(row));
                rows.push(row);
                touchedRows.push(row);
            }
            out.positions.push({ ...pos, rows: this._pullSortRows(rows) });
        }
        if (!any) return { ...list, positions: out.positions };
        const kept = out.totals.filter(t => !touched.has(this.pullRowKey(t)));
        const rebuilt = new Map();
        for (const pos of out.positions) {
            for (const r of pos.rows) {
                const key = this.pullRowKey(r);
                if (!touched.has(key)) continue;
                let hit = rebuilt.get(key);
                if (!hit) {
                    hit = { type: r.type, length: r.length, qty: 0, labels: [], notes: [], side: r.side || 'power' };
                    rebuilt.set(key, hit);
                }
                hit.qty += Number(r.qty) || 0;
                if (r.label && !hit.labels.includes(r.label)) hit.labels.push(r.label);
                if (r.notes && !hit.notes.includes(r.notes)) hit.notes.push(r.notes);
            }
        }
        const totals = kept.concat([...rebuilt.values()].map(h => ({
            type: h.type, length: h.length, qty: h.qty,
            label: h.labels.join(', '), notes: h.notes.join('; '), side: h.side,
        })));
        out.totals = this._pullSortRows(totals);
        return out;
    }

    // THE list both papers print: the engine's reading with the user's
    // edits on top.
    buildPullSheet() {
        return this.applyPullSheetEdits(this.buildPullList());
    }

    // For the editor: the stored overrides no engine row answers to any
    // more - kept, flagged, never exported. [{ positionKey, key, edit }].
    pullSheetStaleEdits(list) {
        const edits = this.getPullSheetEdits();
        const live = new Map();
        for (const pos of (list || this.buildPullList()).positions || []) {
            live.set(this.pullPositionKey(pos), new Set(pos.rows.map(r => this.pullRowKey(r))));
        }
        const out = [];
        for (const [positionKey, pe] of Object.entries(edits.positions)) {
            const keys = live.get(positionKey);
            for (const e of pe.rows) {
                if (!keys || !keys.has(e.key)) out.push({ positionKey, key: e.key, edit: { ...e } });
            }
        }
        return out;
    }

    // ---- the edits: one history entry each, then one project POST ----

    _commitPullSheetEdit(action) {
        this._pullPruneEdits();
        this.saveState(action);
        this._persistPullSheetEdits();
        if (typeof this.renderPullSheetEditorTotals === 'function') this.renderPullSheetEditorTotals();
    }

    _persistPullSheetEdits() {
        // A deleted store must reach the server as an empty object: POST
        // merges top-level keys and would otherwise keep the old edits.
        const body = { pullSheetEdits: (this.project && this.project.pullSheetEdits) || { positions: {} } };
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).catch(() => {});
        this._pullSheetPushQueue = (this._pullSheetPushQueue || Promise.resolve()).then(send);
        return this._pullSheetPushQueue;
    }

    // Override one field of an engine row. A value equal to the engine's
    // own clears the override for that field. `engineRow` (optional) is
    // the row as the engine says it, for that comparison. Returns true
    // when the store changed.
    setPullSheetRowEdit(positionKey, key, patch, engineRow, action = 'Edit Pull Sheet Row') {
        if (!this.project || !positionKey || !key || !patch) return false;
        const pos = this._pullPositionEdits(positionKey, true);
        let e = pos.rows.find(x => x.key === key);
        const before = JSON.stringify(e || null);
        if (!e) { e = { key }; pos.rows.push(e); }
        for (const field of ['qty', 'label', 'notes']) {
            if (!(field in patch)) continue;
            let v = patch[field];
            if (field === 'qty') {
                v = this._pullQtyValue(v);
                if (v === null) { delete e.qty; continue; }
            } else {
                v = String(v == null ? '' : v);
            }
            const engineV = engineRow ? engineRow[field] : undefined;
            if (engineV !== undefined && (field === 'qty' ? Number(engineV) === v : String(engineV || '') === v)) {
                delete e[field];
            } else {
                e[field] = v;
            }
        }
        this._pullPruneEdits();
        const after = this._pullPositionEdits(positionKey, false);
        const now = after ? after.rows.find(x => x.key === key) : null;
        if (JSON.stringify(now || null) === before) return false;
        this._commitPullSheetEdit(action);
        return true;
    }

    // Hide an engine row from every paper (restorable).
    removePullSheetRow(positionKey, key) {
        if (!this.project || !positionKey || !key) return false;
        const pos = this._pullPositionEdits(positionKey, true);
        let e = pos.rows.find(x => x.key === key);
        if (e && e.removed) return false;
        if (!e) { e = { key }; pos.rows.push(e); }
        e.removed = true;
        this._commitPullSheetEdit('Remove Pull Sheet Row');
        return true;
    }

    restorePullSheetRow(positionKey, key) {
        const pos = this._pullPositionEdits(positionKey, false);
        const e = pos && pos.rows.find(x => x.key === key);
        if (!e || !e.removed) return false;
        delete e.removed;
        this._commitPullSheetEdit('Restore Pull Sheet Row');
        return true;
    }

    // Forget every override on one engine row (the show's reading returns).
    resetPullSheetRow(positionKey, key) {
        const pos = this._pullPositionEdits(positionKey, false);
        if (!pos) return false;
        const n = pos.rows.length;
        pos.rows = pos.rows.filter(x => x.key !== key);
        if (pos.rows.length === n) return false;
        this._commitPullSheetEdit('Reset Pull Sheet Row');
        return true;
    }

    // A free row on a position. Returns its index in `added`, or -1.
    addPullSheetRow(positionKey, row) {
        if (!this.project || !positionKey) return -1;
        const pos = this._pullPositionEdits(positionKey, true);
        const r = row || {};
        pos.added.push({
            type: String(r.type || '').trim(),
            length: String(r.length || '').trim(),
            qty: this._pullQtyValue(r.qty) || 1,
            label: String(r.label || ''),
            notes: String(r.notes || ''),
        });
        this._commitPullSheetEdit('Add Pull Sheet Row');
        return pos.added.length - 1;
    }

    updatePullSheetAddedRow(positionKey, index, patch) {
        const pos = this._pullPositionEdits(positionKey, false);
        const a = pos && pos.added[index];
        if (!a || !patch) return false;
        const before = JSON.stringify(a);
        if ('type' in patch) a.type = String(patch.type || '').trim();
        if ('length' in patch) a.length = String(patch.length || '').trim();
        if ('qty' in patch) a.qty = this._pullQtyValue(patch.qty) || a.qty || 1;
        if ('label' in patch) a.label = String(patch.label == null ? '' : patch.label);
        if ('notes' in patch) a.notes = String(patch.notes == null ? '' : patch.notes);
        if (JSON.stringify(a) === before) return false;
        this._commitPullSheetEdit('Edit Pull Sheet Row');
        return true;
    }

    removePullSheetAddedRow(positionKey, index) {
        const pos = this._pullPositionEdits(positionKey, false);
        if (!pos || !pos.added[index]) return false;
        pos.added.splice(index, 1);
        this._commitPullSheetEdit('Remove Pull Sheet Row');
        return true;
    }

    // ---- the export --------------------------------------------------------

    // Today as the sheet's DATE cell says it ("Sep 6, 2026"), plus the ISO
    // form so the server can write a real date.
    _pullSheetDate() {
        const d = new Date();
        const pad = n => String(n).padStart(2, '0');
        return {
            date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
            date_iso: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
        };
    }

    // The engineer's name lives in the server preferences (`engineerName`):
    // it is the same person show after show, so it is a preference, not a
    // project field - and a file handed to another engineer prints theirs.
    getEngineerName() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return String(prefs.engineerName || '').trim();
    }

    setEngineerName(name) {
        const v = String(name == null ? '' : name).trim();
        if (this.getEngineerName() === v) return false;
        const prefs = { ...(typeof this.getPreferences === 'function' ? this.getPreferences() : {}),
                        engineerName: v };
        this._serverPreferences = prefs;
        try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (_) {}
        return fetch('/api/preferences', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs),
        }).then(() => true).catch(() => false);
    }

    // POST the list, save the workbook - straight to disk through the same
    // path the PDF takes (saveBlobWithPicker), no window, no print dialog.
    async exportPullSheet(projectName) {
        const name = projectName || (this.project && this.project.name) || 'Project';
        if (typeof this.refreshPortAssignment === 'function') {
            // dataPortCableForScreen reads the resolved assignment; make
            // sure it describes the screens as they stand now.
            try { await this.refreshPortAssignment(); } catch (_) {}
        }
        const pullList = this.buildPullSheet();
        const settings = pullList.settings;
        const body = {
            project_name: name,
            ...this._pullSheetDate(),
            engineer: this.getEngineerName(),
            rev: settings.rev,
            pull_list: pullList,
        };
        sendClientLog('export_pull_sheet_start', {
            positions: pullList.positions.length,
            rows: pullList.positions.reduce((s, p) => s + p.rows.length, 0),
        });
        const response = await fetch('/api/export/pull-sheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            let msg = 'Failed to build the pull sheet';
            try { msg = (await response.json()).error || msg; } catch (_) {}
            throw new Error(msg);
        }
        let warnings = [];
        try {
            const raw = response.headers.get('X-Pull-Sheet-Warnings');
            if (raw) warnings = JSON.parse(raw);
        } catch (_) { warnings = []; }
        const blob = await response.blob();
        await this.saveBlobWithPicker(
            blob, `${name}-pull-sheet.xlsx`,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
        if (warnings.length && typeof this._toast === 'function') {
            this._toast(warnings.join(' '), false, 8000);
        }
        return { warnings };
    }

    // ---- the export dialog's Pull Sheet section ------------------------

    // Wired once from setupEventListeners. Each field commits on change:
    // the jumper fields to project.pullSheet (one undo entry each), the
    // engineer to the preference.
    initPullSheetControls() {
        if (this._pullSheetControlsWired) return;
        this._pullSheetControlsWired = true;
        const bind = (id, key, action) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => {
                this.setPullSheetSetting(key, el.value, action);
                this.syncPullSheetControls();
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        };
        bind('export-pull-sheet-data-jump-name', 'dataJumpName', 'Set Data Jumper Name');
        bind('export-pull-sheet-data-jump-length', 'dataJumpLength', 'Set Data Jumper Length');
        bind('export-pull-sheet-power-jump-name', 'powerJumpName', 'Set Power Jumper Name');
        bind('export-pull-sheet-power-jump-length', 'powerJumpLength', 'Set Power Jumper Length');
        bind('export-pull-sheet-rev', 'rev', 'Set Pull Sheet Revision');
        const eng = document.getElementById('export-pull-sheet-engineer');
        if (eng) {
            eng.addEventListener('change', () => { this.setEngineerName(eng.value); });
        }
    }

    // Fields from state, and the section shown only for the pull-sheet
    // format (the picture sections mean nothing to a workbook).
    syncPullSheetControls() {
        const s = this.getPullSheetSettings();
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('export-pull-sheet-data-jump-name', s.dataJumpName);
        set('export-pull-sheet-data-jump-length', s.dataJumpLength);
        set('export-pull-sheet-power-jump-name', s.powerJumpName);
        set('export-pull-sheet-power-jump-length', s.powerJumpLength);
        set('export-pull-sheet-rev', s.rev);
        set('export-pull-sheet-engineer', this.getEngineerName());
        const formatEl = document.getElementById('export-format');
        const isSheet = !!formatEl && formatEl.value === 'pull-sheet';
        const show = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.style.display = on ? '' : 'none';
        };
        show('export-pull-sheet-section', isSheet);
        show('export-canvases-section', !isSheet);
        show('export-options-section', !isSheet);
        if (isSheet) show('export-views-section', false);
    }
}

for (const k of Object.getOwnPropertyNames(_PullList.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PullList.prototype, k));
    }
}
