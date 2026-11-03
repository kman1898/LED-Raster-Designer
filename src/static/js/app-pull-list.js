// app-pull-list: the pull list, built ONCE from the project and read by
// every paper that lists cable - the pull-sheet workbook now, the binder
// packet next.
//
// The user's own pull sheet (Google Sheets, exported to xlsx) is the shape
// this feeds: POSITIONS side by side, each a list of (Gear, Length,
// Qty, Label, Notes) rows in the GEAR LIST vocabulary, then TOTALS built
// from every position. Rulings (2026-09-06):
//
//   * a POSITION is a screen GROUP ("the beach location should be the
//     groupings"); an ungrouped screen is its own position, named after it.
//   * the thing a multi or an L21-30 breakout is, is a BOX. Its home run is
//     a property of the box and is said once - one `Multi` row per box on a
//     distro, whatever it feeds, two plan entries on one (distro, number)
//     being one box.
//   * a circuit's cable is the connector's NAME as the type (TRUE1 /
//     powerCON / Edison / L6-20) plus its length; a 2fer / 3fer is
//     `<panel input> 2fer` EA - the panels' side, TRUE1 or powerCON; a box
//     on a distro takes one `<connector> Breakout` EA per connector its
//     screens break out to. A circuit off an Edison or L6-20 breakout
//     takes one `Edison → TRUE1 cable` EA (2026-10-21). A DIRECT output's
//     one cable is the panel input, or both ends where the outlet is
//     another plug ("CEE 16A → TRUE1"); its length is its own column.
//   * data: `Cat6` (or `etherCON`, where the box's output is etherCON -
//     dataCableWord) + length for a loose port cable, `Cat6` with an empty
//     length and "no length" in Notes for a port with none typed, one
//     `Cat6 Snake` row per snake (qty 1, labelled by the port labels of
//     its sockets folded - "VX A-1 … A-4" - with "SNAKE A · 6 channel" in
//     Notes, 2026-10-21 - the type already says Snake, so snakeSizeText
//     does not say it again - two snakes are never merged, `apart`),
//     lengths as the snake's ONE home run. A snake is said ONCE for the show, keyed by the snake
//     itself: since 2026-09-09 one holds sockets from as many cards and
//     boxes as it was formed across ("Any sockets, any device"), and it is
//     still one cable to pull - its hardware rows land on every processor
//     it touches. A snaked port's EXTENSION (the shorter cable from the
//     snake's fan-out to the panel, 2026-09-07) is one `Cat6 Extension` +
//     length row under the socket's own port label ("VX A-1",
//     2026-10-21) with "ext · <snake>" in Notes,
//     and ONE `Cat6 Barrel` EA row under the same label beside it -
//     the coupler that joins the extension to the snake's fan-out
//     ("every time we add an extension to a snake, we need to count for
//     one barrel so a snake of four with four extensions would be four
//     ethercon barrels", 2026-09-07). A loose port's own home run joins
//     nothing, so it takes no barrel - unless the stock makes it of
//     several pieces: every join of two pieces is one more barrel (one per
//     channel on a snake). Power multis join without one; a powerCON
//     cable's join takes one `powerCON Coupler` EA, a TRUE1 cable's none
//     (2026-10-21, _pullPowerJoin).
//   * the BACKUP end of a port (the socket its return comes back on -
//     backedBy, the card's 1:1 partner or the box's) is walked exactly like
//     the primary: its snake said once, its cable or extension as a row
//     under the RETURN label ("SR-1R"), its box's fiber said once. "i have
//     no way of putting lengths for redundancy cables" (2026-09-07) - the
//     length is typed on the backup card's or box's own ≡ sheet.
//   * JUMPERS (2026-09-25, replacing the one-per-row-step count): every
//     link between two consecutive cabinets of a run, per port (data) and
//     per circuit branch (power), is a VERTICAL jumper (the cabinet above /
//     below - across a group seam too, when the members' cabinets touch)
//     at the screen's vertical length, a HORIZONTAL one (beside) at its
//     horizontal length, or a LONG one (not touching) measured center
//     to center along the panels, +1 ft, up to the stock ladder - the rule
//     and the per-screen lengths live in app-jumpers.js. Each LENGTH is its
//     own row under the jumper's name ("Data Jump 1'" x 200, "Data Jump 6'"
//     x 5); a short link on a screen whose length for that direction is
//     blank counts no cable. The NAMES are per project (project.pullSheet),
//     defaults "Data Jump", and one power jumper per panel input,
//     "TRUE1 Power Jump" and "powerCON Power Jump", each link named by the
//     panel input of the cabinet's own screen (2026-10-21).
//   * a breakout box's FIBER is its links' CABLES (2026-09-25,
//     app-fiber.js): each TAC, MTP or opticalCON is ONE row however many
//     boxes' links take it - "TAC 12 · ST", "MTP 24", "opticalCON QUAD"
//     with its length, under the cable's name, where the first box that
//     reaches it sits. A backup record bound to its primary (the same box
//     taking a second fiber) adds no EA row of its own. A 1.3 box's typed
//     fiber (fiberType / fiberFt) still prints as its own row - its type,
//     or "Fiber", and its length; none without a length - until a link on
//     the box has a cable. `unmodelled` is empty.
//
//   * EDITS (2026-09-06, "edit in the app and then export a whole file i can
//     share"): buildPullList() is the engine, recomputed from the show every
//     time; project.pullSheetEdits holds the user's deltas on top - a qty /
//     label / notes override or a hide on an engine row (keyed by its
//     `type|length`, per position), and free rows added to a position.
//     buildPullSheet() = applyPullSheetEdits(buildPullList()) is what BOTH
//     exports read (the workbook and the binder's pull pages), so an edit
//     rides into every paper - since 2026-10-21 the binder's per-screen
//     CABLES THIS SCREEN tables and the hardware pull lists as well (a
//     hidden row and a changed count; _pullCarryEdits has the rule). An
//     override on a row the show no longer
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
//     is a position of its own as before. A group is always ONE position
//     (2026-10-01): its members all stand on the beach of its first member
//     that is on one (screenBeachId), and its jumpers are a row per member
//     under the screen they sit on. Position keys: `beach:<id>`,
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
//     type ("CVT4K-S", "XD"), its name or letter as the label - at
//     the box's location, else the position of the first screen whose
//     ports it delivers (a box delivering nothing, with no location, is
//     not listed); two boxes at one location merge to qty 2, label "A, B".
//     One row per distro with a box in use: the type is the distro's
//     TYPE as typed behind its gear (2026-10-18, "200A 24ch rack";
//     a preset fills it with its name), "Distro" where it has none - the
//     old "<N> way" from the boxes in use is gone. The label is the
//     distro's name, at the distro's location, else the position of the
//     first screen it feeds.
//
//   * PANELS, EA (owner, 2026-10-22: "we need to have the pull sheet
//     include panel counts"): one row per panel type a screen hangs, under
//     the screen's own position, labelled with the screen's name - two
//     screens of one type on one position (a group's members) merge into
//     one row, "WALL SL, WALL SR". Blank and hidden cabinets, and hidden
//     screens, count none. A HALF TILE is a row of its own. The type is
//     the panel SAVED on the screen (picked from the panel library, or
//     named in Screen Info - "ROE Black Quartz 3.9 Full Tile"), its half
//     the library's matching half saved with it, else "<name> half"; a
//     show saved before is named by the library where its size and weight
//     find one model (catalogPanelNames). A cabinet nothing names is its
//     size, always in mm: "500 × 500 mm panel", "500 × 250 mm half
//     panel" (owner, 2026-10-22). A square
//     cabinet's two halves are one cabinet turned, so one row; on any
//     other the halves are told apart by their sizes (pullPanelTypes).
//     These rows are side 'panel': the binder's pull pages print them in
//     a Panels block beside the hardware, and they are on no screen's
//     CABLES THIS SCREEN table and no hardware pull list.
//
//   * CABLE STOCK (2026-10-20, app-cable-units.js): in a show that keeps
//     one, a multi's home run, a data cable and a circuit's cable are
//     written as the stock pieces that make them, and a row is ONE ROW PER
//     PIECE LENGTH - a 125' multi on 25 / 50 / 100 stock is `Multi 100'`
//     and `Multi 25'`, both under its label (_pullExpandPieces) - so the
//     sheet, its totals and the hardware rows count the cables pulled.
//
// Lengths print as `100'`, each-items as `EA`; quantities are integers;
// Label is the short names covered ("SR 1-4", "SNAKE A", "SR1-1, SR1-6");
// Notes are blank unless a rule above says otherwise. Sorting follows the
// sheet's own Apps Script: type A-Z with numbers inside a name compared as
// numbers, then length ascending, EA last.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The jumpers' LENGTHS are per screen since 2026-09-25 (app-jumpers.js);
// the project keeps their names. A file that still carries the old
// project-wide pullSheet.dataJumpLength / powerJumpLength keeps the key,
// read by nothing.
const PULL_SHEET_DEFAULTS = {
    dataJumpName: 'Data Jump',
    powerJumpNameTrue1: 'TRUE1 Power Jump',
    powerJumpNamePowercon: 'powerCON Power Jump',
    rev: '1.0',
};

// The one power jumper name a project or a preference kept before the
// per-connector names (2026-10-21). Customised, it carries over to TRUE1
// only; still the shipped one, it carries nothing.
const LEGACY_POWER_JUMP_NAME = 'Tru-1 Power Jump';

// The sheet's spelling of each power connector: the app's own now
// (2026-10-21, "TRUE1" and "powerCON" everywhere).
const POWER_CONNECTOR_SHEET_NAMES = {};

// The pull sheet spelled TRUE1 "Tru-1" until 2026-10-21, and older files
// key their edits on it ("Tru-1|10'", "Tru-1 Breakout|EA"); such an edit
// answers to the row under its TRUE1 name now (pullEditKey).
const PULL_LEGACY_TRUE1 = 'Tru-1';
// ... anywhere in the type, as a whole word ("L21-30 Tru-1 Breakout|EA",
// "Harting Tru-1 Breakout|EA" - 2026-10-22), either case.
const PULL_LEGACY_TRUE1_WORD = /(^|[\s(/])(?:Tru-1|TRU-1)(?=[\s)/]|$)/g;

// The Edison / L6-20 adapter cable printed as "Edison → TRUE1 tail" in the
// 1.5.4 betas; it is "Edison → TRUE1 cable" now (2026-10-21, never "tail"),
// and an edit keyed on the old row answers to the new one (pullEditKey).
const PULL_LEGACY_ADAPTER = /^((?:Edison|L6-20) → (?:TRUE1|powerCON)) tail(?=\||$)/;

// A distro's power in printed as "Feeder" / "L21-30 feeder" in the 1.5.4
// betas and "Feed" / "L21-30 feed" in the 1.6.0 betas; it is "Power in" /
// "L21-30 power in" now (2026-11-02), and an edit keyed on either old row
// answers to the new one (pullEditKey). Read against a row's TYPE; the
// words before " feed" must be a distro input's name, so an "SDI feed"
// stays what it is.
const PULL_LEGACY_FEEDER = /^(?:Feed(?:er)?|(.+) feed(?:er)?)$/;

// Brompton models as the pull sheet printed them until 2026-10-17 -
// "Tessera XD", "Tessera SX40" - and as older files key their edits. The
// catalog dropped the word (owner, 2026-10-17: "tessera is not needed"),
// and a pull-sheet edit is keyed on the type the row printed, so an edit
// saved on one of these names answers to the row under its name now
// (pullEditKey).
const PULL_LEGACY_TYPE_PREFIX = 'Tessera ';
const PULL_LEGACY_PREFIXED_TYPES = new Set(['SX40', 'S8', 'S4', 'M2', 'T1', 'SQ200',
    'QD-S', 'XD', 'XD-S', 'XD-T']);

// Data home runs as the sheet printed them until 2026-10-21 - "Ether-con",
// a bare "Data Cable" / "Snake" / "Barrel" where no connector was known -
// and as older files key their edits. Read alone (pullEditKey) each is its
// Cat6 row; read against its position's rows it is the etherCON row where
// the position has no Cat6 one, and a snake key the position's one snake
// of that length (_pullResolveEditKey).
const PULL_LEGACY_DATA_TYPES = new Map([
    ['Ether-con', 'Cat6'], ['Ether-con Snake', 'Cat6 Snake'],
    ['Ether-con Barrel', 'Cat6 Barrel'], ['Data Cable', 'Cat6'],
    ['Snake', 'Cat6 Snake'], ['Barrel', 'Cat6 Barrel'],
]);

// A free row's side (pullGuessSide): these words, whole, make it power
// whatever else it says ("Socapex Snake", "Camlok Barrel")...
// ("Light switch" is power, 2026-10-22: a switch alone is a network's)
const PULL_POWER_WORDS = new RegExp('\\b(?:socapex|soca|camlok|camlock|cam|edison|true1|tru-1|powercon'
    + '|harting|cee|nema|stage ?pin|l\\d{1,2}-\\d{2}|power|feeder|distro|light ?switch(?:es)?)\\b', 'i');
// ...and these make it data.
// RJ45, LC, coax, BNC and a network switch are data too (2026-10-22:
// "RJ45 coupler", "LC duplex patch", "Network switch", "Coax", "BNC").
const PULL_DATA_WORDS = new RegExp('\\b(?:ether\\w*|cat(?:5e?|6a?|7|8)?|fiber|fibre|\\w*sdi|hdmi|data'
    + '|snakes?|barrels?|tac\\s?\\d*|mtp\\s?\\d*|opticalcon\\w*|sfp\\+?|opt|cvt\\w*|xd(?:-\\w+)?'
    + '|\\w*rj-?45|lc|coax\\w*|bnc|switch(?:es)?|patch(?:es)?)\\b', 'i');
// A distro's FEED ("L21-30 feed", "Feed": the word that replaced "feeder"
// on 2026-11-01, which stays a power word above for older rows) is power
// too, but read after the data words: an "SDI feed" is still data.
// Whole word only, so "feedback" is not a feed.
const PULL_FEED_WORD = /\bfeeds?\b/i;
// (an RJ45 count glued to it is still RJ45: "Card H 20xRJ45"; a patch
// panel patches data - 2026-10-22)
// ...and, failing both, these make it a panel - only where nothing else
// in it says it is some other gear: "Breakout panel" is power, "Truss
// panel" is rigging (power, the default), never a panel (2026-10-22).
const PULL_PANEL_WORDS = /\b(?:panels?|cabinets?|tiles?)\b/i;
const PULL_NOT_PANEL_WORDS = /\b(?:breakouts?|truss(?:es)?|rigging|brackets?|bumpers?|headers?|clamps?|carts?|dolly|dollies|cases?|mounts?)\b/i;
// What may follow a catalog model and leave it the head of the name.
const PULL_MODEL_TAIL_WORDS = new Set(['rack', 'racks', 'case', 'cases', 'spare', 'spares', 'unit',
    'units', 'processor', 'processors', 'card', 'cards', 'box', 'boxes', 'frame', 'kit', 'backup',
    'pro', 'ea']);

class _PullList {

    // ---- project settings -------------------------------------------------

    // What a project starts from: the shipped values, under the Pull
    // sheet & cables preferences (rev, the two jumpers' names) where
    // those are set. The project's own pullSheet wins over both
    // (getPullSheetSettings).
    getPullSheetDefaults() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const out = { ...PULL_SHEET_DEFAULTS };
        const map = { rev: 'pullRev', powerJumpNameTrue1: 'powerJumpNameTrue1',
                      powerJumpNamePowercon: 'powerJumpNamePowercon', dataJumpName: 'dataJumpName' };
        for (const k of Object.keys(map)) {
            const v = prefs[map[k]];
            if (v != null && String(v).trim()) out[k] = String(v).trim();
        }
        if (!(prefs && prefs.powerJumpNameTrue1 != null)) {
            const legacy = this._legacyPowerJumpName(prefs && prefs.powerJumpName);
            if (legacy) out.powerJumpNameTrue1 = legacy;
        }
        return out;
    }

    // The old single power jumper name where somebody customised it, else
    // null: it carries over to TRUE1 only.
    _legacyPowerJumpName(value) {
        const v = String(value == null ? '' : value).trim();
        return v && v !== LEGACY_POWER_JUMP_NAME ? v : null;
    }

    // The project's pull-sheet settings, defaults filled in. Never returns
    // the stored object itself: readers must not mutate the project.
    getPullSheetSettings() {
        const stored = (this.project && this.project.pullSheet) || {};
        const out = this.getPullSheetDefaults();
        if (stored.powerJumpNameTrue1 == null) {
            const legacy = this._legacyPowerJumpName(stored.powerJumpName);
            if (legacy) out.powerJumpNameTrue1 = legacy;
        }
        for (const k of Object.keys(PULL_SHEET_DEFAULTS)) {
            if (stored[k] === undefined || stored[k] === null) continue;
            out[k] = stored[k];
        }
        return out;
    }

    // The power jumper's name for a panel input id ('true1' / 'powercon').
    pullPowerJumpName(settings, inputId) {
        const s = settings || this.getPullSheetSettings();
        return inputId === 'powercon' ? s.powerJumpNamePowercon : s.powerJumpNameTrue1;
    }

    // One setting, one history entry, one project POST (a blank falls
    // back to the default). Returns true when something changed.
    setPullSheetSetting(key, value, action = 'Edit Pull Sheet Settings') {
        if (!this.project || !(key in PULL_SHEET_DEFAULTS)) return false;
        const defaults = this.getPullSheetDefaults();
        const v = String(value == null ? '' : value).trim() || defaults[key];
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
        return this._postPullSheetState(['pullSheet']);
    }

    // THE one queue for the pull sheet's project POSTs - its settings, its
    // edits and the show's cable unit (app-cable-units.js), which relabels
    // the edits. One POST in flight, at most one waiting; a call while one
    // is in flight adds its keys to the waiting one, and every body is read
    // off the project when it is SENT, so the latest state always lands
    // last (two queues let a slow stale POST land after a newer one).
    // Resolves once a POST carrying `keys` has landed.
    _postPullSheetState(keys) {
        const q = this._pullSheetPost || (this._pullSheetPost = { busy: false, keys: new Set(), waiters: [] });
        keys.forEach(k => q.keys.add(k));
        const landed = new Promise(resolve => q.waiters.push(resolve));
        if (!q.busy) this._sendPullSheetState();
        return landed;
    }

    _sendPullSheetState() {
        const q = this._pullSheetPost;
        if (!q.keys.size) {
            q.busy = false;
            const idle = q.idle || [];
            q.idle = [];
            idle.forEach(r => r());
            return;
        }
        const p = this.project || {};
        const value = {
            cableUnit: () => this.cableUnit(),
            // A deleted store must reach the server as an empty object:
            // POST merges top-level keys and would otherwise keep the old
            // edits.
            pullSheetEdits: () => p.pullSheetEdits || { positions: {} },
            pullSheet: () => p.pullSheet || {},
            // the show's cable stock (app-cable-stock.js); null clears it
            cableStock: () => (p.cableStock === undefined ? null : p.cableStock),
        };
        const body = {};
        q.keys.forEach(k => { if (value[k]) body[k] = value[k](); });
        const waiters = q.waiters;
        q.keys = new Set();
        q.waiters = [];
        q.busy = true;
        fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).catch(() => {}).then(() => {
            waiters.forEach(w => w());
            this._sendPullSheetState();
        });
    }

    // null when the queue above is idle, else a promise that resolves once
    // it is: nothing in flight, nothing waiting. What a whole-project
    // write (undo / redo's restore PUT, New, a file open) waits on, so a
    // POST of the old project's unit or edits cannot land after it and
    // put them back (app-history.js _syncRestoredProject).
    _pullSheetStateSettled() {
        const q = this._pullSheetPost;
        if (!q || (!q.busy && !q.keys.size)) return null;
        return new Promise(resolve => (q.idle || (q.idle = [])).push(resolve));
    }

    // ---- vocabulary --------------------------------------------------------

    // A length in the show's unit as the sheet prints it - "100'" in a
    // feet show, "30 m" in a meters one (app-cable-units.js) - "EA" for
    // each-items, "" for a length nobody typed. A cable of a `kind` the
    // show's stock covers ('multi' / 'data' / 'circuit') is written as its
    // pieces, "100'+25'" (cableStockText).
    pullLengthText(ft, kind = null) {
        if (ft === 'EA') return 'EA';
        if (this._pullLengthProbe) {
            const n = this.parseCableLength(ft);
            const pieces = kind ? this.cableStockPieces(ft, kind) : null;
            if (pieces) this._pullLengthProbe.push(...pieces);
            else if (n !== null) this._pullLengthProbe.push(n);
        }
        return kind ? this.cableStockText(ft, kind) : this.cableLengthText(ft);
    }

    // A row's length cell for a covered cable: { text, pieces } - the text
    // as pullLengthText writes it, and the pieces' own texts when the
    // stock makes it of more than one length or more than one cable, so
    // the sheet counts each (_pullExpandPieces). A row built from it
    // carries the pieces until it is merged.
    pullCableLength(ft, kind) {
        const text = this.pullLengthText(ft, kind);
        const pieces = this.cableStockPieces(ft, kind);
        return { text, pieces: pieces && pieces.length > 1
            ? pieces.map(p => this.cableLengthText(p)) : null };
    }

    // Which stock a box's home run is pulled from (2026-10-21, a list per
    // cable kind): a DIRECT output's one cable 'direct', an L21-30 box's
    // 'l2130', a Harting box's 'harting', every other box's a multi's.
    // Reads the pull list's box ({ kind, typeId, connectorId }), a face box
    // ({ kind, conn }) or a box type ({ id }).
    pullHomeRunKind(box) {
        if (!box) return 'multi';
        if (box.kind === 'direct') return 'direct';
        const conn = box.connectorId || (box.conn && box.conn.id) || '';
        const type = String(box.typeId || box.id || '');
        if (conn === 'l2130' || type.startsWith('l2130')) return 'l2130';
        if (conn === 'harting') return 'harting';
        return 'multi';
    }

    // The same for a multi's soca-plan record (getSocaPlan): the face box
    // its distro and number name, else the type its box is.
    socaHomeRunKind(s) {
        const d = s && s.distroId && typeof this.getDistros === 'function'
            ? this.getDistros().find(x => x.id === s.distroId) : null;
        const fbox = d && typeof this.faceBox === 'function' ? this.faceBox(d, s.number) : null;
        if (fbox || !d || typeof this.distroBoxType !== 'function') return this.pullHomeRunKind(fbox);
        const typed = this.distroBoxType(d, s.number).type;
        return this.pullHomeRunKind(typed ? { typeId: typed.id } : null);
    }

    // Rows whose length is several stock pieces (pullCableLength), one row
    // per piece length: "Multi | 100'+25' | 1" pulls as "Multi | 100' | 1"
    // and "Multi | 25' | 1", each with the row's label and notes, so the
    // sheet and its totals count the cables a crew pulls. A row that
    // carries `_join` (its coupler's type and how many per join) adds the
    // couplers its joins take: "Cat6 | 100'+25'" is 100' + 25' + one "Cat6
    // Barrel" EA, "powerCON | 100'+25'" one "powerCON Coupler" EA
    // (_pullPowerJoin). A power multi and a TRUE1 cable join without one.
    // Every other row passes through as it is.
    _pullExpandPieces(rows) {
        const out = [];
        for (const r of rows) {
            if (!r || !Array.isArray(r._pieces) || !r._pieces.length) { out.push(r); continue; }
            const counts = new Map();
            for (const p of r._pieces) counts.set(p, (counts.get(p) || 0) + 1);
            for (const [length, n] of counts) {
                const piece = { ...r, length, qty: (Number(r.qty) || 0) * n };
                delete piece._pieces;
                delete piece._join;
                out.push(piece);
            }
            const joins = r._pieces.length - 1;
            if (r._join && joins > 0) {
                const barrel = { ...r, type: r._join.type, length: 'EA', notes: '',
                                 qty: (Number(r.qty) || 0) * joins * (Number(r._join.per) || 1) };
                delete barrel._pieces;
                delete barrel._join;
                // a coupler is a coupler, whichever snake it joins
                delete barrel.apart;
                out.push(barrel);
            }
        }
        return out;
    }

    // A powerCON cable made of several stock pieces (a circuit's cable, a
    // direct output's, any cable whose panel end is powerCON) is joined
    // where the pieces meet by one "powerCON Coupler" EA per join, under
    // the cable's label (owner, 2026-10-21). TRUE1 needs none - a female
    // mates with a male - and neither does a multi or any other power
    // cable. _pullExpandPieces counts them.
    _pullPowerJoin(r) {
        if (r && Array.isArray(r._pieces) && r._pieces.length > 1
                && /(^|→\s*)powerCON$/.test(String(r.type || '').trim())) {
            r._join = { type: 'powerCON Coupler', per: 1 };
        }
        return r;
    }

    // One socket as the pull sheet labels a snake and its extensions
    // (owner, 2026-10-21): the port label its own device gives it ("VX
    // A-1" off a box named VX A), else `fallback` (the label of the screen
    // port riding it), else that screen port's label read off the
    // assignment, else the device's name and the socket's number.
    _pullSocketLabel(owner, socket, fallback = '') {
        if (!owner) return fallback || '';
        const n = parseInt(socket, 10);
        const port = ((owner.rec || {}).ports || []).find(p => p.number === n);
        if (port && port.label) return String(port.label);
        if (fallback) return fallback;
        const occ = owner.cardId && typeof this._portOccupants === 'function'
            ? this._portOccupants(owner.cardId, n) : [];
        for (const o of occ) {
            const layer = ((this.project && this.project.layers) || [])
                .find(l => String(l.id) === String(o.layerId));
            if (!layer || typeof this.getPortLabelText !== 'function') continue;
            const text = this.getPortLabelText(layer, o.number, o.role === 'return' ? 'return' : 'primary');
            if (text) return String(text);
        }
        const own = typeof this.dataSocketLabel === 'function' ? this.dataSocketLabel(owner, n) : String(n);
        if (!/^\d+$/.test(own)) return own;
        const title = typeof this.dataOwnerTitle === 'function' ? this.dataOwnerTitle(owner) : '';
        return title ? `${title} ${own}` : own;
    }

    // Every port on a snake, labelled as _pullSocketLabel says, in member
    // order: what the snake's row is labelled with.
    _pullSnakePortLabels(snake) {
        const out = [];
        for (const m of ((snake && snake.members) || [])) {
            const owner = typeof this._dataCableOwner === 'function' ? this._dataCableOwner(m.kind, m.id) : null;
            const label = owner ? this._pullSocketLabel(owner, m.socket) : String(m.socket);
            if (label && !out.includes(label)) out.push(label);
        }
        return out;
    }

    // Every number the engine prints as a length, as the number itself
    // (7.62, never "7.6'"): what a unit change relabels the edits' keys by
    // (app-cable-units.js), so an edit stays on its row whatever the print
    // rounds to.
    pullSheetLengthNumbers() {
        const seen = [];
        this._pullLengthProbe = seen;
        try { this.buildPullList(); } finally { this._pullLengthProbe = null; }
        return seen;
    }

    // Every distro box's label on paper (owner, 2026-10-21: "should be
    // only listing the distros by name, if there happen to be 2 of the
    // exact same name, then you can use a -1 etc"): the box's OWN name -
    // the multi's name as the tray shows it ("SR1", "DISTRO 1-1", a typed
    // "MAIN") - never the distro's name and the number glued on. Two
    // DISTROS of one name are told apart on the distro itself (owner,
    // 2026-10-22: "Suffix the distro: SR-1 and SR-2", distroLabel), so
    // their derived boxes already differ (SR-1-1, SR-2-1) and no box ever
    // reads like a circuit (SR1-2). Only where two boxes still carry
    // exactly the same name - two typed "MAIN" - does each take "-1",
    // "-2" (distro tray order, then box number). A box on hidden screens
    // only is not counted. The pull sheet, the distros' pull lists, the
    // binder's distro tables and the map's brackets all read this one
    // map: `${distroId}|${number}` -> label.
    distroBoxLabels() {
        const distros = typeof this.getDistros === 'function' ? this.getDistros() : [];
        const order = new Map(distros.map((d, i) => [d.id, i]));
        const found = new Map();      // key -> { d, number, name, shown }
        const hidden = (l) => (typeof this._screenHidden === 'function'
            ? this._screenHidden(l) : l.visible === false);
        for (const l of ((this.project && this.project.layers) || [])) {
            if (!l || (l.type || 'screen') !== 'screen' || typeof this._powerNaming !== 'function') continue;
            const shown = !hidden(l);
            for (const rec of this._powerNaming(l).socas.values()) {
                if (!rec || !rec.distroId || !order.has(rec.distroId)) continue;
                const key = `${rec.distroId}|${rec.number}`;
                if (found.has(key)) {
                    if (shown) found.get(key).shown = true;
                    continue;
                }
                const d = distros[order.get(rec.distroId)];
                const base = typeof this.distroLabel === 'function'
                    ? this.distroLabel(d) : String(d.name || '').trim();
                const name = String(rec.name || '').trim()
                    || (typeof this._deriveMultiName === 'function'
                        ? this._deriveMultiName(base, rec.number, null)
                        : `${base}${rec.number}`);
                found.set(key, { d: rec.distroId, number: Number(rec.number), name, shown });
            }
        }
        const keys = [...found.keys()].sort((a, b) => {
            const x = found.get(a), y = found.get(b);
            return (order.get(x.d) - order.get(y.d)) || (x.number - y.number);
        });
        const count = new Map();
        for (const k of keys) {
            const f = found.get(k);
            if (f.shown) count.set(f.name, (count.get(f.name) || 0) + 1);
        }
        const seen = new Map();
        const out = new Map();
        for (const k of keys) {
            const { name, shown } = found.get(k);
            if (!shown || (count.get(name) || 0) < 2) { out.set(k, name); continue; }
            const i = (seen.get(name) || 0) + 1;
            seen.set(name, i);
            out.set(k, `${name}-${i}`);
        }
        return out;
    }

    // What paper calls a breakout box (a CVT, an XD): its model and
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

    // The distro on its own gear row, by its TYPE (2026-10-18): what the
    // user typed behind its gear, or a preset's name, else "Distro".
    pullDistroType(d) {
        const t = String((d && d.typeName) || '').trim();
        return t || 'Distro';
    }

    // ---- panels ------------------------------------------------------------

    // A cabinet's size as a panel row says it: always millimetres, "500 ×
    // 500 mm", in a feet show too (owner, 2026-10-22) - "128 × 128 px"
    // where the screen has no size in mm.
    _pullPanelSizeText(wmm, hmm, wpx, hpx) {
        if (!(wmm > 0) || !(hmm > 0)) return `${wpx} × ${hpx} px`;
        const tidy = (n) => String(Math.round(n * 10) / 10);
        return `${tidy(wmm)} × ${tidy(hmm)} mm`;
    }

    // One screen's panel types: { none, height, width } - the names of a
    // full cabinet and of a half tile halved along each axis (halfTile
    // 'height' halves the height, 'width' the width). The panel SAVED on
    // the screen first (panelModelName, its halves' names saved with it -
    // app-presets.js catalogPanelModelFields; a name typed in Screen Info
    // has no halves of its own), so the rows never wait on the library;
    // a show saved before is named by the library where it knows the
    // cabinet (catalogPanelNames); a half with no match is "<name> half".
    // A cabinet nothing names is its
    // size, "500 × 500 mm panel", its half "500 × 250 mm half panel". A
    // SQUARE cabinet (in mm and in pixels) halved either way is the same
    // cabinet turned, so both halves carry one name; on any other the two
    // halves are different cabinets and a name with no library match says
    // its size: "<name> half (250 × 1000 mm)".
    pullPanelTypes(layer) {
        const num = (v) => Number(v) || 0;
        const wmm = num(layer && layer.panel_width_mm), hmm = num(layer && layer.panel_height_mm);
        const wpx = num(layer && layer.cabinet_width), hpx = num(layer && layer.cabinet_height);
        const square = wmm === hmm && wpx === hpx;
        const size = (w, h, pw, ph) => this._pullPanelSizeText(w, h, pw, ph);
        const halfH = size(wmm, hmm / 2, wpx, Math.round(hpx / 2));
        const halfW = size(wmm / 2, hmm, Math.round(wpx / 2), hpx);
        const savedName = String((layer && layer.panelModelName) || '').trim();
        let lib = null;
        if (savedName) {
            // a library model under its own name keeps the halves saved
            // with it; renamed, or named by hand, its halves are "<name> half"
            const own = layer.panelModelId && typeof this.catalogModelIdLabel === 'function'
                && this.catalogModelIdLabel(layer.panelModelId) === savedName;
            const halves = own && layer.panelModelHalves && typeof layer.panelModelHalves === 'object'
                ? layer.panelModelHalves : {};
            lib = { full: savedName, height: halves.height || null, width: halves.width || null };
        } else if (typeof this.catalogPanelNames === 'function') {
            lib = this.catalogPanelNames(layer);
        }
        if (lib && lib.full) {
            if (square) {
                const one = lib.height || lib.width || `${lib.full} half`;
                return { none: lib.full, height: one, width: one };
            }
            return { none: lib.full,
                     height: lib.height || `${lib.full} half (${halfH})`,
                     width: lib.width || `${lib.full} half (${halfW})` };
        }
        const full = `${size(wmm, hmm, wpx, hpx)} panel`;
        if (square) return { none: full, height: `${halfH} half panel`, width: `${halfH} half panel` };
        return { none: full, height: `${halfH} half panel`, width: `${halfW} half panel` };
    }

    // One screen's panel counts by type: [{ type, qty }] in first-seen
    // order (full, then the halves) - every cabinet that hangs, blank and
    // hidden ones left out.
    pullPanelCounts(layer) {
        const types = this.pullPanelTypes(layer);
        const counts = new Map();
        for (const p of (layer && layer.panels) || []) {
            if (!p || p.blank || p.hidden) continue;
            const half = p.halfTile === 'height' || p.halfTile === 'width' ? p.halfTile : 'none';
            const type = types[half];
            counts.set(type, (counts.get(type) || 0) + 1);
        }
        return [...counts].map(([type, qty]) => ({ type, qty }));
    }

    // Every panel type name the show's screens can print, lower-cased:
    // what pullGuessSide reads as a panel.
    _pullPanelTypeNames() {
        const out = new Set();
        for (const l of ((this.project && this.project.layers) || [])) {
            if (!l || (l.type || 'screen') !== 'screen') continue;
            const t = this.pullPanelTypes(l);
            for (const k of ['none', 'height', 'width']) out.add(String(t[k]).toLowerCase());
        }
        return out;
    }

    // The panel library loaded where a panel row still needs it to be
    // named: a screen with no panel saved on it (a show saved before
    // 2026-10-22) is named by matching its figures against the library.
    // What an export and the editor wait on before they read the list; a
    // show whose every screen saved its panel waits on nothing.
    async pullPanelCatalogReady() {
        if (this._panelCatalog || typeof this._ensurePanelCatalogData !== 'function') return;
        const unsaved = this._pullScreens().some(l => !String(l.panelModelName || '').trim());
        if (!unsaved) return;
        try { await this._ensurePanelCatalogData(); } catch (_) {}
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
        const ft = this.parseCableLength(box && box.fiberFt);
        if (!Number.isFinite(ft) || ft <= 0) return '';
        return `${(box.fiberType || '').trim() || 'Fiber'} ${this.pullLengthText(ft)}`;
    }

    // A copper link on a box (an XD's X1 on Cat6A) as a pull row's cells:
    // the kind, its length, one, "XD A (X1)" - the port in brackets
    // so the name folding never reads it as a run - and the plain warning
    // where it runs past its 10G length ("no length" where none is typed).
    // Rows merge by kind and length like every other cable.
    _pullCopperCells(l) {
        const ft = this.parseCableLength(l.copper.ft);
        const has = ft !== null;
        return [l.copper.copper, has ? this.pullLengthText(ft) : '', 1,
                `${this.pullBoxTitle(l.box)} (${l.title})`,
                this.copperOverText(l.copper) || (has ? '' : 'no length')];
    }

    // A fiber link's EXTENSION at the box end (owner, 2026-11-02) as a
    // pull row's cells: its kind and two ends, "Fan-out · MTP / MPO to LC
    // duplex", its length, one, "XD A (X1)" as a copper link reads, and
    // the trunk it extends in Notes ("ext · MTP A", "no length" where none
    // is typed). Rows merge by type and length, so identical extensions -
    // kind, both ends, length - are one row with a count.
    _pullFiberExtensionCells(l) {
        const ext = this.fiberLinkExtension(l);
        const ft = this.parseCableLength(ext.ft);
        const has = Number.isFinite(ft) && ft > 0;
        return [this.fiberExtensionType(ext, l.cable), has ? this.pullLengthText(ft) : '', 1,
                `${this.pullBoxTitle(l.box)} (${l.title})`,
                `ext · ${l.cable.name || this.fiberCableTypeText(l.cable)}` + (has ? '' : ' · no length')];
    }

    pullPowerConnectorName(appName) {
        const name = String(appName || '').trim();
        return POWER_CONNECTOR_SHEET_NAMES[name] || name;
    }

    // The sheet's word for a data connector id - the one name table
    // (dataCableWord): "etherCON" or "Cat6", Cat6 where the catalog is
    // silent. Copper only: a port's or a snake's plug is never fiber -
    // fiber is a breakout box's trunk row (pullBoxFiberText), processor to
    // box.
    pullDataConnectorWord(connectorId) {
        return typeof this.dataCableWord === 'function' ? this.dataCableWord(connectorId) : 'Cat6';
    }

    // Natural compare for the sort: numbers inside a name read as numbers
    // (3G SDI before 12G SDI, TRUE1 2fer before TRUE1 3fer), case-blind.
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
    // union in first-seen order. Output is sorted. With `keepSplit` a row
    // carrying `split` (a group member's jumpers, one row per member on the
    // group's pull sheet) merges only with rows of the same split, and keeps
    // it; without, every row of a type and length folds into one - the
    // totals, and a screen's own reading. A row carrying `apart` (a snake's,
    // `snake:<id>`) merges only with its own copies everywhere, totals
    // included: two snakes are never one row, whatever their channels
    // (owner, 2026-10-21).
    _pullMergeRows(rows, keepSplit = false) {
        const byKey = new Map();
        for (const r of this._pullExpandPieces(rows)) {
            if (!r || !r.type) continue;
            const split = keepSplit && r.split ? r.split : '';
            const apart = r.apart || '';
            const key = `${r.type}\u0000${r.length}\u0000${split}\u0000${apart}`;
            let hit = byKey.get(key);
            if (!hit) {
                hit = { type: r.type, length: r.length, qty: 0, _labels: [], _notes: [] };
                if (split) hit.split = split;
                if (apart) hit.apart = apart;
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
                ...(r.split ? { split: r.split } : {}),
                ...(r.apart ? { apart: r.apart } : {}),
                _labels: r._labels, _notes: r._notes,
            })));
    }

    // Short names covered. Only a true RUN of numbered siblings folds - two
    // or more names sharing a prefix whose numbers follow on ("SR1", "SR2",
    // "SR3", "SR4" -> "SR 1-4"). A lone name is listed exactly as typed
    // ("SR 13x5", "Floor H2", "CVT10" never lose their last number), and
    // a number glued to a token that already holds digits ("13x5",
    // "19x11") is never cut off it. A dashed name - a multi under a
    // digit-ending distro ("DISTRO 1-1") or a circuit label ("SR1-1") -
    // folds only a run of three or more, its first name whole and its last
    // from the number before the dash: "DISTRO 1-1 … 1-7". A socket's
    // port label - a letter before the dash, "VX A-1" off a box named VX A
    // (2026-10-21, a snake's and its extensions' labels) - folds the same
    // way: "VX A-1 … A-4". A list still
    // longer than eight pieces after folding (a wall's worth of circuit
    // labels) is said as its ends and a count.
    _pullCompressNames(names) {
        const list = (names || []).filter(Boolean).map(String);
        if (!list.length) return '';
        const runsOf = (nums) => {
            const runs = [];
            for (const n of [...new Set(nums)].sort((a, b) => a - b)) {
                const last = runs[runs.length - 1];
                if (last && n === last[1] + 1) last[1] = n;
                else runs.push([n, n]);
            }
            return runs;
        };
        // key -> { names, nums, text(runs) }, in first-seen order
        const groups = new Map();
        const plain = [];
        const add = (key, name, num, text) => {
            const g = groups.get(key) || { names: [], nums: [], text };
            if (!g.names.includes(name)) { g.names.push(name); g.nums.push(num); }
            groups.set(key, g);
        };
        for (const n of list) {
            const dashed = n.match(/^(.*?)(\d+)([-–])(\d+)$/);
            if (dashed) {
                const [, head, mid, sep, tail] = dashed;
                add(`d\u0000${head}${mid}${sep}`, n, parseInt(tail, 10),
                    ([a, b]) => `${head}${mid}${sep}${a} … ${mid}${sep}${b}`);
                continue;
            }
            const lettered = n.match(/^(.*?)([A-Za-z]+)([-–])(\d+)$/);
            if (lettered) {
                const [, head, mid, sep, tail] = lettered;
                add(`d\u0000${head}${mid}${sep}`, n, parseInt(tail, 10),
                    ([a, b]) => `${head}${mid}${sep}${a} … ${mid}${sep}${b}`);
                continue;
            }
            const m = n.match(/^(.*?)(\d+)$/);
            // the token the number ends: letters then the number ("SR1",
            // "H2") or the number alone; "13x5" holds digits before it. A
            // port label like SR-1 keeps its own text, as it always has.
            const token = m ? (m[1].match(/\S*$/) || [''])[0] : '';
            if (!m || /\d/.test(token) || /[-–]$/.test(m[1])) { plain.push(n); continue; }
            // the prefix exactly as typed: "Screen1" and "Screen 2" are two
            // names, not a run (QA 1.6.0 read them "Screen 1-2")
            add(`p\u0000${m[1]}`, n, parseInt(m[2], 10), null);
        }
        const out = [];
        for (const [key, g] of groups) {
            const runs = runsOf(g.nums);
            if (key.startsWith('d')) {
                // a dashed run of three or more folds; the rest as typed
                for (const [a, b] of runs) {
                    if (b - a >= 2) { out.push(g.text([a, b])); continue; }
                    for (let k = a; k <= b; k++) out.push(g.names[g.nums.indexOf(k)]);
                }
                continue;
            }
            // no two names here follow on: each is a name, not a run
            if (!runs.some(([a, b]) => b > a)) { out.push(...g.names); continue; }
            const prefix = key.slice(2).trim();
            const text = runs.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(', ');
            out.push(prefix ? `${prefix} ${text}` : text);
        }
        const pieces = [...out, ...plain];
        if (pieces.length > 8) return `${list[0]} … ${list[list.length - 1]} (${list.length})`;
        return pieces.join(', ');
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
        const groupOf = (layer) => (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        const beachOf = this._pullBeachResolver();
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

    // The beach a screen is pulled to (null: none) - what pullPositions,
    // the Beaches line's counts and the Screen Info picker all read.
    screenBeachId(layer) {
        return layer ? this._pullBeachResolver()(layer) : null;
    }

    // The beach of a screen, as a function over one reading of the beaches.
    // A screen's own pick first, else its group's name when a beach is
    // called that (the "groups are beaches" files). A screen GROUP is ONE
    // position (owner, 2026-10-01: "the group screens should be in the same
    // section so i would think together"): every member is on the beach of
    // its FIRST member in group order that is on one - by its own pick or
    // by the group's name - and a group with no member on a beach is a
    // position of its own. Members once picked onto different beaches all
    // print on that first one; none is dropped and none printed twice.
    _pullBeachResolver() {
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
        const own = (layer, group) => {
            if (layer.beachId && beachIds.has(layer.beachId)) return layer.beachId;
            if (group) {
                const norm = String(group.name == null ? '' : group.name).trim().toLowerCase();
                if (norm && beachByNorm.has(norm)) return beachByNorm.get(norm);
            }
            return null;
        };
        const byGroup = new Map();
        return (layer) => {
            const group = groupOf(layer);
            if (!group) return own(layer, null);
            if (!byGroup.has(group.id)) {
                const members = (typeof this.getGroupMembers === 'function' ? this.getGroupMembers(group) : [])
                    .filter(m => m && (m.type || 'screen') === 'screen' && m.visible !== false);
                let at = null;
                for (const m of members.length ? members : [layer]) {
                    at = own(m, group);
                    if (at) break;
                }
                byGroup.set(group.id, at);
            }
            return byGroup.get(group.id);
        };
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
                    const resolved = this.getResolvedPathPanels(layer, layer.customPortPaths[n] || [], 'data');
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
    //     byScreen: { [layerId]: { name, rows, boxes, gangs: {twofer, threefer,
    //                 wider?: {ways: count} for 4fers and up},
    //                              ports, snakes, jumpers: {data, power},
    //                              jumperLengths: {data: {ft: n}, power: {ft: n}} } },
    //     hardware: [{ kind: 'distro'|'processor', id, name, rows }],
    //     settings, unmodelled: [strings] }
    // where a row is { type, length, qty, label, notes, side } and side is
    // 'power', 'data' or 'panel' (a screen's panels, EA). A
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
        // The DIRECT outputs among them (1.5): one circuit, one cable - not
        // a hole a multi plugs into, so the distro's "N way" never counts them.
        const directSeen = new Set();
        // Each breakout a box takes: one per connector its screens break
        // out to ("<box key>|<breakout type>").
        const breakoutsSeen = new Set();
        const snakesSeen = new Set();
        // A row said once for several runs (a snake, a box's fiber) is
        // tagged with every screen those runs land on, whichever screen's
        // walk said it (_pullScreenList's `on`).
        const saidOnce = new Map();
        const fiberSeen = new Set();      // a box's fiber trunk, said once
        // Where a device's gear row falls back to when the device has no
        // location: the first screen a distro feeds, the first screen
        // whose port a box delivers.
        const distroFirstLayer = new Map();   // String(distroId) -> layerId
        const boxFirstLayer = new Map();      // boxId -> layerId
        const procFirstLayer = new Map();     // processorId -> layerId
        // The tail cache is a per-tick memo keyed by layer object; a build
        // that follows an edit in the same tick must not read stale names.
        this._circuitTailCache = null;
        const boxLabels = this.distroBoxLabels();
        // Multi boxes holding more circuits than their fan (round 7), read
        // once for the whole list (_boxOverflows, the tray's own reading).
        const boxOverflows = typeof this._boxOverflowMap === 'function'
            ? this._boxOverflowMap() : new Map();

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
        // Where each row was pulled, for the edits (applyPullSheetEdits):
        // `_rid` ties a row to the copies on the hardware sheets, `_pos` and
        // `_layer` say which position took it and which screen's walk made
        // it (none for a gear row).
        let nextRid = 0;
        const rid = () => ++nextRid;
        const posOfRid = new Map();
        const land = (key, r, layerId) => {
            const pos = byKey.get(key);
            if (!pos) return;
            if (!r._rid) r._rid = rid();
            r._pos = key;
            r._layer = layerId == null ? null : layerId;
            posOfRid.set(r._rid, key);
            pos.rows.push(r);
            if (layerId != null && !pos.layerIds.includes(layerId)) pos.layerIds.push(layerId);
        };

        for (const base of bases) {
            for (const layer of base.layers) {
                const scr = this._pullScreenList(layer, {
                    settings, distroById, boxesSeen, directSeen, breakoutsSeen, snakesSeen, fiberSeen, hw, saidOnce,
                    distroFirstLayer, boxFirstLayer, procFirstLayer, rid, boxLabels, boxOverflows,
                });
                byScreen[layer.id] = scr;
                // Every row goes where the device that produced it sits;
                // a row no device located stays with the screen.
                for (const r of scr.rows) {
                    land((r._at && locationKey(r._at)) || base.key, r, layer.id);
                }
                // PANELS, EA: one row per type the screen hangs, under its
                // own position and its name (pullPanelCounts). No screen's
                // walk made them, so they are on no CABLES THIS SCREEN
                // table and no hardware pull list.
                for (const { type, qty } of this.pullPanelCounts(layer)) {
                    land(base.key, { type, length: 'EA', qty, label: layer.name || '',
                                     notes: '', side: 'panel' }, null);
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
        // EVERY PROCESSOR, EA (owner, 2026-09-25: "List mains and
        // backups"): one row per unit of its model, counted by model like
        // the boxes, its name in the label - and a processor's BACKUP UNIT
        // (an option on the main) one more of the same model under the
        // backup's name, marked "(backup)". Each lands where its main's
        // first counted box does, else the first screen its ports reach,
        // else the first position. A backup unit's own twin of every box
        // it does not feed on a backup input (a HELIOS's RS12 switches) is
        // counted where, and only where, the main's box it mirrors is.
        for (const proc of this._processorsResolved || []) {
            const type = String(proc.deviceName || '').trim();
            if (!type) continue;
            const procName = proc.name || proc.deviceName || proc.id;
            const boxes = this._pullAllBoxes().filter(b => b.proc === proc).map(b => b.box);
            const unitRow = (label) => {
                const r = { type, length: 'EA', qty: 1, label, notes: '', side: 'data' };
                if (!boxes.some(b => gearAt(r, this.pullLocationOf(b), boxFirstLayer.get(b.id)))
                        && !gearAt(r, null, procFirstLayer.get(proc.id))) {
                    if (!bases.length) return;
                    land(bases[0].key, r, null);
                }
                hw('processor', proc.id, procName).rows.push({ ...r });
            };
            // Its NAME is the label; an unnamed unit's model is already the
            // row's type, so it adds none (a bare "H9" would fold as a run).
            unitRow(String(proc.name || '').trim());
            // A CARD THAT IS A UNIT OF ITS OWN - a QD-S, 1U on an SQ200's
            // OUT port (catalog separateUnit) - is gear on the truck, one
            // row each under its title ("QD 1"), where its first located
            // box is, else where its processor's is. A backup SQ200 feeds
            // the same QD-S on IN 2, so it brings none of its own.
            for (const slot of proc.slots || []) {
                const c = slot && slot.card;
                const cType = String((c && c.deviceName) || '').trim();
                if (!c || !c.separateUnit || !cType) continue;
                const r = { type: cType, length: 'EA', qty: 1,
                            label: String(c.name || c.unitTitle || '').trim(),
                            notes: '', side: 'data' };
                if (!(c.cvts || []).some(b => gearAt(r, this.pullLocationOf(b), boxFirstLayer.get(b.id)))
                        && !gearAt(r, null, procFirstLayer.get(proc.id))) {
                    if (!bases.length) continue;
                    land(bases[0].key, r, null);
                }
                hw('processor', proc.id, procName).rows.push({ ...r });
            }
            const unit = proc.backupUnit;
            if (!unit) continue;
            unitRow(`${unit.name} (backup)`);
            for (const twin of unit.boxes || []) {
                const of = boxes.find(b => b.id === twin.mirrorOf);
                // "HX BU A" - the backup's name and the mirrored box's own
                // label, where that says more than the model the row is.
                const own = of ? String(this.pullBoxLabel(of) || '').trim() : '';
                const t = { type: String(twin.deviceName || '').trim(), length: 'EA', qty: 1,
                            label: own && own !== String(twin.deviceName || '').trim()
                                ? `${unit.name} ${own}` : unit.name,
                            notes: '', side: 'data' };
                if (!t.type || !of) continue;
                if (!gearAt(t, this.pullLocationOf(of), boxFirstLayer.get(of.id))) continue;
                hw('processor', proc.id, procName).rows.push({ ...t });
            }
        }
        // FIBER CABLES NO SCREEN PORT REACHED: a cable is on the list once
        // however it is used, so a TAC that only a backup link takes, or one
        // feeding a box no screen's port comes out of yet, is still pulled -
        // under its first box's location (tray order), else the screen that
        // box first feeds, else the first position. The walk above said the
        // rest, where their ports reached them.
        if (typeof this.fiberBoxLinks === 'function') {
            // Every link host - a QD-S's IN 1 / IN 2 as well as each box.
            const hosts = typeof this._fiberAllBoxes === 'function'
                ? this._fiberAllBoxes() : this._pullAllBoxes();
            for (const { box, proc, card } of hosts) {
                // A card cabled on links of its own (a QD-S, `box` the
                // card itself) has no location and no first screen: its
                // fiber goes where its boxes are, as its gear row does,
                // else where its processor's ports first land.
                const place = (r) => {
                    const placed = box === card
                        ? ((card.cvts || []).some(b => gearAt(r, this.pullLocationOf(b), boxFirstLayer.get(b.id)))
                           || gearAt(r, null, procFirstLayer.get(proc.id)))
                        : gearAt(r, this.pullLocationOf(box), boxFirstLayer.get(box.id));
                    if (!placed) {
                        if (!bases.length) return;
                        land(bases[0].key, r, null);
                    }
                    hw('processor', proc.id, proc.name || proc.deviceName || proc.id).rows.push({ ...r });
                };
                for (const l of this.fiberBoxLinks(box)) {
                    // the link's own extension at the box end, once per link
                    const extKey = `ext:${l.box.id}:${l.key}`;
                    if (!l.copper && this.fiberLinkExtension(l) && !fiberSeen.has(extKey)) {
                        fiberSeen.add(extKey);
                        const [type, length, qty, label, notes] = this._pullFiberExtensionCells(l);
                        place({ type, length, qty, label, notes, side: 'data' });
                    }
                    const key = l.copper ? `cu:${l.box.id}:${l.key}` : (l.cable ? `fib:${l.cable.id}` : null);
                    if (!key || fiberSeen.has(key)) continue;
                    fiberSeen.add(key);
                    let r;
                    if (l.copper) {
                        const [type, length, qty, label, notes] = this._pullCopperCells(l);
                        r = { type, length, qty, label, notes, side: 'data' };
                    } else {
                        const ft = this.parseCableLength(l.cable.ft);
                        const has = Number.isFinite(ft) && ft > 0;
                        r = { type: this.fiberCableTypeText(l.cable), length: this.pullLengthText(ft),
                              qty: 1, label: l.cable.name || '', notes: has ? '' : 'no length', side: 'data' };
                    }
                    place(r);
                }
            }
        }
        const boxesOn = new Map();            // String(distroId) -> boxes in use
        const directOn = new Map();           // String(distroId) -> direct outputs in use
        for (const key of boxesSeen) {
            const distroId = key.split('|')[0];
            const into = directSeen.has(key) ? directOn : boxesOn;
            into.set(distroId, (into.get(distroId) || 0) + 1);
        }
        // The distros another distro is fed thru (feeder.from), each with
        // the distros fed thru it - a pass-through distro is pulled even
        // with nothing plugged into it (owner, 2026-10-21).
        const fedThru = new Map();            // String(distroId) -> [distros fed thru it]
        for (const x of distros) {
            const from = x && x.feeder && typeof x.feeder === 'object' ? x.feeder.from : null;
            if (from == null || String(from) === String(x.id)) continue;
            if (!fedThru.has(String(from))) fedThru.set(String(from), []);
            fedThru.get(String(from)).push(x);
        }
        // Where a distro with no location and nothing of its own plugged
        // in falls back to: the first screen a distro fed thru it feeds
        // (down the chain), else the one the distro it is fed thru feeds
        // (up the chain), else the first position.
        const fallbackLayer = (d) => {
            const seen = new Set();
            const walk = [d];
            while (walk.length) {
                const cur = walk.shift();
                if (!cur || seen.has(String(cur.id))) continue;
                seen.add(String(cur.id));
                const at = distroFirstLayer.get(String(cur.id));
                if (at != null) return at;
                walk.push(...(fedThru.get(String(cur.id)) || []));
            }
            for (let cur = d, hops = 0; cur && hops < distros.length; hops++) {
                const from = cur.feeder && typeof cur.feeder === 'object' ? cur.feeder.from : null;
                cur = from != null ? distroById.get(from) : null;
                const at = cur ? distroFirstLayer.get(String(cur.id)) : null;
                if (at != null) return at;
            }
            const first = bases.find(b => (b.layers || []).length);
            return first ? first.layers[0].id : null;
        };
        for (const d of distros) {
            const n = boxesOn.get(String(d.id)) || 0;
            const k = directOn.get(String(d.id)) || 0;
            // Listed when something is plugged into it, when another distro
            // is fed thru it, or when its feeder is set; a distro with none
            // of those stays off.
            const passes = fedThru.has(String(d.id));
            const fed = !!(d.feeder && typeof d.feeder === 'object');
            if (!n && !k && !passes && !fed) continue;
            // Named by its Type; a distro feeding direct outputs only says
            // its outputs in Notes, as it always has.
            const r = { type: this.pullDistroType(d), length: 'EA', qty: 1,
                        label: this.distroLabel(d),
                        notes: n || !k ? '' : `${k} direct output${k === 1 ? '' : 's'}`,
                        side: 'power' };
            const at = n || k ? distroFirstLayer.get(String(d.id)) : fallbackLayer(d);
            if (!gearAt(r, this.pullLocationOf(d), at)) continue;
            hw('distro', d.id, this.distroLabel(d)).rows.push({ ...r });
            // Its FEEDER (2026-10-21, app-services.js): one row under the
            // distro's name, where the distro sits - "400 A cam set" with
            // its length, "no length" where none is typed.
            const feeder = typeof this.pullFeederRow === 'function' ? this.pullFeederRow(d) : null;
            if (feeder && gearAt(feeder, this.pullLocationOf(d), at)) {
                hw('distro', d.id, this.distroLabel(d)).rows.push({ ...feeder });
            }
        }

        // A device location is a position only while rows land on it.
        const listed = positions.filter(p => p.memberIds.length || p.rows.length);
        // Which screens' walks and which hardware sheets each position row
        // was built from, counted per piece: what an edit on that row does
        // to the screens' CABLES THIS SCREEN tables and the hardware pull
        // lists (applyPullSheetEdits). `${positionKey}\n${rowKey}` ->
        // { screens: Map(layerId -> qty), hw: Map(hwKey -> qty) }.
        const shares = new Map();
        const shareOf = (posKey, r) => {
            const k = `${posKey}\n${this.pullRowKey(r)}`;
            let s = shares.get(k);
            if (!s) { s = { screens: new Map(), hw: new Map() }; shares.set(k, s); }
            return s;
        };
        for (const p of listed) {
            for (const r of this._pullExpandPieces(p.rows)) {
                if (!r || !r.type || r._layer == null) continue;
                const s = shareOf(p.key, r);
                s.screens.set(r._layer, (s.screens.get(r._layer) || 0) + (Number(r.qty) || 0));
            }
        }
        for (const [hwKey, h] of hardwareRows) {
            for (const r of this._pullExpandPieces(h.rows)) {
                const posKey = r && r._rid ? posOfRid.get(r._rid) : null;
                if (!posKey || !r.type) continue;
                const s = shareOf(posKey, r);
                s.hw.set(hwKey, (s.hw.get(hwKey) || 0) + (Number(r.qty) || 0));
            }
        }
        listed.forEach(p => { p.rows = this._pullMergeRows(p.rows, true); });
        const totals = this._pullMergeRows(listed.flatMap(p => p.rows));
        const hardware = [...hardwareRows.values()].map(h => ({
            kind: h.kind, id: h.id, name: h.name, rows: this._pullMergeRows(h.rows),
        }));
        // `side` rides along for the binder, which lists a screen's power
        // cable apart from its data cable; the workbook ignores it. `_at`
        // (where the row was pulled) has done its work.
        const strip = r => ({ type: r.type, length: r.length, qty: r.qty,
                              label: r.label, notes: r.notes, side: r.side || 'power',
                              ...(r.split ? { split: r.split } : {}),
                              ...(r.apart ? { apart: r.apart } : {}) });
        listed.forEach(p => { p.rows = p.rows.map(strip); });
        hardware.forEach(h => { h.rows = h.rows.map(strip); });
        // `rowsOn`: the screen's rows unmerged, each with the screens its
        // cable lands on (`on`, layer ids) - what a grouped wall's member
        // sheet lists as its own (2026-10-01: "separate them. if the data
        // or power splits then mention it on both"). The merged `rows` and
        // every total are untouched: each cable is still counted once.
        // Each keeps, unlisted, the position that pulled it (`_pos`), so an
        // edit on that position's row finds it.
        Object.values(byScreen).forEach(s => {
            s.rowsOn = this._pullExpandPieces(s.rows).map(r => this._pullTagPosition(
                { ...strip(r), on: (r._on || []).slice() }, r._pos));
            s.rows = this._pullMergeRows(s.rows).map(strip);
        });
        const out = {
            positions: listed,
            totals: totals.map(strip),
            byScreen,
            hardware,
            settings,
            // Nothing the show can carry is left off the list now: a
            // breakout box's fiber trunk rides its own fiberType / fiberFt.
            unmodelled: [],
        };
        // Unlisted, so neither the workbook POST nor a copy carries it.
        Object.defineProperty(out, '_shares', { value: shares });
        return out;
    }

    // `_pos` on a row, unlisted (it never reaches a paper or the server).
    _pullTagPosition(row, posKey) {
        Object.defineProperty(row, '_pos', { value: posKey == null ? null : posKey,
                                             writable: true, configurable: true });
        return row;
    }

    // One screen's share: its raw rows (merged later by the caller) and the
    // per-screen readings the packet prints.
    _pullScreenList(layer, ctx) {
        const { settings, distroById, boxesSeen, snakesSeen, fiberSeen, hw } = ctx;
        const directSeen = ctx.directSeen || new Set();
        const breakoutsSeen = ctx.breakoutsSeen || new Set();
        const distroFirstLayer = ctx.distroFirstLayer || new Map();
        const boxFirstLayer = ctx.boxFirstLayer || new Map();
        const procFirstLayer = ctx.procFirstLayer || new Map();
        const rows = [];
        // Rows are power until the data walk below flips the switch: the
        // binder prints a screen's power cable and data cable apart.
        let side = 'power';
        // `on`: the screens (layer ids) the cable a row stands for lands on
        // - this screen unless a run crosses into a group peer. Set before
        // each run's rows; a jumper row names its own link's two ends.
        let on = [layer.id];
        const onOf = (panels, layers) => {
            const ids = [];
            (panels || []).forEach((pn, i) => {
                if (!pn || pn.hidden) return;
                const l = (layers && layers[i]) || layer;
                if (!ids.includes(l.id)) ids.push(l.id);
            });
            return ids.length ? ids : [layer.id];
        };
        const saidOnce = ctx.saidOnce || new Map();
        const tagOnce = (key) => {
            const r = saidOnce.get(key);
            if (r) for (const id of on) if (!r._on.includes(id)) r._on.push(id);
        };
        // `at` is the location of the device that produced the row (the
        // distro's, the box's) - buildPullList pulls the row there; null
        // leaves it with the screen.
        // `length` is the cell's text, or a covered cable's
        // { text, pieces } (pullCableLength): its pieces ride the row until
        // the merge counts them.
        const row = (type, length, qty, label, notes, at) => {
            const cell = length && typeof length === 'object' ? length : null;
            const r = { type, length: cell ? cell.text : length, qty, label: label || '',
                        notes: notes || '', side, _at: at || null, _on: on.slice() };
            if (cell && cell.pieces) r._pieces = cell.pieces.slice();
            // ties the row to its copies on the hardware sheets
            if (ctx.rid) r._rid = ctx.rid();
            rows.push(r);
            return r;
        };
        const locationOf = (d) => this.pullLocationOf(d);
        // A grouped screen's jumpers are said per member: each row under
        // the screen its jumpers sit on (a link joining two members' cabinets
        // counted once, on its first cabinet's), one row each on the group's
        // pull sheet (owner, 2026-10-01: "the jumpers should go on the beach
        // they are on"). An ungrouped screen's are its own, as before.
        const grouped = typeof this.groupMembersOf === 'function' && this.groupMembersOf(layer).length > 1;
        const out = {
            name: layer.name || '', rows, boxes: [], gangs: { twofer: 0, threefer: 0 },
            // jumpers: how many were counted per side; jumperLengths: the
            // same per length in feet ({ 1: 200, 6: 5 }).
            ports: [], snakes: [], jumpers: { data: 0, power: 0 },
            jumperLengths: { data: {}, power: {} },
        };
        // The jumpers of one run into `buckets` (location -> length -> count),
        // the per-screen tallies alongside - app-jumpers.js's rule, per link.
        // A bucket per screen pair a link joins, so each jumper row knows
        // where its jumpers are; merged, the rows read as they always did.
        // A power jumper is the panel input of the cabinet's OWN screen
        // (link.la) - in a grouped wall that is the member, not the carrier
        // - so each connector is a row of its own (2026-10-21).
        const countJumpers = (side, panels, layers, at, buckets) => {
            for (const link of this.jumperLinksOfRun(panels, layers, layer, side)) {
                if (link.ft == null) continue;
                out.jumpers[side]++;
                out.jumperLengths[side][link.ft] = (out.jumperLengths[side][link.ft] || 0) + 1;
                const ends = [...new Set([(link.la || layer).id, (link.lb || layer).id])];
                const conn = side === 'power' ? this.panelInput(link.la || layer).id : '';
                const key = `${at || ''}\u0000${link.ft}\u0000${ends.join(',')}\u0000${conn}`;
                const b = buckets.get(key) || { at, ft: link.ft, n: 0, on: ends, first: link.la || layer, conn };
                b.n++;
                buckets.set(key, b);
            }
        };

        // ---- power: boxes, breakouts, circuit cables, gangs, jumpers ----
        const breakout = this.getPowerBreakout(layer);
        const screenConn = this.pullPowerConnectorName(breakout.connector);
        // the connector the panels take (TRUE1 / powerCON): the splitters
        // and the tails are on the panels' side - a circuit's are its first
        // cabinet's own screen's (a group member's, not the carrier's)
        const inputOf = (c) => this.panelInput((c && c.layers && c.layers[0]) || layer);
        const plan = this.getSocaPlan(layer);
        const circuitOn = new Map(this.screenCircuits(layer).map(c => [c.num, onOf(c.panels, c.layers)]));
        const boxOn = new Map();    // box key -> the screens its circuits land on
        const boxes = new Map();    // "distroId|number" -> box
        const circuitDistro = new Map();   // circuit number -> its distro, or null
        for (const s of plan) {
            const key = s.distroId ? `${s.distroId}|${s.number}` : `off|${layer.id}|${s.soca}`;
            let box = boxes.get(key);
            if (!box) {
                const d = s.distroId ? distroById.get(s.distroId) || null : null;
                const typed = d ? this.distroBoxType(d, s.number).type : null;
                box = {
                    // a box on a distro by its label on paper - "-1", "-2"
                    // where two boxes share a name (distroBoxLabels) - so
                    // the binder's brackets read what the pull sheet does
                    key, name: (s.distroId && ctx.boxLabels && ctx.boxLabels.get(key)) || s.name,
                    number: s.number,
                    distroId: s.distroId || null, distro: d ? this.distroLabel(d) : null,
                    type: typed ? typed.name : null,
                    typeId: typed ? typed.id : null,
                    // A face box (1.5) says what connector it is: a direct
                    // output is one cable, a multi row its own kind.
                    kind: typed && typed.face ? typed.kind : 'multi',
                    connectorId: typed && typed.face ? typed.connectorId : null,
                    // a direct output's cable runs outlet to panel: its type
                    // names both ends where they differ (directCableType)
                    cable: typed && typed.face
                        ? (typed.kind === 'direct' ? this.directCableType(typed.cable, layer) : typed.cable)
                        : null,
                    boxSize: typed ? Number(typed.boxSize) || 6 : null,
                    // the typed home run as a length: null when none, or
                    // not one in the show's unit (parseCableLength) - and
                    // null on a multi no distro feeds: the home run is the
                    // feed's (owner, 2026-10-17), so a length an older file
                    // left on an unfed multi prints nowhere
                    homeRun: s.distroId ? this.parseCableLength(s.length) : null,
                    connector: d
                        ? this.pullPowerConnectorName(
                            this.cableConnectorName(this.boxTailConnector(d, s.number, layer)))
                        : screenConn,
                    circuits: [],
                    shared: false,
                };
                // An overfull multi box (round 7): its circuits, every
                // screen's on it (a hidden one's included: it keeps its
                // slots), against the fan - flagged like a crowded direct
                // output, and said in the home run's notes.
                const ovf = s.distroId && ctx.boxOverflows ? ctx.boxOverflows.get(key) : null;
                if (ovf) box.overfull = { circuits: ovf.circuits, size: ovf.size };
                boxes.set(key, box);
            } else if (!box.homeRun && s.distroId && this.parseCableLength(s.length) !== null) {
                box.homeRun = this.parseCableLength(s.length);
            }
            const d = box.distroId ? distroById.get(box.distroId) || null : null;
            for (const leg of s.legs) {
                circuitDistro.set(leg.circuit, d);
                on = circuitOn.get(leg.circuit) || [layer.id];
                const bo = boxOn.get(key) || [];
                for (const id of on) if (!bo.includes(id)) bo.push(id);
                boxOn.set(key, bo);
                // A cable prints only where the circuit is fed (the
                // home run's rule above - printedCircuitCable).
                const cable = this.printedCircuitCable(layer, leg.circuit);
                // A DIRECT output is one circuit on one cable, distro to
                // screen: a cable typed on the circuit IS that cable, and
                // wins over the output's home run - what the map's cable
                // tag prints (directCircuitCable). Printed once, by the
                // direct output's row below. Only when the circuit is ALONE
                // there: a multi left on a direct output (the flagged error
                // state) lists every circuit's cable and the home run as
                // their own rows - never one cable standing in for seven.
                const crowd = box.kind === 'direct'
                    ? this.directOutputCircuitCount(layer, leg.circuit) : 0;
                if (crowd > 1) box.crowded = crowd;
                // (the output's length typed in the tray's direct Cable
                // field with no cable on the circuit is that one cable too:
                // directCircuitCable falls back to the output's home run)
                const one = crowd === 1 ? this.directCircuitCable(layer, leg.circuit) : null;
                // The circuit's cable reads as that one cable too - the
                // binder's Circuits table on a direct output said the
                // circuit stock ("50' Edison → powerCON") where every
                // other surface said "30'+10' Edison → powerCON"
                // (2026-10-22).
                const said = one || cable;
                box.circuits.push({
                    num: leg.circuit, label: leg.label, tail: leg.leg,
                    tiles: leg.tiles, amps: leg.amps,
                    cable: said ? said.text : null,
                    cableFt: said ? said.ft : null,
                    cableConnector: said ? this.pullPowerConnectorName(said.name || (cable && cable.name)) : null,
                });
                if (one) {
                    box.homeRun = one.ft;
                    if (one.name) box.cable = one.name;
                } else if (cable) {
                    this._pullPowerJoin(row(cable.name ? this.pullPowerConnectorName(cable.name) : 'Power Cable',
                                            this.pullCableLength(cable.ft, 'circuit'), 1, leg.label, '', locationOf(d)));
                }
            }
        }
        // The box's own name, as the tray and the binder say it ("SR1",
        // "DISTRO 1-1", or what somebody typed; "-1", "-2" where two
        // boxes share it, distroBoxLabels) - never the distro's name
        // glued to the number, which made DISTRO 1's box 1 read
        // "DISTRO 11". Its home run, its breakout and the breakout a
        // second screen on a shared box takes all read it.
        const boxLabelOf = (box) => (ctx.boxLabels && ctx.boxLabels.get(box.key))
            || String(box.name || '').trim()
            || (typeof this._deriveMultiName === 'function'
                ? this._deriveMultiName(box.distro || '', box.number, null)
                : `${box.distro || ''}${box.number}`);
        for (const box of boxes.values()) {
            out.boxes.push(box);
            if (!box.distroId) continue;
            const seenKey = box.key;
            const distroName = box.distro || '';
            const at = locationOf(distroById.get(box.distroId));
            const isL2130 = String(box.typeId || '').startsWith('l2130')
                || box.connectorId === 'l2130';
            const isHarting = box.connectorId === 'harting';
            const breakoutType = isL2130
                ? `L21-30 ${box.connector} Breakout`
                : (isHarting ? `Harting ${box.connector} Breakout` : `${box.connector} Breakout`);
            if (boxesSeen.has(seenKey)) {
                box.shared = true;
                // The home run is said once; a screen breaking the same box
                // out to another connector takes a breakout of its own
                // (2026-10-21: one breakout row per connector).
                const brkKey = `${seenKey}|${breakoutType}`;
                if (box.kind !== 'direct' && !breakoutsSeen.has(brkKey)) {
                    breakoutsSeen.add(brkKey);
                    on = boxOn.get(box.key) || [layer.id];
                    const b = row(breakoutType, 'EA', 1, boxLabelOf(box), '', at);
                    hw('distro', box.distroId, distroName).rows.push({ ...b });
                }
                continue;
            }
            boxesSeen.add(seenKey);
            if (!distroFirstLayer.has(String(box.distroId))) {
                distroFirstLayer.set(String(box.distroId), layer.id);
            }
            const boxLabel = boxLabelOf(box);
            on = boxOn.get(box.key) || [layer.id];
            if (box.kind === 'direct') {
                // A DIRECT output (1.5): its one cable, distro to screen, in
                // the show's unit, under the output's name - no breakout.
                // The circuit's own cable when it has one (set above), else
                // the output's home run. A crowded output (several
                // circuits, the flagged error state) says so in Notes; its
                // circuits' cables are their own rows above.
                directSeen.add(seenKey);
                const notes = [box.homeRun ? '' : 'no length',
                               box.crowded ? `${box.crowded} circuits on a one-circuit output` : '']
                    .filter(Boolean).join(' · ');
                const r = this._pullPowerJoin(row(this.pullPowerConnectorName(box.cable),
                                                  this.pullCableLength(box.homeRun, 'direct'), 1, boxLabel, notes, at));
                hw('distro', box.distroId, distroName).rows.push({ ...r });
                continue;
            }
            const homeType = isL2130 ? 'L21-30' : (isHarting ? 'Harting 16E' : 'Multi');
            const homeNotes = [box.homeRun ? '' : 'no length',
                               box.overfull ? `${box.overfull.circuits} circuits on a `
                                   + `${this._fanWord(box.overfull.size)}-circuit output` : '']
                .filter(Boolean).join(' · ');
            const r = row(homeType, this.pullCableLength(box.homeRun, this.pullHomeRunKind(box)), 1, boxLabel,
                          homeNotes, at);
            breakoutsSeen.add(`${seenKey}|${breakoutType}`);
            const b = row(breakoutType, 'EA', 1, boxLabel, '', at);
            const hrec = hw('distro', box.distroId, distroName);
            hrec.rows.push({ ...r }, { ...b });
        }
        // Gangs: a circuit made of two runs is a 2fer, three a 3fer, four a
        // 4fer and so on - one splitter of its own ways each (a circuit split
        // into its columns can be any width, app-power.js nferCircuit), the
        // 4fer and wider counted under `wider` by their ways. Both the gang
        // and the circuit's jumpers go with the circuit's distro.
        const powerJumps = new Map();   // location + length -> { at, ft, n }
        for (const c of this.screenCircuits(layer)) {
            const ways = Array.isArray(c.runIds) ? c.runIds.length : 1;
            const label = this.getPowerCircuitLabel(layer, c.num);
            const at = locationOf(circuitDistro.get(c.num));
            on = circuitOn.get(c.num) || [layer.id];
            if (ways >= 2) {
                if (ways === 2) out.gangs.twofer++;
                else if (ways === 3) out.gangs.threefer++;
                else {
                    out.gangs.wider = out.gangs.wider || {};
                    out.gangs.wider[ways] = (out.gangs.wider[ways] || 0) + 1;
                }
                row(`${inputOf(c).name} ${ways}fer`, 'EA', 1, label, '', at);
            }
            // An Edison or L6-20 breakout reaches the panels through an
            // adapter cable per circuit, "Edison → TRUE1 cable" (the owner,
            // 2026-10-21: never "tail"). A circuit on a direct output has no
            // breakout: its one cable is that adapter.
            if (this.breakoutHasPanelInputChoice(breakout)
                    && !this.directOutputCircuitCount(layer, c.num)) {
                row(`${screenConn} → ${inputOf(c).name} cable`, 'EA', 1, label, '', at);
            }
            // Jumpers: every link of each run (branch) of the circuit.
            const runs = Array.isArray(c.branches) && c.branches.length ? c.branches : [c.panels];
            let off = 0;
            for (const run of runs) {
                const layers = c.layers ? c.layers.slice(off, off + run.length) : null;
                off += run.length;
                countJumpers('power', run, layers, at, powerJumps);
            }
        }
        const jumpRow = (name, { at, ft, n, on: ends, first }) => {
            on = ends;
            const r = row(name, this.pullLengthText(ft), n, grouped ? first.name : layer.name, '', at);
            if (grouped) r.split = first.name;
        };
        for (const b of powerJumps.values()) jumpRow(this.pullPowerJumpName(settings, b.conn), b);

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
        // once, a loose cable as one `Cat6 50'` row under `label` (a
        // `Cat6` row with "no length" where none is typed); then, on a
        // snaked socket, its EXTENSION as one `Cat6 Extension 25'` row
        // under the same label with "ext · <snake>" in Notes and the
        // `Cat6 Barrel` EA that joins it to the fan-out. Every
        // row is pushed to the processor's hardware rows too. `into` is
        // the port entry (or its .backup) that records what was read.
        // Every row of a socket a BOX delivers is pulled where the box
        // sits (its location); a socket straight off a card stays with
        // the screen - a processor has no location.
        // `boxId` reads the socket on a named box: a loop box's backup
        // socket shares its main's card-wide number (backedBy's cvtId).
        const owned = (cardId, socket, boxId = null) =>
            (cardId != null && socket != null && typeof this._dataPortOwner === 'function'
                ? this._dataPortOwner(cardId, socket, boxId) : null);
        const boxAt = (owner) => (owner && owner.kind === 'cvt' ? locationOf(owner.rec) : null);
        const walk = (cardId, socket, label, into, boxId = null) => {
            const owner = owned(cardId, socket, boxId);
            if (!owner) return;
            const at = boxAt(owner);
            const proc = (this.project.processors || []).find(p => p.id === owner.procId) || null;
            const procName = proc ? (proc.name || proc.deviceName || proc.id) : '';
            const push = (r) => { if (proc) hw('processor', proc.id, procName).rows.push({ ...r }); };
            if (proc && !procFirstLayer.has(proc.id)) procFirstLayer.set(proc.id, layer.id);
            // Each fiber CABLE once, however many boxes' links take it
            // (a TAC shared by four boxes is one TAC to pull): "TAC 12 ·
            // ST", "MTP 24", "opticalCON QUAD" with its length, under the
            // cable's name, where the first box that reaches it sits, and
            // on that box's processor's hardware rows.
            const sayLinks = (links) => {
                for (const l of links) {
                    // the link's own extension at the box end, said once
                    // per link, where its box sits
                    const extKey = `ext:${l.box.id}:${l.key}`;
                    if (!l.copper && this.fiberLinkExtension(l)) {
                        if (fiberSeen.has(extKey)) tagOnce(extKey);
                        else {
                            fiberSeen.add(extKey);
                            const er = row(...this._pullFiberExtensionCells(l), at);
                            saidOnce.set(extKey, er);
                            push(er);
                        }
                    }
                    const key = l.copper ? `cu:${l.box.id}:${l.key}` : `fib:${l.cable.id}`;
                    if (fiberSeen.has(key)) { tagOnce(key); continue; }
                    fiberSeen.add(key);
                    const r = l.copper ? row(...this._pullCopperCells(l), at) : (() => {
                        const ft = this.parseCableLength(l.cable.ft);
                        const has = Number.isFinite(ft) && ft > 0;
                        return row(this.fiberCableTypeText(l.cable), this.pullLengthText(ft), 1,
                                   l.cable.name || '', has ? '' : 'no length', at);
                    })();
                    saidOnce.set(key, r);
                    push(r);
                }
            };
            // A card that is a unit of its own (a QD-S) is cabled to its
            // processor on links of its own (IN 1 from the SQ200, IN 2
            // from a backup SQ200): that fiber goes where the QD-S is - with
            // the box the socket comes out of - and on this screen's rows.
            const found = typeof this._dockFindCard === 'function' ? this._dockFindCard(owner.cardId) : null;
            const host = found && found.card && found.card.linkHost ? found.card : null;
            if (host && typeof this.fiberBoxLinks === 'function') {
                sayLinks(this.fiberBoxLinks(host).filter(l => l.cable || l.copper));
            }
            if (owner.kind === 'cvt') {
                const box = owner.rec;
                into.box = this.pullBoxTitle(box);
                if (!boxFirstLayer.has(box.id)) boxFirstLayer.set(box.id, layer.id);
                const linked = typeof this.fiberBoxLinks === 'function'
                    ? this.fiberBoxLinks(box).filter(l => l.cable || l.copper) : [];
                // The 1.3 typed note prints as it always did - until a link
                // on the box has a cable.
                const fiberText = linked.length ? '' : this.pullBoxFiberText(box);
                if (fiberText && !fiberSeen.has(box.id)) {
                    fiberSeen.add(box.id);
                    const fr = row((box.fiberType || '').trim() || 'Fiber',
                                   this.pullLengthText(box.fiberFt), 1, into.box, '', at);
                    saidOnce.set(`fiber:${box.id}`, fr);
                    push(fr);
                } else if (fiberText) {
                    tagOnce(`fiber:${box.id}`);
                }
                sayLinks(linked);
            }
            // A cable made of several stock pieces is joined where they
            // meet: one barrel in the cable's word per join, per channel
            // on a snake - the extension coupler's rule (owner,
            // 2026-10-21). _pullExpandPieces counts them.
            const joined = (r, word, per = 1) => {
                if (r._pieces && r._pieces.length > 1) r._join = { type: `${word} Barrel`, per };
                return r;
            };
            const cable = this._dataPortCableOn(owner, socket);
            if (!cable) {
                // A socket with a screen on it and no home run typed still
                // takes a cable: one row in the cable's word, an empty
                // length and "no length" in Notes, as a multi, a snake or a
                // TAC with no length reads (owner, 2026-10-21).
                const rec = (owner.rec.portCables || {})[String(socket)];
                push(row(this.pullDataConnectorWord(this.dataPortConnectorId(owner, rec && rec.connector)),
                         '', 1, label, 'no length', at));
                return;
            }
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
                    // An extension is a type of its own ("Cat6 Extension"),
                    // so its note never rides onto the home runs of the same
                    // length when the rows merge. It and its barrel are
                    // labelled by the socket's own port label, "VX A-1"
                    // (owner, 2026-10-21), the note still naming the snake.
                    const sockLabel = this._pullSocketLabel(owner, socket, label);
                    push(joined(row(`${extWord} Extension`, this.pullCableLength(cable.ext, 'data'), 1, sockLabel,
                                    `ext · ${s.name || 'snake'}`, at), extWord));
                    // One barrel per extension (2026-09-07): the coupler
                    // between the fan-out and the extension, in the
                    // extension's connector word ("Cat6 Barrel"), EA, no
                    // notes. _pullMergeRows folds a snake's four into
                    // `Cat6 Barrel | EA | 4`. The backup end passes through
                    // here too, so its extension takes one as well.
                    push(row(`${extWord} Barrel`, 'EA', 1, sockLabel, '', at));
                }
                // ONE row for the loom, keyed by the SNAKE (2026-09-09:
                // "Any sockets, any device" - one snake can hold sockets
                // from several cards and boxes, and it is still one cable
                // to pull). Its hardware rows land on every processor it
                // touches, so a snake shared between two machines is on
                // both their sheets and counted once on the show's.
                const snakeKey = `snake:${s.id}`;
                if (snakesSeen.has(snakeKey)) { tagOnce(snakeKey); return; }
                snakesSeen.add(snakeKey);
                out.snakes.push({ name: s.name || '', ways, ft: s.ft || null,
                                  connector: connId || null, owner: owner.kind,
                                  ownerId: owner.id, id: s.id });
                // Labelled by the ports on it, folded ("VX A-1 … A-4"),
                // the snake's own name in Notes beside its size, "SNAKE A
                // · 4 channel" (owner, 2026-10-21). `apart` keeps it its
                // own row: two snakes never merge, whatever their channels.
                const type = `${word} Snake`;
                const ft = this.parseCableLength(s.ft);
                const size = typeof this.snakeSizeText === 'function'
                    ? this.snakeSizeText(`${type} ${s.name || ''}`, ways)
                    : `${ways} channel`;
                const ports = this._pullSnakePortLabels(s);
                const snakeRow = { type, length: this.pullCableLength(ft, 'data'),
                                   qty: 1, label: this._pullCompressNames(ports),
                                   notes: [[s.name || '', size].filter(Boolean).join(' · '),
                                           (Number.isFinite(ft) && ft > 0)
                                               ? '' : 'no length']
                                       .filter(Boolean).join('; ') };
                const r = joined(row(snakeRow.type, snakeRow.length, snakeRow.qty,
                                     snakeRow.label, snakeRow.notes, at), word, Math.max(1, ways));
                r.apart = snakeKey;
                r._labels = ports;
                saidOnce.set(snakeKey, r);
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
                push(joined(row(word, this.pullCableLength(cable.ft, 'data'), 1, label, '', at), word));
            }
        };
        // A run's jumpers go with the box delivering its primary socket.
        const dataJumps = new Map();    // location + length -> { at, ft, n }
        for (const run of this._pullPortRuns(layer)) {
            const port = { num: run.num, label: run.label, cable: null, snake: null,
                           ext: null, box: null, backup: null };
            out.ports.push(port);
            on = onOf(run.panels, run.layers);
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const at = (placed && placed.cardId && placed.port != null)
                ? boxAt(owned(placed.cardId, placed.port)) : null;
            countJumpers('data', run.panels, run.layers, at, dataJumps);
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
                walk(bb.cardId, bb.port, label, port.backup, bb.cvtId || null);
            }
        }
        for (const b of dataJumps.values()) jumpRow(settings.dataJumpName, b);
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

    // A group member's jumper row (`split`) is keyed with its screen, so an
    // edit to "Data Jump 2' WALL SL" never lands on WALL SR's; a snake's row
    // (`apart`) with its snake, so two snakes of one length keep their own.
    pullRowKey(row) {
        return `${row && row.type != null ? row.type : ''}|${row && row.length != null ? row.length : ''}`
            + (row && row.split ? `|${row.split}` : '')
            + (row && row.apart ? `|${row.apart}` : '');
    }

    // A stored edit's key as the row it answers to is keyed today: a key
    // whose type is a Brompton model under its old name ("Tessera
    // XD|EA") reads as that model's row now ("XD|EA"), an old data word
    // ("Ether-con|50'") as its Cat6 row ("Cat6|50'"), and one on a
    // "Tru-1" row as its TRUE1 row ("Tru-1 Breakout|EA" is
    // "TRUE1 Breakout|EA"; the old shipped jumper name "Tru-1 Power Jump"
    // is the TRUE1 jumper's shipped one), and the Edison adapter's old
    // "Edison → TRUE1 tail|EA" as "Edison → TRUE1 cable|EA", and a distro's
    // old "Feeder|50'" / "Feed|50'" / "L21-30 feeder|50'" / "L21-30
    // feed|50'" as its "Power in|50'" / "L21-30 power in|50'" (unless that
    // type is a distro Type somebody typed). Every
    // other key is itself. Nothing is rewritten on open - the stored key
    // takes the new spelling the next time somebody edits that row.
    pullEditKey(key) {
        const text = String(key == null ? '' : key);
        if (PULL_LEGACY_ADAPTER.test(text)) return text.replace(PULL_LEGACY_ADAPTER, '$1 cable');
        {
            const cut = text.indexOf('|');
            const type = cut < 0 ? text : text.slice(0, cut);
            const m = PULL_LEGACY_FEEDER.exec(type);
            if (m && (!m[1] || this._pullDistroInputNames().has(m[1]))
                    && !this._pullUserTypeNames().has(type.toLowerCase())) {
                return (m[1] ? `${m[1]} power in` : 'Power in') + (cut < 0 ? '' : text.slice(cut));
            }
        }
        // A key whose type is the USER'S TEXT - a distro's Type, a jumper
        // name somebody typed, a panel name from Screen Info - is never
        // rewritten (2026-10-22): its row prints that text as typed, so
        // the key keeps matching it ("Tru-1 Rack|EA" on a distro typed so).
        {
            const cut = text.indexOf('|');
            const type = cut < 0 ? text : text.slice(0, cut);
            PULL_LEGACY_TRUE1_WORD.lastIndex = 0;
            const old = PULL_LEGACY_TRUE1_WORD.test(type) || PULL_LEGACY_DATA_TYPES.has(type)
                || type.startsWith(PULL_LEGACY_TYPE_PREFIX);
            PULL_LEGACY_TRUE1_WORD.lastIndex = 0;
            if (old && type !== LEGACY_POWER_JUMP_NAME
                    && this._pullUserTypeNames().has(type.toLowerCase())) return text;
        }
        // "Tru-1 ...|len" is the TRUE1 row of the same name now - and so
        // is a type with "Tru-1" anywhere in it as a word ("L21-30 Tru-1
        // Breakout") - unless it is a jumper name somebody typed, which
        // still prints as typed
        {
            const cut = text.indexOf('|');
            const type = cut < 0 ? text : text.slice(0, cut);
            PULL_LEGACY_TRUE1_WORD.lastIndex = 0;
            if (PULL_LEGACY_TRUE1_WORD.test(type)
                    && type !== this.getPullSheetSettings().powerJumpNameTrue1) {
                return type.replace(PULL_LEGACY_TRUE1_WORD, '$1TRUE1') + (cut < 0 ? '' : text.slice(cut));
            }
        }
        const cut = text.indexOf('|');
        const type = cut < 0 ? text : text.slice(0, cut);
        if (PULL_LEGACY_DATA_TYPES.has(type)) {
            return PULL_LEGACY_DATA_TYPES.get(type) + (cut < 0 ? '' : text.slice(cut));
        }
        if (!text.startsWith(PULL_LEGACY_TYPE_PREFIX)) return text;
        const model = type.slice(PULL_LEGACY_TYPE_PREFIX.length);
        if (!PULL_LEGACY_PREFIXED_TYPES.has(model)) return text;
        return model + (cut < 0 ? '' : text.slice(cut));
    }

    // ---- old edits on renamed rows (owner, 2026-10-21) ----------------------
    //
    // An edit saved by 1.5.2 or a 1.5.3 beta is keyed on what the row was
    // called then. Where the new name depends on the position's own rows,
    // pullEditKey alone cannot say it, so these keys are read against the
    // rows the position has now (_pullResolveEditKey):
    //   * an old data word ("Ether-con|25'", "Data Cable|25'", "Barrel|EA")
    //     is that position's Cat6 row, else its etherCON row;
    //   * a snake key with no snake on it ("Ether-con Snake|100'", "Cat6
    //     Snake|100'", "Snake|100'") is the position's ONE snake row of that
    //     type and length; with several it stays stale;
    //   * "Tru-1 Power Jump|6'" is the TRUE1 jumper row, else (a powerCON
    //     screen) the powerCON jumper row of that length;
    //   * "Edison 2fer|EA", "L6-20 3fer|EA" ... are "<panel input> Nfer",
    //     TRUE1 or powerCON, whichever the position has;
    //   * an old direct output's cable by its plug alone ("CEE 16A|50'",
    //     "Tru-1|25'") is the position's "<plug> → <input>|len" row where
    //     it is the only one (2026-10-22).
    // AN OLD ROW THAT IS TWO ROWS NOW (owner, 2026-10-22): "Ether-con|25'"
    // at a position with both a Cat6 and an etherCON 25', "Tru-1 Power
    // Jump|6'" with both a TRUE1 and a powerCON 6' jumper. A HIDE covers
    // both rows; a count, label or note cannot say which of them it meant
    // and goes stale, shown in the editor for the user to redo
    // (_pullEditHits, getPullSheetEdits).
    // A 1.5.2 extension printed as "Ether-con|25'" too and cannot be told
    // from a home run: it stays on the home-run row. Every other key is
    // pullEditKey's.

    // A FREE ROW'S TYPE in today's spelling (owner, 2026-10-22: "Rewrite
    // to TRUE1 / etherCON"): a row somebody typed on the pull sheet in
    // 1.5.2 or 1.5.3 says "Tru-1", "TRU-1" or "True1" for TRUE1,
    // "Ether-con" for etherCON, "... tail" for "... cable". Read so on
    // every paper - the pull pages, the xlsx, the GEAR LIST - so the new
    // word counts as a connector in use and the old one never prints.
    // Anything else is the user's own words, as typed.
    // "tail" is "cable" only on an ADAPTER (owner, 2026-10-22): a type
    // with "→" in it, or "Edison tail" / "L6-20 tail". Any other "tail"
    // is the user's word: "Tail rope" stays "Tail rope".
    pullFreeRowType(type) {
        return this._pullFreeRowWords(type, false);
    }

    // The old words in a free row's text: TRUE1 and etherCON - an old
    // word glued to a plural "s" or a "-" too ("Tru-1s", "Ether-con-50",
    // 2026-10-23; "TRU-1S", "Tru-1s-50" and "Tru-1-to-Ether-con", round 6)
    // - and "tail" (or "tails") as "cable" where it names an adapter. In a
    // TYPE an arrow makes the whole row an adapter; in NOTES (`notes`) an
    // arrow says nothing about the rest of the sentence, so only the
    // "tail" right after "→ <word>", or right after the arrow itself, is
    // the adapter's ("Tail rope for the Edison → TRUE1 tail" keeps its
    // "Tail rope"). pull_sheet.free_row_spelling reads a row the same way.
    _pullFreeRowWords(type, notes) {
        if (type == null) return type;
        // a plural "s" is the connector's own, always lower case: "TRU-1S"
        // reads "TRUE1s"
        const end = '(?:([sS])(?!\\w)|(?![\\w-])|(?=-))';
        const t = String(type)
            .replace(new RegExp('(^|\\W)(?:Tru-1|TRU-1|tru-1|True1|true1)' + end, 'g'),
                (m, lead, s) => `${lead}TRUE1${s ? 's' : ''}`)
            .replace(new RegExp('(^|\\W)(?:Ether-con|ether-con|Ether-Con|ETHER-CON)' + end, 'g'),
                (m, lead, s) => `${lead}etherCON${s ? 's' : ''}`);
        const cable = (w, s) => (w === 'TAIL' ? 'CABLE' : w === 'Tail' ? 'Cable' : 'cable')
            + (s === 'S' ? 'S' : s ? 's' : '');
        const plug = (text) => text.replace(
            /(^|[^\w-])((?:Edison|EDISON|edison|L6-20|l6-20)\s+)(tail|Tail|TAIL)([sS]?)(?![\w-])/g,
            (m, lead, p, w, s) => lead + p + cable(w, s));
        if (notes) {
            // (the tail right after the arrow tried first: "-> Tail TAILS"
            // reads "-> Cable TAILS", round 7)
            return plug(t.replace(/((?:→|->)\s*(?:\S+\s+)??)(tail|Tail|TAIL)([sS]?)(?![\w-])/g,
                (m, lead, w, s) => lead + cable(w, s)));
        }
        if (/→|->/.test(t)) {
            return t.replace(/(^|[^\w-])(tail|Tail|TAIL)([sS]?)(?![\w-])/g, (m, lead, w, s) => lead + cable(w, s));
        }
        return plug(t);
    }

    // A FREE ROW'S NOTES in today's spelling too (owner, 2026-10-22: "Old
    // free-row NOTES are rewritten too"): each thing the notes say - the
    // pieces between " · ", "; " and ", " - read the way a type is, but
    // for an arrow, which turns only its own "tail" into "cable".
    pullFreeRowNotes(notes) {
        if (notes == null) return notes;
        return String(notes).split(/( · |; |, )/)
            .map((piece, i) => (i % 2 ? piece : this._pullFreeRowWords(piece, true))).join('');
    }

    // A free row in today's spelling, its type and its notes.
    _pullFreeRowSpelled(r) {
        if (!r || typeof r !== 'object') return r;
        const out = { ...r, type: this.pullFreeRowType(r.type) };
        if (r.notes != null) out.notes = this.pullFreeRowNotes(r.notes);
        return out;
    }

    // The names of the distro inputs, as a power in row prints them
    // ("L21-30", "Powerlock 400 A"): the words an old "<input> feed" row
    // started with (pullEditKey).
    _pullDistroInputNames() {
        const list = typeof this.distroInputs === 'function' ? this.distroInputs() || [] : [];
        return new Set(list.map(i => i && i.name).filter(Boolean));
    }

    // The row types that are the user's own text, lower-cased: every
    // distro's typed Type, the jumper names (a custom one from an old file
    // too) and every screen's panel names (a name typed in Screen Info,
    // its halves). The shipped jumper names are the app's.
    _pullUserTypeNames() {
        const out = new Set();
        const add = (t) => { const v = String(t == null ? '' : t).trim(); if (v) out.add(v.toLowerCase()); };
        const distros = typeof this.getDistros === 'function' ? this.getDistros() || [] : [];
        for (const d of distros) add(d && d.typeName);
        const shipped = new Set(Object.values(PULL_SHEET_DEFAULTS || {}).map(v => String(v)));
        const s = this.getPullSheetSettings();
        for (const k of ['powerJumpNameTrue1', 'powerJumpNamePowercon', 'dataJumpName']) {
            if (s && s[k] != null && !shipped.has(String(s[k]))) add(s[k]);
        }
        const stored = (this.project && this.project.pullSheet) || {};
        if (typeof this._legacyPowerJumpName === 'function') add(this._legacyPowerJumpName(stored.powerJumpName));
        for (const l of ((this.project && this.project.layers) || [])) {
            if (!l || (l.type || 'screen') !== 'screen') continue;
            const name = String(l.panelModelName || '').trim();
            if (!name) continue;
            const t = this.pullPanelTypes(l);
            for (const k of ['none', 'height', 'width']) add(t[k]);
        }
        out.delete(String(LEGACY_POWER_JUMP_NAME).toLowerCase());
        return out;
    }

    // Does this stored key need the position's rows to be placed?
    _pullEditNeedsRows(key) {
        const text = String(key == null ? '' : key);
        const cut = text.indexOf('|');
        if (cut < 0) return false;
        const type = text.slice(0, cut);
        const parts = text.slice(cut + 1).split('|');
        if (PULL_LEGACY_DATA_TYPES.has(type)) return true;
        if (/ Snake$/.test(type) && parts.length === 1) return true;
        if (this._pullLegacyJumpNames().includes(type)) return true;
        // (a key already spelled as a panel input - "TRUE1|25'",
        // "powerCON|25'" - is today's row from that outlet, read alone)
        if (parts.length === 1 && parts[0] !== 'EA' && !this._pullPanelInputNames().has(type)
                && this._pullDirectPlugNames().has(this._pullEditType(key))) {
            return true;
        }
        const fer = /^(.+) (\d+)fer$/.exec(type);
        return !!(fer && fer[1] !== 'TRUE1' && fer[1] !== 'powerCON');
    }

    // A stored key's type as pullEditKey reads it ("Tru-1|25'" -> "TRUE1").
    _pullEditType(key) {
        const plain = this.pullEditKey(key);
        const cut = plain.indexOf('|');
        return cut < 0 ? plain : plain.slice(0, cut);
    }

    _pullPanelInputNames() {
        const all = typeof this.getPanelInputTypes === 'function' ? this.getPanelInputTypes() : [];
        return new Set(all.map(t => t && t.name).filter(Boolean));
    }

    // The plugs a direct output's cable is named by ("Edison", "CEE 16A",
    // "TRUE1"): an old key on one of them alone was that output's cable.
    _pullDirectPlugNames() {
        const all = typeof this.distroConnectors === 'function' ? this.distroConnectors() : [];
        return new Set(all.filter(c => c && c.kind === 'direct' && c.cable).map(c => c.cable));
    }

    // The jumper names an old file keyed its power jumper rows on: the
    // shipped "Tru-1 Power Jump" and a single name somebody customised.
    _pullLegacyJumpNames() {
        const stored = (this.project && this.project.pullSheet) || {};
        const custom = stored.powerJumpNameTrue1 == null ? this._legacyPowerJumpName(stored.powerJumpName) : null;
        return custom ? [LEGACY_POWER_JUMP_NAME, custom] : [LEGACY_POWER_JUMP_NAME];
    }

    // A stored key as the row it answers to among `liveKeys` (the
    // pullRowKey of every engine row of its position). A key the rows
    // cannot place is pullEditKey's reading: an edit on no live row is
    // stale, as before.
    // An old key whose row is two rows now (_pullEditHits) answers to
    // neither: it keeps its own spelling, so a count on it is stale.
    _pullResolveEditKey(key, liveKeys) {
        const plain = this.pullEditKey(key);
        if (!this._pullEditNeedsRows(key)) return plain;
        const hits = this._pullEditHits(key, liveKeys);
        if (hits.length > 1) return String(key);
        return hits.length ? hits[0] : plain;
    }

    // The live rows an old key that needs its position's rows answers to:
    // one, or none (it reads as pullEditKey), or - for an old row that
    // is two rows now - each of them.
    _pullEditHits(key, liveKeys) {
        const plain = this.pullEditKey(key);
        if (!this._pullEditNeedsRows(key)) return [];
        const live = liveKeys instanceof Set ? liveKeys : new Set(liveKeys || []);
        const text = String(key);
        const cut = text.indexOf('|');
        const type = text.slice(0, cut);
        const rest = text.slice(cut);                 // "|25'" or "|6'|WALL-A"
        const length = rest.slice(1).split('|')[0];
        const all = (keys) => keys.filter(k => live.has(k));
        // the data words: Cat6, else etherCON
        let types = null;
        if (PULL_LEGACY_DATA_TYPES.has(type)) {
            const cat = PULL_LEGACY_DATA_TYPES.get(type);
            types = [cat, cat.replace(/^Cat6/, 'etherCON')];
        } else if (/ Snake$/.test(type)) {
            types = [type];
        }
        if (types && / Snake$/.test(types[0]) && rest.split('|').length === 2) {
            // a snake by its type and length: the only one there is
            // (several of them: it stays stale, whatever it was)
            for (const t of types) {
                const head = `${t}|${length}|`;
                const hits = [...live].filter(k => k.startsWith(head));
                if (hits.length === 1) return hits;
                if (hits.length > 1) return [];
            }
            return [];
        }
        if (types) return all(types.map(t => t + rest));
        if (this._pullLegacyJumpNames().includes(type)) {
            return all([plain, `${this.getPullSheetSettings().powerJumpNamePowercon}${rest}`]);
        }
        const fer = /^(.+) (\d+)fer$/.exec(type);
        if (fer) return all([`TRUE1 ${fer[2]}fer${rest}`, `powerCON ${fer[2]}fer${rest}`]);
        // an old direct output's cable by its plug: the one "<plug> →
        // <input>" row of that length (the plug's own row where it is the
        // input too)
        const plug = this._pullEditType(key);
        if (this._pullDirectPlugNames().has(plug)) {
            const plainRest = plain.slice(plain.indexOf('|'));
            if (live.has(plain)) return [plain];
            const hits = [...live].filter(k => k.startsWith(`${plug} → `)
                && k.indexOf('|') >= 0 && k.slice(k.indexOf('|')) === plainRest);
            return hits.length === 1 ? hits : [];
        }
        return [];
    }

    // The pullRowKey of every row of one position of `list`.
    _pullPositionRowKeys(list, positionKey) {
        const pos = ((list && list.positions) || []).find(p => this.pullPositionKey(p) === positionKey);
        return new Set(((pos && pos.rows) || []).map(r => this.pullRowKey(r)));
    }

    // The stored edits, never the store itself (readers must not mutate).
    // Each row edit carries its key as the row it answers to reads it
    // (pullEditKey; an old key on a renamed row is read against its
    // position's rows in `list`, or in the show's own list when none is
    // handed in - _pullResolveEditKey); where an old key and its new
    // spelling both hold an edit, the new one is the edit.
    getPullSheetEdits(list) {
        const stored = (this.project && this.project.pullSheetEdits) || {};
        let engine = list || null;
        const liveOf = (positionKey) => {
            if (!engine) {
                try { engine = this.buildPullList(); } catch (err) {
                    sendClientLog('pull_edit_rows_failed', { error: String(err) });
                    engine = { positions: [] };
                }
            }
            return this._pullPositionRowKeys(engine, positionKey);
        };
        const positions = {};
        for (const [k, v] of Object.entries(stored.positions || {})) {
            if (!v || typeof v !== 'object') continue;
            const held = Array.isArray(v.rows) ? v.rows : [];
            let live = null;
            const keyOf = (raw) => (this._pullEditNeedsRows(raw)
                ? this._pullResolveEditKey(raw, live || (live = liveOf(k)))
                : this.pullEditKey(raw));
            const rows = [];
            for (const r of held) {
                // an old row that is two rows now: a hide covers both
                if (r && r.removed && r.key != null && this._pullEditNeedsRows(r.key)) {
                    const hits = this._pullEditHits(r.key, live || (live = liveOf(k)));
                    if (hits.length > 1) {
                        for (const hit of hits) {
                            if (held.some(x => x && x.key === hit) || rows.some(x => x.key === hit)) continue;
                            rows.push({ ...r, key: hit });
                        }
                        continue;
                    }
                }
                const key = r && r.key != null ? keyOf(r.key) : null;
                if (key === null || key === r.key) { rows.push({ ...r }); continue; }
                if (held.some(x => x && x.key === key)) continue;
                rows.push({ ...r, key });
            }
            positions[k] = {
                rows,
                // a free row typed in 1.5.2 / 1.5.3 reads in today's
                // spelling (pullFreeRowType)
                added: Array.isArray(v.added)
                    ? v.added.map(r => this._pullFreeRowSpelled(r))
                    : [],
            };
        }
        return { positions };
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

    // A free row's side, for the binder's power / data split. Whole words
    // only, so "Contactor", "Stacking plate" and "Ground Stack" never read
    // as data through "tac":
    //   * a POWER word wins outright - a connector or a feed (Socapex,
    //     Camlok, Edison, TRUE1, powerCON, L21-30, power ...), so
    //     "Socapex Snake" and "Camlok Barrel" are power;
    //   * then a DATA word makes it data - Cat5e / Cat6 / Cat6A, etherCON
    //     or Ethernet, fiber, SDI, HDMI, data, a snake, a barrel, a TAC,
    //     MTP, opticalCON, SFP, OPT, a CVT, XD ("Optical isolator" is
    //     not: "optical" alone is no data word);
    //   * then a MODEL the catalog or the show names (XD, H9, MX40 Pro)
    //     makes it data only where it is the whole name, or the name's
    //     head followed by nothing but an equipment word - "S4 rack",
    //     "H9 spare (2)" are data, "S4 Spanset", "T1 Tape", "M2 bolt" are
    //     not (_pullModelIsHead);
    //   * then a PANEL word ("Spare panel", "Half tile", "cabinet") makes
    //     it a panel, side 'panel' - printed with the show's panel rows -
    //     unless another word names other gear ("Breakout panel", "Truss
    //     panel" are power; "Patch panel" is data, a patch a data word);
    //   * everything else is power.
    // Before all of these, a type that IS one of the show's panel types
    // (the name a panel row prints, pullPanelTypes) is a panel, whatever
    // words its maker put in it. The pull sheet has no hardware side: a
    // processor and a box are data, a distro power, and its panels are
    // their own side.
    pullGuessSide(type) {
        const text = String(type || '').trim();
        const lower = text.toLowerCase();
        if (lower && this._pullPanelTypeNames().has(lower)) return 'panel';
        if (PULL_POWER_WORDS.test(text)) return 'power';
        if (PULL_DATA_WORDS.test(text)) return 'data';
        if (PULL_FEED_WORD.test(text)) return 'power';
        if (PULL_PANEL_WORDS.test(text) && !PULL_NOT_PANEL_WORDS.test(text)) return 'panel';
        // an old row's "Tessera SX40" is the SX40 (2026-10-23): the device
        // check reads the model with the retired prefix off as well
        const prefix = PULL_LEGACY_TYPE_PREFIX.toLowerCase();
        const bare = lower.startsWith(prefix) ? lower.slice(prefix.length).trim() : null;
        return this._pullDataDeviceNames().some(n => this._pullModelIsHead(lower, n)
            || (!!bare && this._pullModelIsHead(bare, n))) ? 'data' : 'power';
    }

    // `model` (lower-cased) is the whole of `lower`, or its head with only
    // equipment words after it ("rack", "spare", a count, a note in
    // brackets).
    _pullModelIsHead(lower, model) {
        if (!lower.startsWith(model)) return false;
        const rest = lower.slice(model.length);
        if (!rest.trim()) return true;
        if (!/^[\s(]/.test(rest)) return false;
        const words = rest.replace(/\([^)]*\)/g, ' ').trim().split(/\s+/).filter(Boolean);
        return words.every(w => PULL_MODEL_TAIL_WORDS.has(w) || /^x?\d+x?$/.test(w));
    }

    // Every processor, card and breakout box model the catalog and the
    // show name, lower-cased, a "RS12 / MSM4214X" as both and a
    // "(legacy)" left off: the words pullGuessSide reads as data.
    // A catalog model also counts by its common short name (2026-10-22:
    // "UHD JR" for a NovaPro UHD Jr): the catalog's own shortName, and the
    // name with its product-line head dropped where what is left still
    // names one model - two words or more, or one carrying a digit
    // ("UHD Jr", never a bare "Pro" or "Jr").
    _pullDataDeviceNames() {
        const names = new Set();
        // (and a model's short name without its "Pro": "MX40" for an
        // MX40 Pro, where what is left carries a digit - 2026-10-22)
        const addOne = (n) => {
            names.add(n);
            const bare = n.replace(/\s+pro$/, '');
            if (bare !== n && /\d/.test(bare) && bare.length >= 3) names.add(bare);
        };
        const add = (name) => String(name || '').replace(/\([^)]*\)/g, '').split('/')
            .map(n => n.trim().toLowerCase()).filter(n => n.length >= 2).forEach(n => {
                addOne(n);
                const rest = n.split(/\s+/).slice(1);
                if (rest.length >= 2 || (rest.length === 1 && /\d/.test(rest[0]) && rest[0].length >= 3)) {
                    addOne(rest.join(' '));
                }
            });
        const devices = typeof this._processorDevices === 'function' ? this._processorDevices() : [];
        for (const d of devices) {
            add(d && d.name);
            add(d && d.shortName);
        }
        for (const proc of this._processorsResolved || []) {
            add(proc && proc.deviceName);
            for (const slot of (proc && proc.slots) || []) {
                const card = slot && slot.card;
                if (!card) continue;
                add(card.deviceName);
                for (const box of card.cvts || []) add(box && box.deviceName);
            }
        }
        return [...names];
    }

    // Engine list in, the list the papers print out: overrides overlaid,
    // hidden rows dropped, added rows appended, totals recomputed. A key
    // no edit touches keeps the engine's totals row verbatim (its folded
    // labels); a touched key is rebuilt from the edited position rows.
    //
    // The edits reach the per-screen readings and the hardware pull lists
    // too (owner, 2026-10-21) - the binder's CABLES THIS SCREEN tables and
    // each distro's and processor's "Pull list" (_pullCarryEdits). Free
    // rows have no screen and stay on the pull pages.
    applyPullSheetEdits(list) {
        const edits = this.getPullSheetEdits(list);
        const out = { ...list, positions: [], totals: (list.totals || []).slice() };
        // the totals are by type and length, whatever split a row carries -
        // and by snake, as the engine's are (_pullMergeRows)
        const totalKey = (r) => `${r && r.type != null ? r.type : ''}|${r && r.length != null ? r.length : ''}`
            + (r && r.apart ? `|${r.apart}` : '');
        const touched = new Set();
        const touchedRows = [];
        // What each engine-row edit does to the screens and the hardware:
        // [{ posKey, row (the engine's), removed, qty }]
        const carried = [];
        let any = false;
        for (const pos of list.positions || []) {
            const pe = edits.positions[this.pullPositionKey(pos)];
            const rows = [];
            for (const r of pos.rows || []) {
                const key = this.pullRowKey(r);
                const e = pe ? pe.rows.find(x => x.key === key) : null;
                if (!e) { rows.push({ ...r }); continue; }
                any = true;
                touched.add(totalKey(r));
                const qty = this._pullQtyValue(e.qty);
                if (e.removed || (qty !== null && qty !== r.qty)) {
                    carried.push({ posKey: pos.key || this.pullPositionKey(pos), row: r,
                                   removed: !!e.removed, qty });
                }
                if (e.removed) continue;
                const row = { ...r };
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
                    side: ['data', 'power', 'panel'].includes(a.side) ? a.side : this.pullGuessSide(type),
                    added: true,
                };
                touched.add(totalKey(row));
                rows.push(row);
                touchedRows.push(row);
            }
            out.positions.push({ ...pos, rows: this._pullSortRows(rows) });
        }
        if (!any) return { ...list, positions: out.positions };
        const kept = out.totals.filter(t => !touched.has(totalKey(t)));
        const rebuilt = new Map();
        for (const pos of out.positions) {
            for (const r of pos.rows) {
                const key = totalKey(r);
                if (!touched.has(key)) continue;
                let hit = rebuilt.get(key);
                if (!hit) {
                    hit = { type: r.type, length: r.length, qty: 0, labels: [], notes: [], side: r.side || 'power' };
                    if (r.apart) hit.apart = r.apart;
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
            ...(h.apart ? { apart: h.apart } : {}),
        })));
        out.totals = this._pullSortRows(totals);
        if (carried.length) this._pullCarryEdits(list, out, carried);
        return out;
    }

    // An edit on a position row, carried to the screens and hardware sheets
    // whose cables that row counts (buildPullList's `_shares`):
    //   * HIDE takes the row's cables off every screen's table and every
    //     hardware pull list it was counted on - each loses exactly what
    //     it gave that row.
    //   * A COUNT goes to a screen only where the row maps 1:1 - every
    //     cable it counts came from that one screen's walk. Then the
    //     screen's own row of that type and length moves by the
    //     difference (it may also hold the same cable pulled at another
    //     position, which keeps its count). A row counting several
    //     screens' cables (a beach's Multi 100' x 4 from two walls) cannot
    //     say whose cable the change is, so each screen keeps its own
    //     count and the pull sheet's totals carry the edit. The hardware
    //     pull lists follow the same rule, per distro or processor.
    // The engine's byScreen and hardware are never written: the touched
    // screens and sheets are copies.
    _pullCarryEdits(list, out, carried) {
        const shares = list && list._shares;
        if (!shares) return;
        const byScreen = { ...(list.byScreen || {}) };
        const hardware = (list.hardware || []).slice();
        const cloned = new Set();
        const screen = (id) => {
            const s = byScreen[id];
            if (!s) return null;
            if (!cloned.has(`s:${id}`)) {
                cloned.add(`s:${id}`);
                byScreen[id] = { ...s, rows: (s.rows || []).map(r => ({ ...r })),
                                 rowsOn: (s.rowsOn || []).map(r => this._pullTagPosition({ ...r }, r._pos)) };
            }
            return byScreen[id];
        };
        const sheet = (hwKey) => {
            const i = hardware.findIndex(h => `${h.kind}:${h.id}` === hwKey);
            if (i < 0) return null;
            if (!cloned.has(`h:${hwKey}`)) {
                cloned.add(`h:${hwKey}`);
                hardware[i] = { ...hardware[i], rows: (hardware[i].rows || []).map(r => ({ ...r })) };
            }
            return hardware[i];
        };
        const same = (a, b) => a.type === b.type && a.length === b.length
            && (a.apart || '') === (b.apart || '');
        // Move a merged row's count by `delta`; a row brought to nothing goes.
        const moveRows = (rows, row, delta) => {
            const i = rows.findIndex(r => same(r, row));
            if (i < 0) return;
            rows[i].qty = (Number(rows[i].qty) || 0) + delta;
            if (rows[i].qty <= 0) rows.splice(i, 1);
        };
        // The same on the unmerged rows that position pulled: taken off the
        // last first, added to the first.
        const moveRowsOn = (rows, row, posKey, delta) => {
            const hits = [];
            rows.forEach((r, i) => {
                if (same(r, row) && (r.split || '') === (row.split || '') && r._pos === posKey) hits.push(i);
            });
            if (!hits.length) return;
            if (delta > 0) { rows[hits[0]].qty += delta; return; }
            let left = -delta;
            for (let k = hits.length - 1; k >= 0 && left > 0; k--) {
                const r = rows[hits[k]];
                const take = Math.min(left, Number(r.qty) || 0);
                r.qty -= take;
                left -= take;
            }
            for (let k = hits.length - 1; k >= 0; k--) if (rows[hits[k]].qty <= 0) rows.splice(hits[k], 1);
        };
        const sum = (m) => [...m.values()].reduce((a, b) => a + b, 0);
        for (const c of carried) {
            const share = shares.get(`${c.posKey}\n${this.pullRowKey(c.row)}`);
            if (!share) continue;
            const engineQty = Number(c.row.qty) || 0;
            const oneTo = (m) => (m.size === 1 && sum(m) === engineQty ? [...m.keys()][0] : null);
            if (c.removed) {
                for (const [id, q] of share.screens) {
                    const s = screen(id);
                    if (!s) continue;
                    moveRows(s.rows, c.row, -q);
                    moveRowsOn(s.rowsOn, c.row, c.posKey, -q);
                }
                for (const [hwKey, q] of share.hw) {
                    const h = sheet(hwKey);
                    if (h) moveRows(h.rows, c.row, -q);
                }
                continue;
            }
            const delta = c.qty - engineQty;
            const id = oneTo(share.screens);
            if (id != null) {
                const s = screen(id);
                if (s) {
                    moveRows(s.rows, c.row, delta);
                    moveRowsOn(s.rowsOn, c.row, c.posKey, delta);
                }
            }
            const hwKey = oneTo(share.hw);
            if (hwKey != null) {
                const h = sheet(hwKey);
                if (h) moveRows(h.rows, c.row, delta);
            }
        }
        out.byScreen = byScreen;
        out.hardware = hardware;
    }

    // THE list both papers print: the engine's reading with the user's
    // edits on top.
    buildPullSheet() {
        return this.applyPullSheetEdits(this.buildPullList());
    }

    // For the editor: the stored overrides no engine row answers to any
    // more - kept, flagged, never exported. [{ positionKey, key, edit }].
    pullSheetStaleEdits(list) {
        const engine = list || this.buildPullList();
        const edits = this.getPullSheetEdits(engine);
        const live = new Map();
        for (const pos of engine.positions || []) {
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

    // ---- an edit goes with the cable it was made on -----------------------
    //
    // A delete or a clear forgets the lengths it took the feed from (owner,
    // 2026-10-17), and the pull-sheet row those lengths printed goes with
    // them - so must the saved edit on that row. Left behind, it sat in
    // the editor as STALE and came straight back onto the paper the day
    // another cable of the same type and length landed on that position.
    // A clear reads the rows before it moves anything (_pullLiveRowKeys)
    // and hands them to _dropPullEditsGoneWith once its stores are
    // written and BEFORE its snapshot, so one undo puts the edit back with
    // the cable. Only rows the clear took away go: a row still printed
    // (one 25' multi of two cleared) keeps its edit, and a free row is
    // the user's own. null where the show has no edits - the walk is
    // skipped altogether.
    _pullLiveRowKeys() {
        const stored = this.project && this.project.pullSheetEdits;
        if (!stored || !stored.positions
                || !Object.keys(stored.positions).length) return null;
        try {
            this._circuitTailCache = null;
            const out = new Set();
            for (const pos of this.buildPullList().positions || []) {
                const pk = this.pullPositionKey(pos);
                for (const r of pos.rows || []) out.add(`${pk}\n${this.pullRowKey(r)}`);
            }
            return out;
        } catch (err) {
            sendClientLog('pull_edit_rows_failed', { error: String(err) });
            return null;
        }
    }

    _dropPullEditsGoneWith(before) {
        if (!before) return false;
        const after = this._pullLiveRowKeys();
        const store = this.project && this.project.pullSheetEdits;
        if (!after || !store || !store.positions) return false;
        let dropped = 0;
        for (const [pk, pos] of Object.entries(store.positions)) {
            if (!pos || !Array.isArray(pos.rows)) continue;
            // an old key is read against the rows the position had
            let had = null;
            const keyOf = (raw) => (this._pullEditNeedsRows(raw)
                ? this._pullResolveEditKey(raw, had || (had = new Set([...before]
                    .filter(k => k.startsWith(`${pk}\n`)).map(k => k.slice(pk.length + 1)))))
                : this.pullEditKey(raw));
            pos.rows = pos.rows.filter(e => {
                // a hide on an old row that is two rows now goes when
                // both of them go
                if (e && e.removed && this._pullEditNeedsRows(e.key)) {
                    const keyOf2 = keyOf(e.key);
                    const hits = this._pullEditHits(e.key, had);
                    if (keyOf2 === String(e.key) && hits.length > 1) {
                        const gone = hits.every(h => before.has(`${pk}\n${h}`) && !after.has(`${pk}\n${h}`));
                        if (gone) dropped++;
                        return !gone;
                    }
                }
                const k = `${pk}\n${keyOf(e && e.key)}`;
                if (before.has(k) && !after.has(k)) { dropped++; return false; }
                return true;
            });
        }
        if (!dropped) return false;
        this._pullPruneEdits();
        this._persistPullSheetEdits();
        sendClientLog('pull_edits_dropped', { count: dropped });
        return true;
    }

    // ---- the edits: one history entry each, then one project POST ----

    _commitPullSheetEdit(action) {
        this._pullPruneEdits();
        this.saveState(action);
        this._persistPullSheetEdits();
        if (typeof this.renderPullSheetEditorTotals === 'function') this.renderPullSheetEditorTotals();
    }

    // On the pull sheet's one queue (_postPullSheetState).
    _persistPullSheetEdits() {
        return this._postPullSheetState(['pullSheetEdits']);
    }

    // The live edit on row KEY in one position's store: the one stored
    // under KEY itself, else one under an older spelling of it
    // (pullEditKey, or _pullResolveEditKey against the position's rows
    // now, for a key only they can place). A writer that takes it stores
    // KEY on it.
    _pullFindRowEdit(pos, key, positionKey) {
        const rows = (pos && pos.rows) || [];
        const keyOf = this._pullStoredKeyReader(positionKey);
        return rows.find(x => x && x.key === key)
            || rows.find(x => x && keyOf(x.key) === key) || null;
    }

    // stored key -> the row key it answers to on one position, the
    // position's rows built once and only for a key that needs them.
    _pullStoredKeyReader(positionKey) {
        let live = null;
        return (raw) => {
            if (positionKey == null || !this._pullEditNeedsRows(raw)) return this.pullEditKey(raw);
            if (!live) {
                try { live = this._pullPositionRowKeys(this.buildPullList(), positionKey); } catch (err) {
                    sendClientLog('pull_edit_rows_failed', { error: String(err) });
                    live = new Set();
                }
            }
            return this._pullResolveEditKey(raw, live);
        };
    }

    // Row KEY's share of a hide stored on an old row that is two rows now
    // (_pullEditHits): the hide is written out as one on each OTHER row,
    // so restoring one row leaves the other hidden. True when it found
    // one (and changed the store).
    _pullUnsplitHide(pos, key, positionKey) {
        const rows = (pos && pos.rows) || [];
        if (rows.some(x => x && x.key === key)) return false;
        let live = null;
        const at = rows.findIndex(x => {
            if (!x || !x.removed || !this._pullEditNeedsRows(x.key)) return false;
            if (!live) {
                try { live = this._pullPositionRowKeys(this.buildPullList(), positionKey); } catch (err) {
                    sendClientLog('pull_edit_rows_failed', { error: String(err) });
                    live = new Set();
                }
            }
            const hits = this._pullEditHits(x.key, live);
            return hits.length > 1 && hits.includes(key);
        });
        if (at < 0) return false;
        const e = rows[at];
        const others = this._pullEditHits(e.key, live).filter(h => h !== key
            && !rows.some(x => x && x.key === h));
        rows.splice(at, 1, ...others.map(h => ({ ...e, key: h })));
        return true;
    }

    // Override one field of an engine row. A value equal to the engine's
    // own clears the override for that field. `engineRow` (optional) is
    // the row as the engine says it, for that comparison. Returns true
    // when the store changed.
    setPullSheetRowEdit(positionKey, key, patch, engineRow, action = 'Edit Pull Sheet Row') {
        if (!this.project || !positionKey || !key || !patch) return false;
        const pos = this._pullPositionEdits(positionKey, true);
        let e = this._pullFindRowEdit(pos, key, positionKey);
        const storedKey = e ? e.key : key;
        const before = JSON.stringify(e ? { ...e, key } : null);
        if (!e) { e = { key }; pos.rows.push(e); }
        e.key = key;
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
        const now = after ? this._pullFindRowEdit(after, key, positionKey) : null;
        if (JSON.stringify(now || null) === before) {
            if (now) now.key = storedKey;   // nothing changed: nor does the key
            return false;
        }
        this._commitPullSheetEdit(action);
        return true;
    }

    // Hide an engine row from every paper (restorable).
    removePullSheetRow(positionKey, key) {
        if (!this.project || !positionKey || !key) return false;
        const pos = this._pullPositionEdits(positionKey, true);
        let e = this._pullFindRowEdit(pos, key, positionKey);
        if (e && e.removed) return false;
        if (!e) { e = { key }; pos.rows.push(e); }
        e.key = key;
        e.removed = true;
        this._commitPullSheetEdit('Remove Pull Sheet Row');
        return true;
    }

    restorePullSheetRow(positionKey, key) {
        const pos = this._pullPositionEdits(positionKey, false);
        if (pos && this._pullUnsplitHide(pos, key, positionKey)) {
            this._commitPullSheetEdit('Restore Pull Sheet Row');
            return true;
        }
        const e = pos && this._pullFindRowEdit(pos, key, positionKey);
        if (!e || !e.removed) return false;
        e.key = key;
        delete e.removed;
        this._commitPullSheetEdit('Restore Pull Sheet Row');
        return true;
    }

    // Forget every override on one engine row (the show's reading returns).
    resetPullSheetRow(positionKey, key) {
        const pos = this._pullPositionEdits(positionKey, false);
        if (!pos) return false;
        const split = this._pullUnsplitHide(pos, key, positionKey);
        const n = pos.rows.length + (split ? 1 : 0);
        const keyOf = this._pullStoredKeyReader(positionKey);
        pos.rows = pos.rows.filter(x => !x || keyOf(x.key) !== key);
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
        await this.pullPanelCatalogReady();
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
    // the jumper names and rev to project.pullSheet (one undo entry each),
    // the engineer to the preference. The jumper LENGTHS are per screen
    // (the Data and Power sidebars' Jumpers row, app-jumpers.js).
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
        bind('export-pull-sheet-power-jump-name-true1', 'powerJumpNameTrue1', 'Set Power Jumper Name');
        bind('export-pull-sheet-power-jump-name-powercon', 'powerJumpNamePowercon', 'Set Power Jumper Name');
        bind('export-pull-sheet-rev', 'rev', 'Set Pull Sheet Revision');
        const eng = document.getElementById('export-pull-sheet-engineer');
        if (eng) {
            eng.addEventListener('change', () => { this.setEngineerName(eng.value); });
        }
        // The show's cable unit - this section's select and the Binder
        // section's (app-cable-units.js).
        if (typeof this.initCableUnitControls === 'function') this.initCableUnitControls();
    }

    // Fields from state, and the section shown only for the pull-sheet
    // format (the picture sections mean nothing to a workbook).
    syncPullSheetControls() {
        const s = this.getPullSheetSettings();
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('export-pull-sheet-data-jump-name', s.dataJumpName);
        set('export-pull-sheet-power-jump-name-true1', s.powerJumpNameTrue1);
        set('export-pull-sheet-power-jump-name-powercon', s.powerJumpNamePowercon);
        set('export-pull-sheet-rev', s.rev);
        set('export-pull-sheet-engineer', this.getEngineerName());
        if (typeof this.syncCableUnitControls === 'function') this.syncCableUnitControls();
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
