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
//     home run. A snake is said ONCE for the show, keyed by the snake
//     itself: since 2026-09-09 one holds sockets from as many cards and
//     boxes as it was formed across ("Any sockets, any device"), and it is
//     still one cable to pull - its hardware rows land on every processor
//     it touches. A snaked port's EXTENSION (the shorter cable from the
//     snake's fan-out to the panel, 2026-09-07) is one `Ether-con` +
//     length row under the port's label with "ext · <snake>" in Notes,
//     and ONE `Ether-con Barrel` EA row under the same label beside it -
//     the coupler that joins the extension to the snake's fan-out
//     ("every time we add an extension to a snake, we need to count for
//     one barrel so a snake of four with four extensions would be four
//     ethercon barrels", 2026-09-07). A loose port's own home run joins
//     nothing, so it takes no barrel.
//   * the BACKUP end of a port (the socket its return comes back on -
//     backedBy, the card's 1:1 partner or the box's) is walked exactly like
//     the primary: its snake said once, its cable or extension as a row
//     under the RETURN label ("SR-1R"), its box's fiber said once. "i have
//     no way of putting lengths for redundancy cables" (2026-09-07) - the
//     length is typed on the backup card's or box's own ≡ sheet.
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
//   * BEACHES (2026-09-08, "beach locations need to be addable for data";
//     "you can either create a beach or you can pick one from the
//     drop-down of one that you created earlier in the project"): the
//     project keeps its beaches as a LIST in order (project.beaches, see
//     app-beaches.js), and a screen, a distro and a breakout box each
//     PICK one (`beachId`, nullable) - the Beach picker in Screen Info,
//     on the distro's ⚙ and on the box's ⚙. The positions are the
//     beaches in that order, each holding the screens on it, then every
//     screen on no beach as its own position (pullPositions). Every row a
//     DEVICE produces is pulled where the device sits - "a screen, when
//     it's added to a distro or cvt will put all of it's gear at whatever
//     position the device is at": a box's Multi / L21-30 home run, its
//     Breakout, the cables and 2fer / 3fer of the circuits on it and their
//     power jumpers go to the DISTRO's beach; a port's home run / snake /
//     extension / backup rows and its data jumpers go to the beach of the
//     BOX delivering the socket; a box's fiber trunk goes to the box's
//     beach. A screen's own position is only the fallback for a device on
//     no beach, and the home of a socket straight off a card (processors
//     have no beach). A screen GROUP named like a beach folds INTO that
//     beach's position (its members with no beachId count as on it), so
//     the earlier "groups are beaches" files keep working; any other group
//     is a position of its own as before. Position keys: `beach:<id>`,
//     the group id, `layer:<id>`. The free-text `location` the ⚙ fields
//     used to carry is migrated on load into a beach of that name
//     (app.py _normalize_beaches); pullLocationOf still reads a leftover
//     `location` on a record nobody migrated, and such a name is its own
//     position keyed `loc:<name lower-cased>` while rows land on it. Pull
//     sheet EDITS keyed on those `loc:` keys are STALE after the
//     migration (the position is `beach:<id>` now) - the editor already
//     flags a stale key and keeps the edit, it is just never exported.
//   * GEAR rows, EA (2026-09-07, "processor doesnt need listing, and
//     neither do the cards, but CVT and distros yes. and list them per
//     beach location and if there is 2 cvts at one beach list them once
//     and add Qty 2"): one row per breakout box - the catalog model as the
//     type ("CVT4K-S", "Tessera XD"), its name or letter as the label - at
//     the box's location, else the position of the first screen whose
//     ports it delivers (a box delivering nothing, with no location, is
//     not listed); two boxes at one location merge to qty 2, label "A, B".
//     One row per distro with a box in use - "the distro should not be
//     named. it should say how many holes it uses. so 2 multi on a distro
//     is a 12 way, 3-4 is a 24 way, 5-6 is a 36 way and 7-8 is a 48 way":
//     the type is `<N> way` from the boxes in use, the label the distro's
//     name, at the distro's location, else the position of the first
//     screen it feeds. The table ends at 8: past it the type stays "48
//     way" and Notes say "<n> multis" - nothing larger is assumed.
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

    // The box on its own gear row ("CVT4K-S EA"): the type column already
    // says the model, so the label is what tells two boxes apart - the
    // name somebody typed ("SR") or the letter the dock gave it ("A").
    pullBoxLabel(box) {
        if (!box) return '';
        const name = String(box.name || '').trim();
        if (name) return name;
        const title = String(box.displayTitle || '').trim();
        const device = String(box.deviceName || '').trim();
        if (device && title.toLowerCase().startsWith(device.toLowerCase())) {
            return title.slice(device.length).trim() || title;
        }
        return title || device;
    }

    // The distro on its own gear row, by how many holes it uses: "2 multi
    // on a distro is a 12 way, 3-4 is a 24 way, 5-6 is a 36 way and 7-8 is
    // a 48 way" (2026-09-07). The table ends at 8; past it the type stays
    // "48 way" and the caller puts the count in Notes.
    pullDistroWayType(boxes) {
        const n = Number(boxes) || 0;
        if (n <= 2) return '12 way';
        if (n <= 4) return '24 way';
        if (n <= 6) return '36 way';
        return '48 way';
    }

    // Every location the project knows - the beach names, in beach order.
    // The ⚙ fields pick from project.beaches directly now (the Beach
    // picker); this stays for anything that wants the names as text.
    pullKnownLocations() {
        const seen = new Map();
        const add = (name) => {
            const text = String(name == null ? '' : name).trim();
            if (!text) return;
            const norm = text.toLowerCase();
            if (!seen.has(norm)) seen.set(norm, text);
        };
        const beaches = (typeof this.getBeaches === 'function')
            ? this.getBeaches() : ((this.project && this.project.beaches) || []);
        for (const b of beaches) add(b && b.name);
        return [...seen.values()];
    }

    // Where a device (a distro, a breakout box - raw or resolved) sits, as
    // the beach's NAME: read through its beachId; a typed `location` is
    // only read on a record nobody migrated yet.
    pullLocationOf(rec) {
        if (!rec) return null;
        if (rec.beachId) {
            const beach = (typeof this.beachById === 'function')
                ? this.beachById(rec.beachId)
                : (((this.project && this.project.beaches) || []).find(b => b && b.id === rec.beachId) || null);
            if (beach && String(beach.name || '').trim()) return String(beach.name).trim();
        }
        const text = String(rec.location == null ? '' : rec.location).trim();
        return text || null;
    }

    // Every breakout box on the resolved tree the dock reads: [{ box,
    // proc, card }].
    _pullAllBoxes() {
        const out = [];
        for (const proc of this._processorsResolved || []) {
            for (const slot of (proc && proc.slots) || []) {
                const card = slot && slot.card;
                if (!card) continue;
                for (const box of card.cvts || []) if (box) out.push({ box, proc, card });
            }
        }
        return out;
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
    // is silent (no plug is guessed). Copper only: a port's or a snake's
    // plug is never fiber - fiber is a breakout box's trunk row
    // (pullBoxFiberText), processor to box.
    pullDataConnectorWord(connectorId) {
        if (connectorId === 'cat') return 'Ether-con';
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

    // The screens' own positions: the project's beaches in ORDER, each with
    // the visible screens on it (beachId, or membership of a group named
    // like the beach), then - as before - one per screen group nobody put
    // on a beach (its name, its visible members in group order) and one
    // per loose screen, in order of first appearance down the layer list.
    // Each carries its editor key (`beach:<id>`, the group id, `layer:<id>`)
    // and the location name it answers to (its own name). A beach with
    // nothing on it is listed only while a device's rows land on it
    // (buildPullList); a device location matching none of these opens its
    // own position there too.
    pullPositions() {
        const out = [];
        const screens = this._pullScreens();
        const beaches = (typeof this.getBeaches === 'function')
            ? this.getBeaches() : ((this.project && this.project.beaches) || []).filter(b => b && b.id);
        const beachIds = new Set(beaches.map(b => b.id));
        const beachByNorm = new Map();
        for (const b of beaches) {
            const norm = String(b.name == null ? '' : b.name).trim().toLowerCase();
            if (norm && !beachByNorm.has(norm)) beachByNorm.set(norm, b.id);
        }
        const groupOf = (layer) => (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        // The beach a screen is on: its own pick first, else its group's name
        // when a beach is called that (the "groups are beaches" files).
        const beachOf = (layer) => {
            if (layer.beachId && beachIds.has(layer.beachId)) return layer.beachId;
            const group = groupOf(layer);
            if (group) {
                const norm = String(group.name == null ? '' : group.name).trim().toLowerCase();
                if (norm && beachByNorm.has(norm)) return beachByNorm.get(norm);
            }
            return null;
        };
        for (const beach of beaches) {
            const name = String(beach.name == null ? '' : beach.name).trim() || beach.id;
            out.push({ name, groupId: null, beachId: beach.id, key: `beach:${beach.id}`,
                       location: name, layers: screens.filter(l => beachOf(l) === beach.id) });
        }
        const seenGroups = new Set();
        for (const layer of screens) {
            if (beachOf(layer)) continue;
            const group = groupOf(layer);
            if (group) {
                if (seenGroups.has(group.id)) continue;
                seenGroups.add(group.id);
                const members = (this.getGroupMembers(group) || [])
                    .filter(l => l.visible !== false && !beachOf(l));
                const name = group.name || layer.name || '';
                out.push({ name, groupId: group.id, beachId: null, key: String(group.id), location: name,
                           layers: members.length ? members : [layer] });
            } else {
                const name = layer.name || `Screen ${layer.id}`;
                out.push({ name, groupId: null, beachId: null, key: `layer:${layer.id}`, location: name,
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

    // The socket a card port's return comes back on - { cardId, port, ... }
    // as processor_catalog link() wrote it onto the resolved port - or null
    // for a port nothing backs. Read off the resolved tree, never worked
    // out here: which socket backs which is the server's one answer.
    _pullBackedBy(cardId, socket) {
        const found = (typeof this._dockFindCard === 'function') ? this._dockFindCard(cardId) : null;
        if (!found) return null;
        const n = parseInt(socket, 10);
        const port = (found.card.ports || []).find(p => p.number === n);
        const bb = port && port.backedBy;
        return bb && bb.cardId && bb.port != null ? bb : null;
    }

    // ---- the list ----------------------------------------------------------

    // Every processor a snake reaches, through its members' devices. A
    // loom that crosses two machines is listed on both their hardware
    // sheets - the cable is really there twice over - and still counted
    // once on the show's totals, because the row is keyed by the snake.
    _snakeProcessorIds(snake) {
        const out = [];
        for (const m of (snake && snake.members) || []) {
            const owner = typeof this._dataCableOwner === 'function'
                ? this._dataCableOwner(m.kind, m.id) : null;
            if (owner && owner.procId && !out.includes(owner.procId)) {
                out.push(owner.procId);
            }
        }
        return out;
    }

    // The one authority. Shape:
    //   { positions: [{ name, key, groupId, location, memberIds, layerIds, rows }],
    //     totals: [rows],
    //     byScreen: { [layerId]: { name, rows, boxes, gangs: {twofer, threefer},
    //                              ports, snakes, jumpers: {data, power} } },
    //     hardware: [{ kind: 'distro'|'processor', id, name, rows }],
    //     settings, unmodelled: [strings] }
    // where a row is { type, length, qty, label, notes, side }. A
    // position's memberIds are the screens whose own position it is;
    // layerIds are every screen whose rows land on it (the members plus
    // any screen a located device pulled in). A screen's byScreen rows are
    // all of its rows wherever they were pulled.
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
        // Where a device's gear row falls back to when the device has no
        // location: the first screen a distro feeds, the first screen
        // whose port a box delivers.
        const distroFirstLayer = new Map();   // String(distroId) -> layerId
        const boxFirstLayer = new Map();      // boxId -> layerId
        // The tail cache is a per-tick memo keyed by layer object; a build
        // that follows an edit in the same tick must not read stale names.
        this._circuitTailCache = null;

        // The positions, keyed. The screens' own come first, in layer
        // order; a device location that matches none of them opens its
        // own as the first row reaches it.
        const positions = [];
        const byKey = new Map();
        const byName = new Map();             // trimmed, lower-cased name -> key
        const ownKey = new Map();             // layerId -> the screen's own key
        const open = (base) => {
            const pos = { name: base.name, key: base.key, groupId: base.groupId,
                          location: base.location, memberIds: [], layerIds: [], rows: [] };
            positions.push(pos);
            byKey.set(pos.key, pos);
            const norm = String(pos.name || '').trim().toLowerCase();
            if (norm && !byName.has(norm)) byName.set(norm, pos.key);
            return pos;
        };
        const bases = this.pullPositions();
        for (const base of bases) {
            const pos = open(base);
            pos.memberIds = base.layers.map(l => l.id);
            pos.layerIds = pos.memberIds.slice();
            base.layers.forEach(l => ownKey.set(l.id, pos.key));
        }
        // The position a location name stands for: the group (or loose
        // screen) of that name, else a position of its own.
        const locationKey = (name) => {
            const text = String(name == null ? '' : name).trim();
            if (!text) return null;
            const norm = text.toLowerCase();
            if (byName.has(norm)) return byName.get(norm);
            const key = `loc:${norm}`;
            if (!byKey.has(key)) open({ name: text, key, groupId: null, location: text });
            return key;
        };
        const land = (key, r, layerId) => {
            const pos = byKey.get(key);
            if (!pos) return;
            pos.rows.push(r);
            if (layerId != null && !pos.layerIds.includes(layerId)) pos.layerIds.push(layerId);
        };

        for (const base of bases) {
            for (const layer of base.layers) {
                const scr = this._pullScreenList(layer, {
                    settings, distroById, boxesSeen, snakesSeen, fiberSeen, hw,
                    distroFirstLayer, boxFirstLayer,
                });
                byScreen[layer.id] = scr;
                // Every row goes where the device that produced it sits;
                // a row no device located stays with the screen.
                for (const r of scr.rows) {
                    land((r._at && locationKey(r._at)) || base.key, r, layer.id);
                }
            }
        }

        // GEAR, EA: the boxes and the distros themselves.
        const gearAt = (r, location, fallbackLayerId) => {
            const key = locationKey(location)
                || (fallbackLayerId != null ? ownKey.get(fallbackLayerId) : null);
            if (!key) return false;
            land(key, r, null);
            return true;
        };
        for (const { box, proc } of this._pullAllBoxes()) {
            const type = String(box.deviceName || '').trim();
            if (!type) continue;
            const r = { type, length: 'EA', qty: 1, label: this.pullBoxLabel(box),
                        notes: '', side: 'data' };
            if (!gearAt(r, this.pullLocationOf(box), boxFirstLayer.get(box.id))) continue;
            hw('processor', proc.id, proc.name || proc.deviceName || proc.id).rows.push({ ...r });
        }
        const boxesOn = new Map();            // String(distroId) -> boxes in use
        for (const key of boxesSeen) {
            const distroId = key.split('|')[0];
            boxesOn.set(distroId, (boxesOn.get(distroId) || 0) + 1);
        }
        for (const d of distros) {
            const n = boxesOn.get(String(d.id)) || 0;
            if (!n) continue;
            const r = { type: this.pullDistroWayType(n), length: 'EA', qty: 1,
                        label: d.name || '', notes: n > 8 ? `${n} multis` : '', side: 'power' };
            if (!gearAt(r, this.pullLocationOf(d), distroFirstLayer.get(String(d.id)))) continue;
            hw('distro', d.id, d.name).rows.push({ ...r });
        }

        // A device location is a position only while rows land on it.
        const listed = positions.filter(p => p.memberIds.length || p.rows.length);
        listed.forEach(p => { p.rows = this._pullMergeRows(p.rows); });
        const totals = this._pullMergeRows(listed.flatMap(p => p.rows));
        const hardware = [...hardwareRows.values()].map(h => ({
            kind: h.kind, id: h.id, name: h.name, rows: this._pullMergeRows(h.rows),
        }));
        // `side` rides along for the binder, which lists a screen's power
        // cable apart from its data cable; the workbook ignores it. `_at`
        // (where the row was pulled) has done its work.
        const strip = r => ({ type: r.type, length: r.length, qty: r.qty,
                              label: r.label, notes: r.notes, side: r.side || 'power' });
        listed.forEach(p => { p.rows = p.rows.map(strip); });
        hardware.forEach(h => { h.rows = h.rows.map(strip); });
        Object.values(byScreen).forEach(s => { s.rows = this._pullMergeRows(s.rows).map(strip); });
        return {
            positions: listed,
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
        const distroFirstLayer = ctx.distroFirstLayer || new Map();
        const boxFirstLayer = ctx.boxFirstLayer || new Map();
        const rows = [];
        // Rows are power until the data walk below flips the switch: the
        // binder prints a screen's power cable and data cable apart.
        let side = 'power';
        // `at` is the location of the device that produced the row (the
        // distro's, the box's) - buildPullList pulls the row there; null
        // leaves it with the screen.
        const row = (type, length, qty, label, notes, at) => {
            const r = { type, length, qty, label: label || '', notes: notes || '', side,
                        _at: at || null };
            rows.push(r);
            return r;
        };
        const locationOf = (d) => this.pullLocationOf(d);
        const out = {
            name: layer.name || '', rows, boxes: [], gangs: { twofer: 0, threefer: 0 },
            ports: [], snakes: [], jumpers: { data: 0, power: 0 },
        };

        // ---- power: boxes, breakouts, circuit cables, gangs, jumpers ----
        const breakout = this.getPowerBreakout(layer);
        const screenConn = this.pullPowerConnectorName(breakout.connector);
        const plan = this.getSocaPlan(layer);
        const boxes = new Map();    // "distroId|number" -> box
        const circuitDistro = new Map();   // circuit number -> its distro, or null
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
            const d = box.distroId ? distroById.get(box.distroId) || null : null;
            for (const leg of s.legs) {
                circuitDistro.set(leg.circuit, d);
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
                        this.pullLengthText(cable.ft), 1, leg.label, '', locationOf(d));
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
            const at = locationOf(distroById.get(box.distroId));
            if (!distroFirstLayer.has(String(box.distroId))) {
                distroFirstLayer.set(String(box.distroId), layer.id);
            }
            const boxLabel = `${distroName}${box.number}`;
            const isL2130 = String(box.typeId || '').startsWith('l2130');
            const homeType = isL2130 ? 'L21-30' : 'Multi';
            const r = row(homeType, this.pullLengthText(box.homeRun), 1, boxLabel,
                          box.homeRun ? '' : 'no length', at);
            const breakoutType = isL2130
                ? `L21-30 ${box.connector} Breakout` : `${box.connector} Breakout`;
            const b = row(breakoutType, 'EA', 1, boxLabel, '', at);
            const hrec = hw('distro', box.distroId, distroName);
            hrec.rows.push({ ...r }, { ...b });
        }
        // Gangs: a circuit made of two runs is a 2fer, three a 3fer. Both
        // the gang and the circuit's jumpers go with the circuit's distro.
        const powerJumps = new Map();   // location (or '') -> { at, n }
        for (const c of this.screenCircuits(layer)) {
            const ways = Array.isArray(c.runIds) ? c.runIds.length : 1;
            const label = this.getPowerCircuitLabel(layer, c.num);
            const at = locationOf(circuitDistro.get(c.num));
            if (ways === 2) { out.gangs.twofer++; row(`${screenConn} 2fer`, 'EA', 1, label, '', at); }
            else if (ways >= 3) { out.gangs.threefer++; row(`${screenConn} 3fer`, 'EA', 1, label, '', at); }
            // Jumpers: one per row step within each run of the circuit.
            const runs = Array.isArray(c.branches) && c.branches.length ? c.branches : [c.panels];
            let off = 0;
            let steps = 0;
            for (const run of runs) {
                const layers = c.layers ? c.layers.slice(off, off + run.length) : null;
                off += run.length;
                steps += this._pullRowSteps(run, layers);
            }
            out.jumpers.power += steps;
            const bucket = powerJumps.get(at || '') || { at, n: 0 };
            bucket.n += steps;
            powerJumps.set(at || '', bucket);
        }
        for (const { at, n } of powerJumps.values()) {
            if (n <= 0) continue;
            row(settings.powerJumpName, this.pullLengthText(settings.powerJumpLength),
                n, layer.name, '', at);
        }

        // ---- data: port cables, snakes, extensions, backups, jumpers ----
        side = 'data';
        const asg = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        // One socket's share of the paper - the primary end and the backup
        // end are walked by the same hand, so nothing the backup carries
        // is said differently. In order: the breakout box delivering the
        // socket, if one does - its fiber trunk is one row (the fiber's
        // type or "Fiber", its length, the box's title) said once however
        // many ports ride it, and a box without a length has no row (the
        // binder's band says so); then the socket's run - a snake said
        // once, a loose cable as one `Ether-con 50'` row under `label`;
        // then, on a snaked socket, its EXTENSION as one `Ether-con 25'`
        // row under the same label with "ext · <snake>" in Notes and
        // the `Ether-con Barrel` EA that joins it to the fan-out. Every
        // row is pushed to the processor's hardware rows too. `into` is
        // the port entry (or its .backup) that records what was read.
        // Every row of a socket a BOX delivers is pulled where the box
        // sits (its location); a socket straight off a card stays with
        // the screen - a processor has no location.
        const owned = (cardId, socket) =>
            (cardId != null && socket != null && typeof this._dataPortOwner === 'function'
                ? this._dataPortOwner(cardId, socket) : null);
        const boxAt = (owner) => (owner && owner.kind === 'cvt' ? locationOf(owner.rec) : null);
        const walk = (cardId, socket, label, into) => {
            const owner = owned(cardId, socket);
            if (!owner) return;
            const at = boxAt(owner);
            const proc = (this.project.processors || []).find(p => p.id === owner.procId) || null;
            const procName = proc ? (proc.name || proc.deviceName || proc.id) : '';
            const push = (r) => { if (proc) hw('processor', proc.id, procName).rows.push({ ...r }); };
            if (owner.kind === 'cvt') {
                const box = owner.rec;
                into.box = this.pullBoxTitle(box);
                if (!boxFirstLayer.has(box.id)) boxFirstLayer.set(box.id, layer.id);
                const fiberText = this.pullBoxFiberText(box);
                if (fiberText && !fiberSeen.has(box.id)) {
                    fiberSeen.add(box.id);
                    push(row((box.fiberType || '').trim() || 'Fiber',
                             this.pullLengthText(box.fiberFt), 1, into.box, '', at));
                }
            }
            const cable = this._dataPortCableOn(owner, socket);
            if (!cable) return;
            if (cable.kind === 'snake') {
                const s = cable.snake;
                const connId = this.dataPortConnectorId(owner, s.connector);
                const word = this.pullDataConnectorWord(connId);
                const ways = (s.members || []).length;
                into.snake = s.name || '';
                if (cable.ext != null) {
                    into.ext = cable.ext;
                    const extWord = this.pullDataConnectorWord(
                        this.dataPortConnectorId(owner, cable.extConnector));
                    push(row(extWord || 'Data Cable', this.pullLengthText(cable.ext), 1, label,
                             `ext · ${s.name || 'snake'}`, at));
                    // One barrel per extension (2026-09-07): the coupler
                    // between the fan-out and the extension, in the
                    // extension's connector word ("Ether-con Barrel" - the
                    // GEAR LIST's own type), EA, no notes. _pullMergeRows
                    // folds a snake's four into `Ether-con Barrel | EA | 4`.
                    // The backup end passes through here too, so its
                    // extension takes one as well.
                    push(row(extWord ? `${extWord} Barrel` : 'Barrel', 'EA', 1, label, '', at));
                }
                // ONE row for the loom, keyed by the SNAKE (2026-09-09:
                // "Any sockets, any device" - one snake can hold sockets
                // from several cards and boxes, and it is still one cable
                // to pull). Its hardware rows land on every processor it
                // touches, so a snake shared between two machines is on
                // both their sheets and counted once on the show's.
                const snakeKey = `snake:${s.id}`;
                if (snakesSeen.has(snakeKey)) return;
                snakesSeen.add(snakeKey);
                out.snakes.push({ name: s.name || '', ways, ft: s.ft || null,
                                  connector: connId || null, owner: owner.kind,
                                  ownerId: owner.id, id: s.id });
                const type = word ? `${word} Snake` : 'Snake';
                const ft = Number(s.ft);
                const snakeRow = { type, length: this.pullLengthText(ft),
                                   qty: 1, label: s.name || '',
                                   notes: [`${ways}-way`,
                                           (Number.isFinite(ft) && ft > 0)
                                               ? '' : 'no length']
                                       .filter(Boolean).join('; ') };
                const r = row(snakeRow.type, snakeRow.length, snakeRow.qty,
                              snakeRow.label, snakeRow.notes, at);
                for (const pid of this._snakeProcessorIds(s)) {
                    const p2 = (this.project.processors || [])
                        .find(x => x.id === pid) || null;
                    if (!p2) continue;
                    hw('processor', pid,
                       p2.name || p2.deviceName || p2.id).rows.push({ ...r });
                }
            } else {
                const word = this.pullDataConnectorWord(cable.id);
                into.cable = cable.text;
                push(row(word || 'Data Cable', this.pullLengthText(cable.ft), 1, label, '', at));
            }
        };
        // A run's jumpers go with the box delivering its primary socket.
        const dataJumps = new Map();    // location (or '') -> { at, n }
        for (const run of this._pullPortRuns(layer)) {
            const steps = this._pullRowSteps(run.panels, run.layers);
            out.jumpers.data += steps;
            const port = { num: run.num, label: run.label, cable: null, snake: null,
                           ext: null, box: null, backup: null };
            out.ports.push(port);
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const at = (placed && placed.cardId && placed.port != null)
                ? boxAt(owned(placed.cardId, placed.port)) : null;
            const bucket = dataJumps.get(at || '') || { at, n: 0 };
            bucket.n += steps;
            dataJumps.set(at || '', bucket);
            if (!placed || !placed.cardId || placed.port == null) continue;
            walk(placed.cardId, placed.port, run.label, port);
            // The backup end: the socket this port's return comes back on
            // (backedBy on the resolved card port - processor_catalog
            // link()), read off ITS card or box exactly like the primary,
            // under the return label.
            const bb = this._pullBackedBy(placed.cardId, placed.port);
            if (bb) {
                // The return label as the tray states it; the derivation
                // lives in deriveReturnLabel (one rule, never re-spelled).
                const label = (typeof this.getPortLabelText === 'function')
                    ? this.getPortLabelText(layer, run.num, 'return')
                    : this.deriveReturnLabel(run.label);
                port.backup = { label, cable: null, snake: null, ext: null, box: null };
                walk(bb.cardId, bb.port, label, port.backup);
            }
        }
        for (const { at, n } of dataJumps.values()) {
            if (n <= 0) continue;
            row(settings.dataJumpName, this.pullLengthText(settings.dataJumpLength),
                n, layer.name, '', at);
        }
        return out;
    }

    // ---- the edits ---------------------------------------------------------
    //
    // project.pullSheetEdits = { positions: { [positionKey]: {
    //     rows:  [{ key, qty?, label?, notes?, removed? }],   // engine rows
    //     added: [{ type, length, qty, label, notes, side? }] // free rows
    // } } }
    // positionKey is `beach:<id>` for a beach (2026-09-08), the group id for
    // a grouped position on no beach, `layer:<id>` for a loose screen, and
    // `loc:<name lower-cased>` for a typed device location nobody migrated
    // (2026-09-07 - an edit keyed on one of those is stale once the location
    // has become a beach); key is the engine row's `type|length`, which is
    // stable across a wall change (the count moves, the override still
    // applies).

    pullPositionKey(pos) {
        if (!pos) return '';
        if (pos.key) return String(pos.key);
        if (pos.groupId != null && pos.groupId !== '') return String(pos.groupId);
        const ids = Array.isArray(pos.memberIds) && pos.memberIds.length ? pos.memberIds : pos.layerIds;
        const id = Array.isArray(ids) ? ids[0] : pos.layerId;
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
