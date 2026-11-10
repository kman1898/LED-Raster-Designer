// app-mirror-screens: feature methods for LEDRasterApp, attached to the
// prototype via the carrier class.
//
// ── Mirror a screen (owner, 2026-10-30) ──────────────────────────────────
//
// "The copy screen's port map follows the first automatically and can't be
// drawn separately." NovaStar's Copy mode is what feeds it: on an H_4xfiber
// "OPT 3 copies the output on OPT 1, while OPT 4 copies the output on OPT 2"
// (H15 Video Wall Splicer Specifications V1.15.0 p.36), on the enhanced card
// OPT 5-8 copy OPT 1-4 (p.37), and on an MX40 Pro in 20-port mode OPT 3/4
// are "the copy channel" of OPT 1/2 (User Manual V1.5.0 p.9), where each box
// there is set Mirror or Backup.
//
// ── Made by dragging (owner, 2026-11-01) ─────────────────────────────────
//
// "Mirroring is driven by the card's existing Copy setting plus dragging,
// NOT by a Screen Info picker." With a card in Copy mode (or an MX40 Pro in
// 20-port mode with a box set to Mirror) the card dropped on a first screen
// feeds it as any drop does; the SAME card dropped on a second screen makes
// that screen the first one's copy (_copyDropPlan, read by the dock's
// _dockDropCardOrBox and its preview). The copy draws no path of its own -
// its path is the source's. The screens must match (columns x rows, pixels
// per cabinet, ports in the same order), or the drop is refused with the
// server's reason (port_assignment.mirror_set_refusal). Unplugging the card
// from the source unplugs the copy too, and unplugging the copy alone just
// removes the copy - both on the server (routes_port_assignment: _store's
// mirrors_unplugged, and the unpin route on a mirror; routes_processors
// _let_mirrors_go where a Remove takes the source's feed or the copy's last
// socket), which names the mirrors it let go of in `mirrorsCleared`
// (_dropClearedMirrors). A setting that leaves a copy with nothing to ride
// (a box on Backup, the card out of Copy) keeps the mirror and its tray line,
// which names the setting and offers Stop mirroring (port_assignment
// _mirror_pass), so nobody is left with a screen they can't free.
//
// The setting is still the layer's `dataMirrorOf` (the screen it copies),
// validated by the layer PUT, so a show saved with one opens mirrored. Two
// things follow from it here:
//
//   * THE MAP IS THE SOURCE'S. Every field that decides which cabinet rides
//     which port (MIRROR_DATA_FIELDS) is copied from the source onto the
//     mirror by the server on every save of the source and on a load
//     (port_assignment.copy_mirror_maps), and on the page at every history
//     snapshot (_syncMirrorScreens, from saveState), so the canvas, the port
//     count and every export read the mirror's own layer and find the
//     source's map on it.
//   * THE MAP IS READ-ONLY on the mirror: its data-map controls are dimmed,
//     and any attempt - a control, a custom run, a fill, a placement in the
//     tray - is refused with an error naming the source (never silent, the
//     locked-screen rule's shape).
//
// Where the mirror's runs land is the server's (port_assignment's mirror
// pass): port N of the source on socket S lands port N of the mirror on the
// copy of S, and the resolution says exactly what is missing where it cannot.
//
// ── A copy takes its source's settings (owner, 2026-11-05) ───────────────
//
// A drop used to pass on shape alone, and the first history snapshot then
// turned Screen2's 30 fps into Screen1's 60 without a word: "this shouldn't
// let me mirror/copy. or better yet it should say not allowed and give me the
// option to match them if the size and shape are the same". So a drop that
// passes every other rule but differs in a setting that makes the port map
// (_mirrorSettingDifferences) says "Not allowed:" on the pill, and its
// release asks whether to match the target to the source (_mirrorMatchAsk).
// That rule holds where a mirror is SET: a mirror already made follows its
// source through _syncMirrorScreens and is never checked against it.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The fields that make a screen's data port map, copied from the source onto
// its mirror. The processing settings ride with the walk because they decide
// how many cabinets a port carries.
export const MIRROR_DATA_FIELDS = [
    'flowPattern', 'lastFlowPattern', 'portMappingMode', 'portNumberOrder',
    'customPortPaths', 'customPortIndex', 'customPortOverrides',
    'processorType', 'bitDepth', 'frameRate', 'lowLatency',
];

// The Screen Info controls that edit the data port map. On a mirror they
// are dimmed and any attempt on them is refused with the mirror's error.
const MIRROR_LOCKED_CONTROLS = [
    '#processor-type', '#bit-depth', '#frame-rate', '#mapping-organized',
    '#mapping-max-capacity', '#port-number-across', '#port-number-down',
    '#low-latency', '.flow-pattern-btn',
    '#custom-flow-toggle', '#custom-active-port-input', '#custom-prev-port',
    '#custom-next-port', '#custom-clear-port', '#custom-clear-all',
    '#custom-clear-selection',
].join(', ');

// A flow pattern's start corner, in its button's tooltip's words.
const MIRROR_FLOW_CORNERS = {
    tl: 'Top-left', tr: 'Top-right', bl: 'Bottom-left', br: 'Bottom-right',
};

class _MirrorScreens {
    // The screen `layer` mirrors, or null: a screen layer of this project
    // other than itself. A stale id (its source deleted) reads as null here
    // and is said in Screen Info from the resolution's issue.
    mirrorSourceOf(layer) {
        if (!layer || layer.dataMirrorOf === undefined
                || layer.dataMirrorOf === null || layer.dataMirrorOf === '') {
            return null;
        }
        const id = String(layer.dataMirrorOf);
        const src = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === id);
        if (!src || src === layer || (src.type || 'screen') !== 'screen') return null;
        return src;
    }

    // The ids of every screen that is a mirror or is mirrored, as strings.
    _mirrorPairIds() {
        const ids = new Set();
        ((this.project && this.project.layers) || []).forEach(l => {
            if (l.dataMirrorOf === undefined || l.dataMirrorOf === null
                    || l.dataMirrorOf === '') return;
            ids.add(String(l.id));
            ids.add(String(l.dataMirrorOf));
        });
        return ids;
    }

    // What the server's match rule compares (port_assignment.mirror_shape):
    // columns x rows, the pixels per cabinet, the half-tile edges, the
    // cabinets that walk differently (blank, hidden, half tiles, by row and
    // column) and whether a custom run crosses onto another screen. Sent
    // with the resolve for the screens of a mirror only (_assignmentScreens),
    // so it is also in the panel's key: a resize of either screen re-runs
    // the check (1.6.0 QA - it ran only when the mirror was made, and a
    // later resize was taken silently), and no other edit asks the server
    // anything new.
    _mirrorShape(layer) {
        const marks = [];
        (layer.panels || []).forEach(p => {
            if (!p) return;
            const half = p.halfTile || 'none';
            if (!p.blank && !p.hidden && half === 'none') return;
            marks.push([p.row, p.col, !!p.blank, !!p.hidden, half]);
        });
        marks.sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]));
        const paths = layer.customPortPaths;
        const crossRuns = !!paths && typeof paths === 'object'
            && Object.values(paths).some(entries => (entries || []).some(e =>
                e && e.layerId !== undefined && e.layerId !== null
                && e.layerId !== '' && String(e.layerId) !== String(layer.id)));
        return {
            columns: layer.columns, rows: layer.rows,
            cabinetWidth: layer.cabinet_width, cabinetHeight: layer.cabinet_height,
            halves: ['halfFirstColumn', 'halfLastColumn', 'halfFirstRow',
                     'halfLastRow'].map(k => !!layer[k]),
            marks,
            crossRuns,
        };
    }

    // A mirror that an edit broke (its screens stopped matching) is said
    // once, out loud, in the server's words: which screens and why. The
    // resolution's 'mirror-mismatch' issue is the standing warning in the
    // tray, and it goes when the screens match again. Nothing is said for
    // the first resolution of a project (a file opened, an undo or redo):
    // that is not an edit breaking it, and the tray already shows it.
    _noteMirrorBreaks() {
        const issues = ((this._assignment && this._assignment.issues) || [])
            .filter(i => i && i.kind === 'mirror-mismatch');
        const now = new Set(issues.map(i => String(i.layerId)));
        const before = this._mirrorBrokenIds;
        const sameProject = this._mirrorBrokenProject === this.project;
        this._mirrorBrokenIds = now;
        this._mirrorBrokenProject = this.project;
        if (!before || !sameProject) return [];
        const fresh = issues.filter(i => !before.has(String(i.layerId)));
        if (!fresh.length) return [];
        if (typeof this._toast === 'function') {
            this._toast(fresh.map(i => i.message).join(' '), true, 8000);
        }
        sendClientLog('mirror_screen_mismatched', {
            layerIds: fresh.map(i => i.layerId),
            messages: fresh.map(i => i.message),
        });
        return fresh;
    }

    // Copy the source's data map onto every mirror (MIRROR_DATA_FIELDS) on
    // this page. Called from saveState, so the snapshot and the canvas
    // carry the copied map. Returns the mirrors it changed. Nothing is
    // sent (2026-11-10): the SERVER copies a source's map onto its mirror
    // whenever the source is saved, and when a show is loaded or restored
    // (port_assignment.copy_mirror_maps, the same fields), and tells every
    // page. Until then each page wrote the copy itself, the one that
    // changed the source only (a following page writes nothing, app-core
    // FOLLOWING), so a mirror stored out of date stayed so until a page
    // edited the show again, and every source edit sent a second save.
    _syncMirrorScreens() {
        const layers = (this.project && this.project.layers) || [];
        const wrote = [];
        layers.forEach(layer => {
            const src = this.mirrorSourceOf(layer);
            if (!src || src.dataMirrorOf) return;
            const body = this._takeMirrorFields(layer, src);
            if (Object.keys(body).length) wrote.push(layer);
        });
        if (wrote.length) {
            sendClientLog('mirror_screens_synced',
                          { layerIds: wrote.map(l => l.id) });
        }
        return wrote;
    }

    // `layer` takes `src`'s MIRROR_DATA_FIELDS. Returns the PUT body of the
    // fields that changed. A field the source lacks goes as null, and the
    // server stores that null and echoes it, so a null here is the same
    // blank as no field, or each snapshot would write it again.
    _takeMirrorFields(layer, src) {
        const body = {};
        const blank = (v) => (v === undefined ? null : v);
        MIRROR_DATA_FIELDS.forEach(k => {
            const want = src[k] === undefined ? undefined
                : JSON.parse(JSON.stringify(src[k]));
            if (JSON.stringify(blank(layer[k])) === JSON.stringify(blank(want))) return;
            if (want === undefined) delete layer[k];
            else layer[k] = want;
            body[k] = want === undefined ? null : want;
        });
        return body;
    }

    // The error a change to a mirror's data map says, naming the source and
    // the way back (owner, 2026-11-01): unplug the card from the copy. A
    // mirror with nothing plugged in has nothing to unplug, so it says the
    // way there is: the tray's Stop mirroring (port_assignment _mirror_pass,
    // and the server's mirror_refusal in the same words).
    _mirrorErrorText(layer) {
        const src = this.mirrorSourceOf(layer);
        const name = layer.name || `Screen ${layer.id}`;
        const from = src ? (src.name || `Screen ${src.id}`) : 'another screen';
        const head = `${name} mirrors ${from}. Its data port map follows `
            + `${from}'s and cannot be changed on its own. `;
        if (this._mirrorPluggedIn(layer) === false) {
            return `${head}Nothing is plugged into ${name} to unplug: press `
                + 'Stop mirroring on its line in the tray.';
        }
        return `${head}Change it on ${from}, or unplug the `
            + `${this._mirrorUnitWord(layer)} from ${name} to stop mirroring.`;
    }

    // Whether any of a mirror's ports landed on a socket (the resolution's
    // own answer), null where no resolution has said yet.
    _mirrorPluggedIn(layer) {
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(layer.id));
        return scr ? (scr.ports || []).some(p => p.cardId) : null;
    }

    // 'card' or 'processor': what feeds a mirror (the unit its first
    // landed port is on, else its source's), for "unplug the card".
    _mirrorUnitWord(layer) {
        const screens = (this._assignment && this._assignment.screens) || [];
        const src = this.mirrorSourceOf(layer);
        const ids = [layer, src].filter(Boolean).map(l => String(l.id));
        let cardId = null;
        ids.some(id => {
            const scr = screens.find(s => s.layerId === id);
            const port = scr && (scr.ports || []).find(p => p.cardId);
            if (port) cardId = port.cardId;
            return !!cardId;
        });
        if (!cardId || typeof this.unitWordForCard !== 'function') return 'card';
        return this.unitWordForCard(cardId) === 'card' ? 'card' : 'processor';
    }

    // True (and the error said) when any of `layers` mirrors a screen: for
    // a data-map change that must not reach a mirror.
    _mirrorRefused(layers) {
        const list = (Array.isArray(layers) ? layers : [layers]).filter(Boolean);
        const hit = list.find(l => this.mirrorSourceOf(l));
        if (!hit) return false;
        if (typeof this._toast === 'function') {
            this._toast(this._mirrorErrorText(hit), true, 6000);
        }
        sendClientLog('mirror_edit_refused', { layerId: hit.id });
        return true;
    }

    // The dimmed map controls while the shown screen is a mirror, refreshed
    // with the rest of the data settings (updatePortCapacityDisplay). The
    // Screen Info pick that used to sit here is gone (owner, 2026-11-01):
    // a mirror is made by dragging a card in Copy mode (_copyDropPlan).
    updateMirrorDataLock() {
        this._wireMirrorDataGuard();
        const layer = this.currentLayer;
        const isScreen = !!layer && (layer.type || 'screen') === 'screen';
        this._dimMirrorControls(isScreen && !!this.mirrorSourceOf(layer));
    }

    _dimMirrorControls(on) {
        // Only what this dimmed is put back, to the opacity it had: other
        // code owns these controls' look (the Port Mapping buttons' '1').
        document.querySelectorAll(MIRROR_LOCKED_CONTROLS).forEach(el => {
            if (on) {
                if (el.dataset.mirrorLocked === undefined) {
                    el.dataset.mirrorLocked = el.style.opacity || '';
                }
                el.style.opacity = '0.45';
            } else if (el.dataset.mirrorLocked !== undefined) {
                el.style.opacity = el.dataset.mirrorLocked;
                delete el.dataset.mirrorLocked;
            }
        });
    }

    _wireMirrorDataGuard() {
        if (this._mirrorGuardWired) return;
        this._mirrorGuardWired = true;
        // Every attempt on a mirror's data-map controls is refused out
        // loud, before the control's own handler runs.
        const guard = (e) => {
            const el = e.target && e.target.closest
                ? e.target.closest(MIRROR_LOCKED_CONTROLS) : null;
            if (!el || !this.currentLayer
                    || !this.mirrorSourceOf(this.currentLayer)) return;
            if (e.type === 'keydown' && ['Tab', 'Shift', 'Escape']
                .includes(e.key)) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (e.type !== 'mousedown') this._mirrorRefused(this.currentLayer);
        };
        ['mousedown', 'click', 'keydown', 'change'].forEach(type =>
            document.addEventListener(type, guard, true));
    }

    // ── the drag that makes a mirror (owner, 2026-11-01) ─────────────────

    // Whether a card's current mode feeds a mirror screen: Copy on the
    // H_4xfiber and its enhanced card (copyTrunks 'mirror'), or the MX40
    // Pro's 20-port mode with at least one copy box set to Mirror
    // ('per-box'; with every copy box on Backup, the copies are backups and
    // the card drops as it always did). Read off the resolved card, which
    // reads the catalog's mode - no other product is in Copy.
    _cardFeedsMirror(cardId) {
        const found = typeof this._dockFindCard === 'function'
            ? this._dockFindCard(cardId) : null;
        const card = found && found.card;
        if (!card) return false;
        if (card.copyTrunks === 'mirror') return true;
        return card.copyTrunks === 'per-box'
            && (card.copyTrunkList || []).some(t => t && t.role === 'mirror');
    }

    // THE ONE DECISION the dock's preview and its release both read for a
    // whole-card or whole-box drop on a screen (preview == result): does
    // this drop make a mirror? Null where it does not - a box that is not a
    // mirror box, a card not in Copy, a card with no screen on it yet, a
    // drop on a screen the card already feeds - and the drop goes on as any
    // card or box drop. Otherwise
    //   { ok: true, sourceId, sourceName, nums, text } - the screen becomes
    //       the copy of `sourceId`, the first screen on the card;
    //   { ok: false, message } - said, and nothing changes;
    //   { ok: false, message, match: true, sourceId, differences } - a copy
    //       but for its settings: the release offers to match them.
    // The first screen is the one on the card's lowest socket that has no
    // copy yet (a screen has one mirror, on the copy outputs); where every
    // screen on the card already has one, the first of them, so the
    // "already mirrors" refusal is what is said.
    //
    // A BOX SET TO MIRROR IS THE COPY (owner, 2026-11-04: "breakout is the
    // only way mirror works aka copy"): a box whose every socket copies a
    // primary socket (resolve_card's mirrorOf - a box on a copy OPT set to
    // Mirror, or any box on the copy OPTs of a card in Copy mode) dropped on
    // a screen makes that screen the copy of the screen on the sockets it
    // copies (_mirrorBoxDropPlan). Its run lands on the box's sockets.
    //
    // THE PILL TELLS THE TRUTH (owner, 2026-11-04): every refusal the
    // release would meet is decided here, before the drop - a locked
    // screen, a mismatch, a second mirror (_mirrorDropRefusal, the
    // server's mirror_set_refusal in the same words) - so a pill that
    // says "Copy of" is a drop that lands.
    _copyDropPlan(unit, layerId) {
        if (!unit || !unit.cardId) return null;
        if (unit.type === 'box') return this._mirrorBoxDropPlan(unit, layerId);
        if (unit.type !== 'card') return null;
        if (!this._cardFeedsMirror(unit.cardId)) {
            return this._copyDropHint(unit, layerId);
        }
        const screens = (this._assignment && this._assignment.screens) || [];
        const target = screens.find(s => s.layerId === String(layerId));
        if (!target) return null;
        const own = (s) => (s.ports || []).filter(p => p.cardId
            && p.source !== 'mirror');
        if (own(target).some(p => p.cardId === unit.cardId)) return null;
        const firstSocket = (s) => Math.min(...own(s)
            .filter(p => p.cardId === unit.cardId).map(p => Number(p.port)));
        const sources = screens
            .filter(s => s.layerId !== target.layerId && !s.mirrorOf
                && own(s).some(p => p.cardId === unit.cardId))
            .sort((a, b) => firstSocket(a) - firstSocket(b));
        if (!sources.length) return null;
        const name = target.name;
        const layer = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === target.layerId);
        const already = sources.find(s => layer
            && String(layer.dataMirrorOf) === s.layerId);
        if (already) {
            return { ok: false,
                     message: `${name} already mirrors ${already.name}.` };
        }
        if (own(target).length) {
            const word = typeof this.showUnitWord === 'function'
                ? this.showUnitWord() : 'card';
            return { ok: false,
                     message: `${name} already has ports on a ${word}. Clear `
                        + 'them first, then drag the card onto it again to '
                        + 'make it a copy.' };
        }
        const source = sources.find(s => !screens.some(m =>
            m.mirrorOf === s.layerId)) || sources[0];
        // A COPY NEEDS SOMEWHERE TO PLUG IN: every socket the source takes
        // on this card needs a copy socket on a box set to Mirror. An MX40
        // Pro with the box on OPT 3 at Backup and OPT 4 at Mirror feeds no
        // mirror of a screen on OPT 1 - refused here, out loud, the way the
        // other mirror refusals are, instead of making a mirror whose ports
        // have nowhere to go.
        const why = this._copyDropUnfed(unit.cardId, own(source)
            .filter(p => p.cardId === unit.cardId).map(p => Number(p.port)));
        if (why) {
            return { ok: false,
                     message: `${name} can't mirror ${source.name}: ${why}.` };
        }
        return this._copyDropFinish(layer, target, source);
    }

    // The last word on a copy drop, shared by the card and the box: the
    // target's lock, then every rule the server's mirror_set_refusal holds
    // (_mirrorDropRefusal), then the settings, which alone are offered a
    // way through, so a locked screen or a size mismatch never gets the
    // offer. Ok lights the whole screen and says whose copy.
    _copyDropFinish(layer, target, source) {
        if (layer && typeof this._layerLocked === 'function'
                && this._layerLocked(layer)) {
            return { ok: false, locked: true,
                     message: `${target.name} is locked. Unlock it to change it.` };
        }
        const srcLayer = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === String(source.layerId));
        const refusal = layer && srcLayer
            ? this._mirrorDropRefusal(layer, srcLayer) : null;
        if (refusal) return { ok: false, loud: true, message: refusal };
        const differences = layer && srcLayer
            ? this._mirrorSettingDifferences(srcLayer, layer) : [];
        if (differences.length) {
            return { ok: false, match: true, sourceId: source.layerId,
                     differences, message: `Not allowed: ${differences[0]}` };
        }
        const nums = [];
        for (let n = 1; n <= (target.required || 0); n++) nums.push(n);
        return { ok: true, sourceId: source.layerId, sourceName: source.name,
                 nums, text: `Copy of ${source.name}` };
    }

    // A box dropped on a screen, as a copy: null where the box is not a
    // mirror box (a primary box, a backup box, a box straddling a main OPT
    // and its copy) and the drop goes on as any box drop. Otherwise the
    // plan the card's copy drop returns: the screen on the sockets this box
    // copies is the source, the lowest of them first that has no copy yet.
    _mirrorBoxDropPlan(unit, layerId) {
        const found = typeof this._dockFindCard === 'function'
            ? this._dockFindCard(unit.cardId) : null;
        const card = found && found.card;
        if (!card) return null;
        const box = (card.cvts || []).find(b => b.id === unit.boxId);
        if (!box) return null;
        const mine = (card.ports || []).filter(p => p.cvtId === box.id);
        if (!mine.length || !mine.every(p => p.mirrorOf)) return null;
        const screens = (this._assignment && this._assignment.screens) || [];
        const target = screens.find(s => s.layerId === String(layerId));
        if (!target) return null;
        const boxName = box.displayTitle || unit.title || 'This box';
        const primaries = new Set(mine.map(p => Number(p.mirrorOf)));
        // What the box copies, by the names on the rack: the boxes that
        // deliver those sockets, else the unit's own port numbers.
        const lowest = Math.min(...primaries);
        const highest = Math.max(...primaries);
        const fromBoxes = (card.cvts || []).filter(b => b.id !== box.id
            && !b.copyRole && (card.ports || []).some(p => p.cvtId === b.id
                && primaries.has(Number(p.number))));
        const unitTitle = unit.cardTitle || card.deviceName || 'the processor';
        const copied = fromBoxes.length
            ? fromBoxes.map(b => b.displayTitle).join(' and ')
            : `${unitTitle} ports ${lowest}-${highest}`;
        const own = (s) => (s.ports || []).filter(p => p.cardId
            && p.source !== 'mirror');
        const onCopied = (s) => own(s).filter(p => p.cardId === unit.cardId
            && primaries.has(Number(p.port)));
        const name = target.name;
        if (onCopied(target).length) {
            return { ok: false,
                     message: `${name} is on ${copied}. Drag ${boxName} onto `
                        + `the screen that should copy ${name}.` };
        }
        const firstSocket = (s) => Math.min(...onCopied(s).map(p => Number(p.port)));
        const sources = screens
            .filter(s => s.layerId !== target.layerId && !s.mirrorOf
                && onCopied(s).length)
            .sort((a, b) => firstSocket(a) - firstSocket(b));
        if (!sources.length) {
            return { ok: false,
                     message: `Put a screen on ${copied} first. Then drag `
                        + `${boxName} onto the screen that should copy it.` };
        }
        const layer = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === target.layerId);
        const already = sources.find(s => layer
            && String(layer.dataMirrorOf) === s.layerId);
        if (already) {
            return { ok: false,
                     message: `${name} already mirrors ${already.name}.` };
        }
        if (own(target).length) {
            const word = typeof this.showUnitWord === 'function'
                ? this.showUnitWord() : 'card';
            return { ok: false,
                     message: `${name} already has ports on a ${word}. Clear `
                        + `them first, then drag ${boxName} onto it again to `
                        + 'make it a copy.' };
        }
        const source = sources.find(s => !screens.some(m =>
            m.mirrorOf === s.layerId)) || sources[0];
        // Every socket the source takes on this unit needs a copy socket:
        // a source on A-B and on another box this one does not copy has
        // ports with nowhere to land (the card drop's own check).
        const why = this._copyDropUnfed(unit.cardId, own(source)
            .filter(p => p.cardId === unit.cardId).map(p => Number(p.port)));
        if (why) {
            return { ok: false,
                     message: `${name} can't mirror ${source.name}: ${why}.` };
        }
        return this._copyDropFinish(layer, target, source);
    }

    // Why `layer` may not mirror `source` (both project layers), or null:
    // the rules of the server's mirror_set_refusal and mirror_mismatch
    // (port_assignment.py), in the same words, read off the screens as the
    // person sees them (_mirrorShape) so the drag's pill can say it before
    // the drop. The release still asks the server (setLayerMirror), which
    // stays the authority.
    _mirrorDropRefusal(layer, source) {
        const name = layer.name || `Screen ${layer.id}`;
        const srcName = source.name || `Screen ${source.id}`;
        if (String(source.id) === String(layer.id)) {
            return `${name} cannot mirror itself.`;
        }
        if (source.dataMirrorOf !== undefined && source.dataMirrorOf !== null
                && source.dataMirrorOf !== '') {
            return `${srcName} mirrors another screen itself. Set ${name} to `
                + `mirror the screen ${srcName} copies.`;
        }
        const layers = (this.project && this.project.layers) || [];
        const copiedBy = layers.find(l => l !== layer
            && String(l.dataMirrorOf) === String(layer.id));
        if (copiedBy) {
            return `${copiedBy.name || 'Another screen'} mirrors ${name}, so `
                + `${name} cannot mirror another screen.`;
        }
        const why = this._mirrorMismatchText(source, layer);
        if (why) return why;
        const rival = layers.find(l => l !== layer
            && String(l.dataMirrorOf) === String(source.id));
        if (rival) {
            return `${rival.name || 'Another screen'} already mirrors `
                + `${srcName}. A screen has one mirror, on its copy outputs.`;
        }
        if (typeof this._autoCrossMembers === 'function') {
            for (const one of [layer, source]) {
                if (!this._autoCrossMembers(one, 'data')) continue;
                const group = typeof this.getGroupOfLayer === 'function'
                    ? this.getGroupOfLayer(one) : null;
                return `${one.name || 'That screen'} routes its data as one `
                    + `screen with the group ${group ? (group.name || group.id) : ''}. `
                    + 'Turn off Route group as one screen first.';
            }
        }
        return null;
    }

    // The server's mirror_mismatch, off the client's _mirrorShape.
    _mirrorMismatchText(source, mirror) {
        const a = this._mirrorShape(source);
        const b = this._mirrorShape(mirror);
        const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : v);
        const aName = source.name || `Screen ${source.id}`;
        const bName = mirror.name || `Screen ${mirror.id}`;
        const tail = 'A mirror screen must match the screen it copies.';
        if (n(a.columns) !== n(b.columns) || n(a.rows) !== n(b.rows)) {
            return `${bName} is ${n(b.columns)} x ${n(b.rows)} cabinets and `
                + `${aName} is ${n(a.columns)} x ${n(a.rows)}. ${tail}`;
        }
        if (n(a.cabinetWidth) !== n(b.cabinetWidth)
                || n(a.cabinetHeight) !== n(b.cabinetHeight)) {
            return `${bName}'s cabinets are ${n(b.cabinetWidth)} x `
                + `${n(b.cabinetHeight)} px and ${aName}'s are `
                + `${n(a.cabinetWidth)} x ${n(a.cabinetHeight)} px. ${tail}`;
        }
        if (JSON.stringify(a.halves) !== JSON.stringify(b.halves)
                || JSON.stringify(a.marks) !== JSON.stringify(b.marks)) {
            return `${bName} and ${aName} have different blank, hidden or `
                + 'half cabinets, so their ports would not run in the same '
                + `order. ${tail}`;
        }
        if (a.crossRuns) {
            return `${aName}'s custom runs cross onto another screen. A `
                + 'mirror screen copies a screen whose runs stay on it.';
        }
        return null;
    }

    // A flow pattern as its button's tooltip says it (port_assignment
    // _mirror_flow_words).
    _mirrorFlowWords(flow) {
        if (flow === 'custom') return 'Custom';
        const [corner, axis, z] = String(flow).split('-');
        if (!MIRROR_FLOW_CORNERS[corner] || !axis) return String(flow);
        const vertical = axis === 'v';
        const words = `${MIRROR_FLOW_CORNERS[corner]}, `
            + `${vertical ? 'vertical' : 'horizontal'} first`;
        if (!z) return words;
        if (vertical) {
            return `${words}, every column starts at the `
                + `${corner[0] === 't' ? 'top' : 'bottom'}`;
        }
        return `${words}, every row starts at the `
            + `${corner[1] === 'l' ? 'left' : 'right'}`;
    }

    // The drawn runs the walk really reads, as {port: steps} (port_assignment
    // _mirror_runs). Whole-screen custom walks every drawn path and ignores
    // the overrides; an automatic screen walks only the numbers in
    // customPortOverrides (an empty one still holds its number). Every
    // other path is left over from a custom spell and read by nothing. A
    // step is [row, col, the peer it names], its own screen read as no
    // peer, so two screens' runs compare.
    _mirrorRuns(layer) {
        const stored = layer.customPortPaths;
        const paths = stored && typeof stored === 'object' ? stored : {};
        const own = String(layer.id);
        const steps = (path) => (Array.isArray(path) ? path : [])
            .filter(s => s && typeof s === 'object')
            .map(s => {
                const peer = s.layerId;
                const none = peer === undefined || peer === null || peer === ''
                    || String(peer) === own;
                return [Number(s.row), Number(s.col), none ? null : String(peer)];
            });
        const runs = {};
        if (!this.isCustomFlow(layer)) {
            this.getOverrideNums(layer, 'data').forEach(n => {
                runs[n] = steps(paths[n]);
            });
            return runs;
        }
        Object.keys(paths).forEach(key => {
            const n = Number(key);
            const run = steps(paths[key]);
            if (Number.isInteger(n) && n >= 1 && run.length) runs[n] = run;
        });
        return runs;
    }

    // What the port walk reads off a screen, each blank read as the walk
    // reads it (port_assignment.mirror_settings): no processor is NovaStar
    // (Legacy), no bit depth 8, no frame rate 60, no flow 'tl-h', no mapping
    // Organized, no Low Latency off, and no port number order the one along
    // the pattern's lines. lastFlowPattern and customPortIndex are not
    // here: a memory and a cursor, not the map.
    _mirrorSettings(layer) {
        return {
            processor: layer.processorType || 'novastar-armor',
            bitDepth: Number(layer.bitDepth) || 8,
            frameRate: Number(layer.frameRate) || 60,
            lowLatency: !!layer.lowLatency,
            mapping: (layer.portMappingMode || 'organized') === 'organized'
                ? 'organized' : 'max-capacity',
            flow: layer.flowPattern || 'tl-h',
            order: this.portNumberOrderOf(layer),
            runs: this._mirrorRuns(layer),
        };
    }

    // The Processing dropdown's own name for a processor.
    _mirrorProcessorWords(processor) {
        const select = document.getElementById('processor-type');
        const option = select && Array.from(select.options)
            .find(o => o.value === processor);
        return option ? option.textContent.trim() : processor;
    }

    // Every setting of `mirror` that would have to change to copy `source`
    // (both project layers), each a sentence with both values, in Screen
    // Info's order; empty where they agree. The server's
    // mirror_setting_differences, in the same words. The port number order
    // counts only between two Organized automatic screens, and only where
    // the switch changes something on one of them: its row is hidden
    // everywhere else, and nothing moves.
    _mirrorSettingDifferences(source, mirror) {
        const a = this._mirrorSettings(source);
        const b = this._mirrorSettings(mirror);
        const aName = source.name || `Screen ${source.id}`;
        const bName = mirror.name || `Screen ${mirror.id}`;
        const onOff = (v) => (v ? 'on' : 'off');
        const out = [];
        if (a.processor !== b.processor) {
            out.push(`${bName} is on ${this._mirrorProcessorWords(b.processor)} `
                + `and ${aName} is on ${this._mirrorProcessorWords(a.processor)}`);
        }
        if (a.bitDepth !== b.bitDepth) {
            out.push(`${bName} is ${b.bitDepth}-bit and ${aName} is `
                + `${a.bitDepth}-bit`);
        }
        if (a.frameRate !== b.frameRate) {
            out.push(`${bName} runs at ${b.frameRate} fps and ${aName} at `
                + `${a.frameRate}`);
        }
        if (a.lowLatency !== b.lowLatency) {
            out.push(`${bName} has Low Latency ${onOff(b.lowLatency)} and `
                + `${aName} has it ${onOff(a.lowLatency)}`);
        }
        if (a.mapping !== b.mapping) {
            const words = { organized: 'Organized', 'max-capacity': 'Max Capacity' };
            out.push(`${bName}'s Port Mapping is ${words[b.mapping]} and `
                + `${aName}'s is ${words[a.mapping]}`);
        }
        if (a.flow !== b.flow) {
            out.push(`${bName}'s data flow is ${this._mirrorFlowWords(b.flow)} `
                + `and ${aName}'s is ${this._mirrorFlowWords(a.flow)}`);
        }
        if (a.flow !== 'custom' && b.flow !== 'custom'
                && a.mapping === 'organized' && b.mapping === 'organized'
                && a.order !== b.order
                && (this.portNumberOrderMatters(source)
                    || this.portNumberOrderMatters(mirror))) {
            const word = (o) => (o === 'down' ? 'Down' : 'Across');
            out.push(`${bName}'s port numbers run ${word(b.order)} and `
                + `${aName}'s run ${word(a.order)}`);
        }
        if (JSON.stringify(a.runs) !== JSON.stringify(b.runs)) {
            const count = (n) => (n ? `${n} custom run${n === 1 ? '' : 's'}`
                : 'no custom runs');
            const aN = Object.keys(a.runs).length;
            const bN = Object.keys(b.runs).length;
            out.push(aN === bN
                ? `${bName} and ${aName} have different custom runs`
                : `${bName} has ${count(bN)} and ${aName} has ${count(aN)}`);
        }
        return out;
    }

    // A FULL CARD THAT COULD FEED A MIRROR, SAID WITH THE WAY TO DO IT
    // (beta.4 QA: a copy box on Backup - an MCTRL R5's, a VX600 Pro in
    // Backup - refused the second screen with only "has no free ports").
    // A card whose copy output is set to back up rather than to copy, with
    // a screen already on it and no free port left, dropped on a screen
    // with no ports: the drop could only be a mirror, so the refusal says
    // how to make one - the unit's Copy mode where its mode is the switch
    // (copyTrunks 'backup' with a 'mirror' mode beside it), else the box
    // on the copy output set to Mirror (or a box put there). Null in every
    // other case, and the drop goes on as any card drop.
    _copyDropHint(unit, layerId) {
        const found = typeof this._dockFindCard === 'function'
            ? this._dockFindCard(unit.cardId) : null;
        const card = found && found.card;
        if (!card) return null;
        const copyMode = (card.modes || []).find(m => m.copyTrunks === 'mirror');
        let how = '';
        if (card.copyTrunks === 'backup' && copyMode) {
            how = `switch ${unit.title} to ${copyMode.label || 'Copy'} mode`;
        } else if (card.copyTrunks === 'per-box') {
            const entry = (card.copyTrunkList || [])[0];
            if (!entry) return null;
            how = entry.boxId
                ? `set the box on ${entry.trunkTitle} to Mirror`
                : `put a box on ${entry.trunkTitle} and set it to Mirror`;
        } else {
            return null;
        }
        const summary = ((this._assignment && this._assignment.cards) || [])
            .find(c => c.cardId === unit.cardId);
        if (!summary || summary.free !== 0) return null;
        const screens = (this._assignment && this._assignment.screens) || [];
        const target = screens.find(s => s.layerId === String(layerId));
        if (!target) return null;
        const own = (s) => (s.ports || []).filter(p => p.cardId
            && p.source !== 'mirror');
        if (own(target).length) return null;
        const source = screens.find(s => s.layerId !== target.layerId
            && own(s).some(p => p.cardId === unit.cardId));
        if (!source) return null;
        return { ok: false,
                 message: `${unit.title} has no free ports. To make `
                    + `${target.name} a copy of ${source.name}, ${how}.` };
    }

    // Why the copies of these card sockets give a mirror nowhere to plug
    // in, or '' where each has a copy socket (a resolved port whose
    // mirrorOf is that socket). Said by what is missing on the copy OPT
    // that copies the socket's OPT (the resolved copyTrunkList), the words
    // the server's mirror-unfed issue uses (port_assignment
    // _mirror_missing).
    _copyDropUnfed(cardId, sockets) {
        const found = typeof this._dockFindCard === 'function'
            ? this._dockFindCard(cardId) : null;
        const card = found && found.card;
        if (!card) return '';
        const copied = new Set((card.ports || []).filter(p => p.mirrorOf)
            .map(p => p.mirrorOf));
        const port = sockets.find(n => !copied.has(n));
        if (port == null) return '';
        const per = card.portsPerTrunk || 0;
        const block = per ? Math.floor((port - 1) / per) : 0;
        const entry = (card.copyTrunkList || []).find(t => t && t.copiesTrunk === block);
        if (!entry) return 'no copy output carries those ports';
        if (!entry.boxId) return `${entry.trunkTitle} has no box (it copies ${entry.copiesTitle})`;
        if (entry.role !== 'mirror') {
            return `the box on ${entry.trunkTitle} is set to Backup. Set it to Mirror `
                + 'to feed a mirror screen';
        }
        return `the box on ${entry.trunkTitle} has no socket copying those ports`;
    }

    // The release of a copy plan: the screen is set to mirror the source
    // through the validated layer PUT (setLayerMirror), so a mismatch, a
    // copy of a copy, a second copy of one screen or a screen routed with
    // its group is refused in the server's words, out loud.
    _dockDropMirror(target, plan) {
        const layer = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === String(target.layerId));
        if (!layer) return Promise.resolve(false);
        if (plan.match) return this._mirrorMatchAsk(layer, plan);
        if (!plan.ok) {
            // The pill said it before the drop; the release says it once
            // more where it stays: a locked screen in the locked error
            // (the locked-screens rule), a broken rule in the red toast
            // the server's refusal always wore, anything else in the
            // status bar.
            if (plan.locked && typeof this._lockedRefused === 'function') {
                this._lockedRefused(layer);
            } else if (plan.loud && typeof this._toast === 'function') {
                this._toast(plan.message, true, 6000);
            }
            if (!plan.locked && typeof this._dockSay === 'function') {
                this._dockSay(plan.message);
            }
            sendClientLog('mirror_screen_drop_refused', { layerId: layer.id,
                                                          error: plan.message });
            return Promise.resolve(false);
        }
        sendClientLog('mirror_screen_drop', { layerId: layer.id,
                                              mirrorOf: plan.sourceId });
        return this.setLayerMirror(layer, plan.sourceId);
    }

    // The release of a drop that differs only in its settings: every
    // difference, and the choice. Cancel changes nothing.
    _mirrorMatchAsk(layer, plan) {
        const source = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === String(plan.sourceId));
        if (!source) return Promise.resolve(false);
        const name = layer.name || `Screen ${layer.id}`;
        const from = source.name || `Screen ${source.id}`;
        sendClientLog('mirror_screen_drop_differs', {
            layerId: layer.id, mirrorOf: plan.sourceId,
            differences: plan.differences,
        });
        return this.appConfirm(`${name} can't mirror ${from} while their `
            + `settings differ:\n\n${plan.differences.join('\n')}\n\nMatching `
            + `gives ${name} the settings of ${from}, then makes it the copy.`,
        { id: 'mirror-match-modal', title: 'Not allowed',
          okLabel: `Match ${name} to ${from}` })
            .then(yes => {
                sendClientLog(yes ? 'mirror_screen_match' : 'mirror_screen_match_cancelled',
                              { layerId: layer.id, mirrorOf: plan.sourceId });
                return yes ? this._mirrorMatchTo(layer, source) : false;
            });
    }

    // Match: `layer` takes `source`'s settings, and then the mirror is made
    // through setLayerMirror, the server seeing them equal. Nothing here
    // writes history: setLayerMirror's one step holds both, so one undo
    // takes back the mirror and the settings. A snapshot still waiting
    // lands first, or it would take the matched settings in with the edit
    // before them, and the undo would have nothing to go back to. A refusal
    // after all (nothing else the page knew of) puts the settings back.
    _mirrorMatchTo(layer, source) {
        if (typeof this._flushPendingSaveState === 'function') {
            this._flushPendingSaveState();
        }
        const kept = Object.fromEntries(MIRROR_DATA_FIELDS.map(k => [k, layer[k]]));
        const body = this._takeMirrorFields(layer, source);
        const putBack = () => {
            const back = this._takeMirrorFields(this._liveLayer(layer), kept);
            if (Object.keys(back).length) this._putLayer(layer.id, back);
            if (typeof this.loadLayerToInputs === 'function') this.loadLayerToInputs();
            return false;
        };
        return this._putLayer(layer.id, body)
            .then(r => {
                if (!r.ok) throw new Error(`settings PUT answered ${r.status}`);
                return this.setLayerMirror(this._liveLayer(layer), source.id);
            })
            .then(done => {
                if (!done) return putBack();
                // Screen Info still shows what the screen had.
                if (typeof this.loadLayerToInputs === 'function') this.loadLayerToInputs();
                return true;
            })
            .catch(err => {
                sendClientLog('mirror_screen_match_failed',
                              { layerId: layer.id, error: String(err) });
                return putBack();
            });
    }

    // The mirrors the server let go of with an edit to the pins (the copy
    // unplugged, or its source unplugged from the card that fed it -
    // routes_port_assignment's `mirrorsCleared`): off this copy of the
    // layers too, before the history snapshot takes them.
    _dropClearedMirrors(ids) {
        const gone = new Set((ids || []).map(String));
        if (!gone.size) return [];
        const layers = ((this.project && this.project.layers) || [])
            .filter(l => gone.has(String(l.id)));
        layers.forEach(l => { delete l.dataMirrorOf; });
        if (layers.length) {
            sendClientLog('mirror_screens_unplugged',
                          { layerIds: layers.map(l => l.id) });
            if (typeof this.updateMirrorDataLock === 'function') {
                this.updateMirrorDataLock();
            }
        }
        return layers;
    }

    // Set (sourceId) or clear (null) the screen `layer` mirrors. The server
    // validates and answers 409 with the reason where it refuses; nothing
    // changes then, and the reason is said as an error. On success the
    // mirror lets go of its own pins (the server drops them too), takes the
    // source's map, and one history step records it. Resolves true once the
    // new assignment is in.
    setLayerMirror(layer, sourceId) {
        if (!layer) return Promise.resolve(false);
        if (this._lockedRefused && this._lockedRefused(layer)) {
            return Promise.resolve(false);
        }
        const want = sourceId === null || sourceId === undefined || sourceId === ''
            ? null : sourceId;
        const typed = want === null ? null
            : (Number.isFinite(Number(want)) ? Number(want) : want);
        const refused = (why) => {
            why = why || 'That screen cannot be mirrored.';
            if (typeof this._toast === 'function') {
                this._toast(why, true, 6000);
            }
            sendClientLog('mirror_screen_refused',
                          { layerId: layer.id, mirrorOf: typed, error: why });
            return false;
        };
        // A refusal is an expected answer, so it is ASKED for first, on a
        // 200 (routes_layers mirror_refusal_check): a 409 on the wire is
        // logged by the browser as an error. The PUT's own 409 still
        // guards a race between the two. A save on its way lands first: the
        // server compares the settings it holds, and a frame rate set a
        // moment ago must not read as a difference the pill never saw.
        const saved = typeof this._layerSavesSettled === 'function'
            ? this._layerSavesSettled() : Promise.resolve();
        const check = typed === null ? Promise.resolve({ error: null })
            : saved.then(() => fetch(`/api/layer/${layer.id}/mirror-refusal?of=${encodeURIComponent(typed)}`))
                .then(r => r.json()).catch(() => ({ error: null }));
        return check.then(pre => (pre && pre.error
            ? { ok: false, data: pre }
            : fetch(`/api/layer/${layer.id}?edited=1`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dataMirrorOf: typed }),
            }).then(r => r.json().then(data => ({ ok: r.ok, data })))))
            .then(({ ok, data }) => {
                if (!ok) return refused(data && data.error);
                // A socket echo replaces the object (applyServerLayer), so
                // the one held across the request may no longer be the
                // project's, and the history step below reads the project.
                const live = this._liveLayer(layer);
                if (typed === null) delete live.dataMirrorOf;
                else live.dataMirrorOf = typed;
                if (typed !== null && this.project && this.project.port_assignments
                        && Array.isArray(this.project.port_assignments.pins)) {
                    this.project.port_assignments.pins = this.project
                        .port_assignments.pins
                        .filter(p => String(p.layerId) !== String(layer.id));
                }
                sendClientLog('mirror_screen_set',
                              { layerId: layer.id, mirrorOf: typed });
                this.saveState(typed === null ? 'Stop Mirroring' : 'Mirror Screen');
                if (typeof this.updatePortCapacityDisplay === 'function') {
                    this.updatePortCapacityDisplay();
                }
                const refreshed = typeof this.refreshPortAssignment === 'function'
                    ? this.refreshPortAssignment() : null;
                return Promise.resolve(refreshed).then(() => {
                    if (window.canvasRenderer) window.canvasRenderer.render();
                    return true;
                });
            })
            .catch(err => {
                sendClientLog('mirror_screen_set_failed',
                              { layerId: layer.id, error: String(err) });
                return false;
            });
    }

    // ── a box on a copy OPT: Mirror or Backup ────────────────────────────
    //
    // On a card whose copy OPTs pick per box (the MX40 Pro in 20-port mode -
    // owner, 2026-10-30, "Either, you pick") an add that puts a box on a
    // copy OPT, or brings one there as the default pair, asks which it is
    // (resolve_card's nextBoxOnCopy). Resolves 'mirror', 'backup' or null
    // (cancelled: nothing is added).
    askCopyRole(card) {
        const modal = document.getElementById('copy-role-modal');
        if (!modal) return Promise.resolve('backup');
        if (!this._copyRoleWired) {
            this._copyRoleWired = true;
            const on = (id, result) => {
                const btn = document.getElementById(id);
                if (btn) btn.addEventListener('click', () => this._closeCopyRole(result));
            };
            on('copy-role-cancel', null);
            on('copy-role-backup', 'backup');
            on('copy-role-mirror', 'mirror');
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this._closeCopyRole(null);
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this._copyRoleResolve) this._closeCopyRole(null);
            });
        }
        const text = document.getElementById('copy-role-text');
        if (text) {
            const pairs = (card && card.copyTrunkList) || [];
            const copies = pairs.map(t => `${t.trunkTitle} copies ${t.copiesTitle}`)
                .join(', ');
            text.textContent = `This box goes on a copy output${copies
                ? ` (${copies})` : ''}. Mirror: it feeds a mirror screen. `
                + 'Backup: it backs up the output it copies.';
        }
        if (this._copyRoleResolve) this._copyRoleResolve(null);
        modal.style.display = 'block';
        return new Promise(resolve => { this._copyRoleResolve = resolve; });
    }

    _closeCopyRole(result) {
        const modal = document.getElementById('copy-role-modal');
        if (modal) modal.style.display = 'none';
        const resolve = this._copyRoleResolve;
        this._copyRoleResolve = null;
        if (resolve) resolve(result);
    }

    // Add one box to `card` through the processor routes, asking Mirror or
    // Backup first where the box lands on a copy OPT of a per-box card -
    // the next free OPT, or the one picked (`onCopy`, the body's trunk).
    addBoxWithRole(proc, card, body, action = 'Add Breakout Box', onCopy = false) {
        const url = `/api/processors/${proc.id}/cards/${card.id}/cvts`;
        if (!card.nextBoxOnCopy && !(onCopy && card.copyTrunks === 'per-box')) {
            return this._processorRequest(url, 'POST', body, action);
        }
        return this.askCopyRole(card).then(role => {
            if (!role) return null;
            return this._processorRequest(url, 'POST',
                Object.assign({}, body, { copyRole: role }), action);
        });
    }

    // The box gear's MIRROR / BACKUP strip, on a box sitting on a copy OPT
    // of a card that picks per box (resolve_card's copyRoleChoice).
    _buildBoxCopyRoleStrip(proc, cvt) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip hw-pop-box-copyrole';
        strip.style.marginTop = '6px';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'COPY';
        cap.title = 'What this box on a copy output carries.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Copy');
        bar.dataset.lrdField = `processor-cvt-copyrole-${cvt.id}`;
        [['mirror', 'Mirror', 'Feeds a mirror screen: with the first screen '
            + 'on the box this one copies, drag this box onto a matching '
            + 'second screen to make it the copy.'],
         ['backup', 'Backup', 'Backs up the output this box copies.']]
            .forEach(([role, text, tip]) => {
                // a box straddling a main OPT and its copy picks for its
                // copy input (copyInputRole)
                const lit = (cvt.copyInputRole || cvt.copyRole || 'backup') === role;
                const seg = document.createElement('button');
                seg.type = 'button';
                seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
                seg.setAttribute('role', 'radio');
                seg.setAttribute('aria-checked', lit ? 'true' : 'false');
                seg.dataset.level = role;
                seg.textContent = text;
                seg.title = tip;
                seg.addEventListener('click', () => {
                    if (lit) return;
                    this._processorRequest(
                        `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                        { copyRole: role }, 'Set Box Copy');
                });
                bar.appendChild(seg);
            });
        strip.appendChild(bar);
        return strip;
    }

    // ── per port: the card's own RJ45 or the box ─────────────────────────
    //
    // Where a card's RJ45s are also carried out on its OPTs (plugChoice:
    // the MX40 Pro, the H_16xRJ45+2xfiber), each port plugs in at ONE
    // place (owner, 2026-10-30, "Per port"). The port's chip says where and
    // switches it; the card's gear switches a whole OPT's ports at once.

    _plugCardWord(proc, card) {
        const word = typeof this.unitWordFor === 'function'
            ? this.unitWordFor(proc, card) : 'card';
        return `${word.charAt(0).toUpperCase()}${word.slice(1)} RJ45`;
    }

    _buildPlugSeg(fieldKey, now, cardText, onPick) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip hw-pop-port-plug';
        strip.style.margin = '2px 0 4px 0';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'PLUGS IN AT';
        cap.title = 'One place per port: never the same port both ways.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Plugs in at');
        bar.dataset.lrdField = fieldKey;
        [['card', cardText, `The port plugs in at the ${cardText}.`],
         ['box', 'Breakout box', 'The port plugs in at the breakout box on '
            + 'the OPT that carries it.']]
            .forEach(([plug, text, tip]) => {
                const lit = now === plug;
                const seg = document.createElement('button');
                seg.type = 'button';
                seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
                seg.setAttribute('role', 'radio');
                seg.setAttribute('aria-checked', lit ? 'true' : 'false');
                seg.dataset.level = plug;
                seg.textContent = text;
                seg.title = tip;
                seg.addEventListener('click', () => { if (!lit) onPick(plug); });
                bar.appendChild(seg);
            });
        strip.appendChild(bar);
        return strip;
    }

    // One port's strip, for the chip's editor.
    _buildPortPlugStrip(proc, card, port) {
        if (!port || !port.plug) return null;
        return this._buildPlugSeg(
            `processor-port-plug-${card.id}-${port.number}`, port.plug,
            this._plugCardWord(proc, card),
            (plug) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
                'PUT', { plug }, 'Set Port Plug'));
    }

    // The card gear's per-OPT shortcut: each primary box whose ports have
    // the choice, all of its ports at once.
    _buildCardPlugRows(proc, card) {
        const limit = card.plugChoicePorts;
        if (!limit) return null;
        const byNumber = new Map((card.ports || []).map(p => [p.number, p]));
        const rows = [];
        (card.cvts || []).forEach(cvt => {
            if (cvt.copyRole || cvt.beyondTrunks || !cvt.portCount) return;
            const numbers = [];
            const own = cvt.portNumbers
                || Array.from({ length: cvt.portCount }, (_, i) => cvt.firstPort + i);
            own.forEach(n => {
                if (n <= limit && byNumber.has(n) && byNumber.get(n).plug) numbers.push(n);
            });
            if (!numbers.length) return;
            const atCard = numbers.filter(n => byNumber.get(n).plug === 'card');
            const now = atCard.length === numbers.length ? 'card'
                : (atCard.length ? 'mixed' : 'box');
            const wrap = document.createElement('div');
            wrap.style.marginTop = '4px';
            const head = document.createElement('div');
            head.style.fontSize = '11px';
            head.style.color = 'var(--ps-dim, #c0c0c0)';
            head.textContent = `${cvt.trunkTitle || cvt.displayTitle}: ports `
                + `${numbers[0]}-${numbers[numbers.length - 1]}`
                + (now === 'mixed' ? ` (${atCard.length} at the RJ45)` : '');
            wrap.appendChild(head);
            wrap.appendChild(this._buildPlugSeg(
                `processor-card-plug-${card.id}-${cvt.id}`, now,
                this._plugCardWord(proc, card),
                (plug) => {
                    const set = new Set(card.ethernetPorts || []);
                    numbers.forEach(n => (plug === 'card' ? set.add(n) : set.delete(n)));
                    return this._processorRequest(
                        `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                        { ethernetPorts: [...set].sort((a, b) => a - b) },
                        'Set Port Plugs');
                }));
            rows.push(wrap);
        });
        if (!rows.length) return null;
        const block = document.createElement('div');
        block.className = 'hw-pop-plug-block';
        block.style.marginTop = '6px';
        rows.forEach(r => block.appendChild(r));
        return block;
    }
}

for (const k of Object.getOwnPropertyNames(_MirrorScreens.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_MirrorScreens.prototype, k));
    }
}
