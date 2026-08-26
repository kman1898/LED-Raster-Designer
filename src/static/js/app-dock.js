// app-dock: the hardware dock, a tray under the canvas that holds the view's
// hardware and makes DRAG the way assignments are made.
//
// The Signal and Power panels stay the place DEVICES are named, inspected and
// templated; the dock is the place hardware is AIMED - and, on the data side,
// the ONE place ports appear at all. The Processors panel used to draw the
// same port grid a second time, which was the same data twice; now each port
// chip here carries the port's own editor folded inside it (the shared
// _wireTiles machinery): click or Enter opens the per-port Name and Return
// boxes, the manual backup pick and the occupancy detail in place, and drag
// still starts on press-and-move. Data view lays out every
// processor's cards, their breakout boxes and their port tiles; Power view
// lays out every distro and its multi slots. Dragging a tile onto the canvas
// assigns through exactly the operations the panels used - place, pin,
// move-block, place-overflow, setSocaDistro, setSocaNumber - so the rules,
// the refusals, the conflict question and the undo entries are the same ones,
// arrived at by pointing instead of picking from a select.
//
// Drop semantics (the user's rule, verbatim shape):
//   - a single PORT tile lands on a specific port RUN: that screen-port is
//     placed on that processor port (conflicts come back as the existing
//     question, never a silent displacement);
//   - a single multi SLOT lands on a specific CIRCUIT run: that circuit's
//     multi takes that (distro, number) - landing on an occupied slot is the
//     existing join gesture, exactly as picking the number was. Landing on a
//     circuit that is NOT the first of its multi SPLITS the multi there
//     (the drop implies the boundary the sidebar's Split select used to ask
//     for): the circuits from there to the multi's end take the box, capped
//     at its free tails, one undo entry for split and assignment together;
//   - a whole CARD or BREAKOUT BOX lands anywhere on a screen: the screen's
//     ports fill onto it in order from the first unassigned (place-overflow),
//     or the whole block moves there when nothing is unassigned (move-block,
//     windowed to the box's span for a box);
//   - a whole DISTRO lands anywhere on a screen: the screen's unassigned
//     multis take that distro, numbered automatically;
//   - an OCCUPIED port tile or multi slot dragged back onto the dock releases
//     that assignment (unpin / clear distro+number), undoable like the rest.
//
// Right-click is the other way back: a drawn port run, a power circuit, a
// dock chip, a card, a box or a distro right-clicked gets a "Clear …" item on
// the app's context menu (_prepareClearMenu below arms it, showContextMenu
// draws it). Clearing runs the same release operations the drag-back runs -
// nothing is confirmed, because a clear is undoable and touches only the
// assignment, never a name or a template - and a clear that is impossible is
// offered disabled with the reason as its title, the drag-back rule spoken
// before the gesture instead of after.
//
// The drag is pointer-based, not HTML5 DnD: the canvas is not a drop zone the
// DnD model understands, page.mouse drives pointers natively in the tests,
// and the resize handles already set the document-level move/up + teardown
// pattern this follows. mouseup is bound on the document for the same reason
// canvas.js binds its own on window: a drag routinely ends over a sidebar.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _HardwareDock {

    initHardwareDock() {
        const dock = document.getElementById('hardware-dock');
        if (!dock) return;
        this._dockDrag = null;
        this._dockDropTarget = null;
        // Fold and height are the sidebars' machinery transposed, not the
        // section machinery: initSidebarToggles (app-core.js) owns the
        // collapse - and settles the canvas after it - and theme.js's
        // PANELS row owns the drag-resize, so there is nothing to watch
        // here the way the old section fold needed watching.
        this.renderHardwareDock();
    }

    // ── drawing ───────────────────────────────────────────────────────────

    renderHardwareDock() {
        const dock = document.getElementById('hardware-dock');
        const body = document.getElementById('hardware-dock-body');
        if (!dock || !body) return;
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : '';
        // The port chips carry per-port editors now, so a field mid-edit
        // rides the wipe by its data-lrd-field key - the same guard every
        // panel rebuild takes before its own innerHTML wipe.
        if (typeof this._preserveEditorFocus === 'function') {
            this._preserveEditorFocus();
        }
        // Remember which chip FACE held focus through the wipe, by its
        // stable key - the same reason the panels carry data-lrd-field.
        const focused = document.activeElement
            && document.activeElement.dataset
            && document.activeElement.dataset.hwdock;
        const before = dock.offsetHeight;
        body.innerHTML = '';
        if (mode === 'data-flow') {
            this._dockRenderData(body);
            // The port chips fold their editors inside them, so the tile
            // machinery wires them after every wipe - which chip is open
            // rode the wipe on the app (_openTiles), the way the fold state
            // rides it in localStorage. The power slot chips stay plain
            // drag handles (their editing lives in the Power sidebar's own
            // multi tiles), so only the data render wires tiles.
            if (typeof this._wireTiles === 'function') this._wireTiles(body);
        } else if (mode === 'power') {
            this._dockRenderPower(body);
        }
        if (focused) {
            const again = body.querySelector(
                `[data-hwdock="${CSS.escape(focused)}"]`);
            if (again) again.focus();
        }
        // Content growing or shrinking the tray moves the canvas's bottom
        // edge; the backing store has to follow or a strip paints stale.
        if (dock.offsetHeight !== before
                && typeof this.settleLayout === 'function') {
            this.settleLayout();
        }
    }

    _dockNote(host, text) {
        const note = document.createElement('div');
        note.className = 'hw-dock-note';
        note.textContent = text;
        host.appendChild(note);
    }

    _dockRenderData(host) {
        const procs = this._processorsResolved || [];
        if (!procs.length) {
            this._dockNote(host,
                'No processors. Add one in the Signal panel and its ports '
                + 'appear here to drag onto screens.');
            return;
        }
        const procEls = new Map();
        const unitsByCard = new Map();
        procs.forEach(proc => {
            const wrap = document.createElement('div');
            wrap.className = 'hw-dock-proc';
            const title = document.createElement('div');
            title.className = 'hw-dock-proc-name';
            title.textContent = proc.name || proc.deviceName;
            wrap.appendChild(title);
            (proc.slots || []).forEach(slot => {
                if (!slot.card) return;
                const unit = this._dockBuildCard(proc, slot.card);
                unitsByCard.set(slot.card.id, unit);
                wrap.appendChild(unit);
            });
            procEls.set(proc.id, wrap);
            host.appendChild(wrap);
        });
        // The pair-presentation rule the panel follows, at the tray's two
        // levels: a designated backup UNIT nests whole - name strip and
        // all - under its main's block, and a backup card inside the same
        // chassis nests under the card it mirrors. The chips inside keep
        // their own keys and drags either way.
        procs.forEach(proc => {
            (proc.slots || []).forEach(slot => {
                const card = slot.card;
                if (card && card.backupFor
                        && card.backupFor.processorId === proc.id) {
                    this._nestBackupUnder(
                        unitsByCard.get(card.backupFor.cardId),
                        unitsByCard.get(card.id));
                }
            });
            const mainId = this._backupUnitMainId(proc);
            if (mainId) {
                this._nestBackupUnder(procEls.get(mainId),
                                      procEls.get(proc.id));
            }
        });
    }

    _dockBuildCard(proc, card) {
        const unit = document.createElement('div');
        unit.className = 'hw-dock-unit';

        const summary = ((this._assignment && this._assignment.cards) || [])
            .find(c => c.cardId === card.id);
        // A unit consumed as a 1:1 backup wears the tag its box-level
        // cousin wears - dragging it is pointless (every port is refused as
        // a return end) but hiding it would hide where the returns land.
        const cardTag = card.backupFor
            ? ` (backs up ${card.backupFor.title})` : '';
        const head = this._dockBuildHandle(
            {
                type: 'card', cardId: card.id,
                title: (card.name || card.deviceName) + cardTag,
            },
            `card-${card.id}`,
            (card.name || card.deviceName) + cardTag,
            summary && summary.capacityKnown
                ? `${summary.used} / ${summary.capacity}` : '',
            'Drag the whole card onto a screen: its ports fill in order from '
            + 'the first unassigned, or the whole run moves here.');
        unit.appendChild(head);

        // The ports draw grouped the way they arrive: each breakout box gets
        // its own draggable strip holding its span of the card's ports, and
        // ports no box delivers stay directly under the card. A copy/backup
        // box lists the SAME card ports again - dragging it lands on the same
        // sockets as dragging its primary, because they are the same sockets.
        const cvts = card.cvts || [];
        const covered = new Set();
        cvts.forEach(cvt => {
            (cvt.ports || []).forEach(p => covered.add(p.number));
        });
        const loose = (card.ports || []).filter(p => !covered.has(p.number));
        if (loose.length) {
            unit.appendChild(this._dockBuildPortGrid(proc, card, loose));
        }
        const boxEls = new Map();
        cvts.forEach(cvt => {
            const nums = (cvt.ports || []).map(p => p.number);
            if (!nums.length) return;
            const box = document.createElement('div');
            box.className = 'hw-dock-box';
            const span = `${Math.min(...nums)}-${Math.max(...nums)}`;
            const tag = cvt.backupOf ? ' (backup)'
                : (cvt.duplicateOf ? ' (copy)' : '');
            box.appendChild(this._dockBuildHandle(
                {
                    type: 'box', cardId: card.id,
                    first: Math.min(...nums), last: Math.max(...nums),
                    title: (cvt.name || cvt.deviceName) + tag,
                    beyondTrunks: !!cvt.beyondTrunks,
                },
                `box-${cvt.id}`,
                (cvt.name || cvt.deviceName) + tag,
                `ports ${span}`,
                'Drag the whole box onto a screen: the screen\'s ports fill '
                + 'onto this box\'s sockets in order from the first '
                + 'unassigned.'));
            box.appendChild(this._dockBuildPortGrid(proc, card,
                                                    cvt.ports || []));
            // A redundant pair of boxes is one group here too: B nests
            // under the A it backs (the panel's rule, worn by the tray),
            // and a box with no role stays the plain strip it was.
            boxEls.set(cvt.id, box);
            const main = cvt.backupOf && boxEls.get(cvt.backupOf);
            if (main) this._nestBackupUnder(main, box);
            else unit.appendChild(box);
        });
        return unit;
    }

    _dockBuildPortGrid(proc, card, ports) {
        const grid = document.createElement('div');
        grid.className = 'lrd-tile-grid hw-dock-grid';
        ports.forEach(port => {
            grid.appendChild(this._dockBuildPortTile(proc, card, port));
        });
        return grid;
    }

    // One port as one dense cell of its grid: number, the resolved label
    // (the assignment's answer, never re-derived here), occupant, and the
    // occupied/clash ground. The chip is both the drag handle AND the
    // port's editor - the dock is the one place ports appear, so the
    // editing the panel's tiles carried lives here now: click or Enter
    // (no movement) opens the editor IN the tile through the shared
    // _wireTiles machinery, press-and-move drags. The editor is hidden,
    // never detached (style.css .lrd-tile-body), so every field keeps
    // answering the focus-restore lookup from inside a closed chip.
    _dockBuildPortTile(proc, card, port) {
        const tile = document.createElement('div');
        tile.className = 'lrd-tile hw-dock-tile';
        // The tile machinery's keys, so the open editor comes back by id
        // through the tray's wholesale rebuilds - one open editor per card.
        tile.dataset.lrdTile = `port-${card.id}-${port.number}`;
        tile.dataset.lrdTileBox = `card-${card.id}`;
        const occupants = this._portOccupants(card.id, port.number);
        if (occupants.length > 1) tile.classList.add('lrd-tile-clash');
        else if (occupants.length) tile.classList.add('lrd-tile-occupied');

        const face = document.createElement('div');
        face.className = 'lrd-tile-face';
        const top = document.createElement('div');
        top.className = 'lrd-tile-line';
        const num = document.createElement('span');
        num.style.color = port.beyondCeiling ? '#d05a52' : '#666';
        num.textContent = String(port.number);
        top.appendChild(num);
        if (port.label) {
            const label = document.createElement('span');
            label.style.color = port.labelSource === 'manual'
                ? '#e0c98a' : '#ccc';
            top.appendChild(document.createTextNode(' '));
            label.textContent = port.label;
            top.appendChild(label);
        }
        face.appendChild(top);
        const who = document.createElement('div');
        who.className = 'lrd-tile-line';
        if (!occupants.length) {
            if (port.backsUp) {
                // Claimed by role: this socket is another main's return end.
                // Same gold as the backup boxes, because it is the same job.
                who.style.color = '#c8a04a';
                who.textContent = `backs up ${port.backsUp.label
                    || `port ${port.backsUp.port}`}`;
            } else {
                who.style.color = '#4a4a4a';
                who.textContent = 'free';
            }
        } else if (occupants.length > 1) {
            who.style.color = '#d05a52';
            who.textContent = 'clash';
        } else if (occupants[0].role === 'return') {
            // Derived occupancy: the socket carries this screen-port's
            // return, following its main - the role's gold, because the
            // claim is the role's, and only the main can clear it.
            who.style.color = '#c8a04a';
            who.textContent =
                `${occupants[0].name} p${occupants[0].number} return`;
        } else {
            who.style.color = '#999';
            who.textContent = occupants[0].name;
        }
        face.appendChild(who);
        tile.appendChild(face);

        face.title = `Port ${port.number}`
            + (port.label ? ` - ${port.label}` : '')
            + (occupants.length
                ? ` - ${occupants.map(o => `${o.name} p${o.number}`
                    + (o.role === 'return' ? ' return' : '')).join(', ')}`
                : (port.backsUp
                    ? ` - backs up ${port.backsUp.label
                        || `port ${port.backsUp.port} on ${port.backsUp.cardTitle}`}`
                    : ' - free'))
            + (port.beyondCeiling ? ' - beyond this card’s ceiling' : '')
            + '. Click to edit'
            + (port.backsUp
                ? '. A backup port is that port\'s return end - nothing '
                    + 'else can land on it.'
                : '; drag onto a port run to place it there'
                    + (occupants.some(o => o.source === 'pin')
                        ? '; drag back onto this tray to release it.' : '.'));

        this._dockWireDraggable(face, {
            type: 'port', cardId: card.id, port: port.number,
            title: port.label || `${card.name || card.deviceName} `
                + `port ${port.number}`,
        }, `port-${card.id}-${port.number}`);

        const editor = this._buildPortRow(proc, card, port);
        editor.classList.add('lrd-tile-body');
        tile.appendChild(editor);

        if (this._tileOpenId(tile.dataset.lrdTileBox)
                === tile.dataset.lrdTile) {
            tile.classList.add('lrd-tile-open');
        }
        return tile;
    }

    // One of a port editor's two name boxes, captioned the way the soca
    // rows' fields are: an unlabeled box beside another unlabeled box reads
    // as noise, and these two hold different ends of the same cable. The
    // resolved label sits in the placeholder, so an empty box still reads
    // as what that end is actually called. (Moved here whole from the
    // Processors panel when the dock became the one port surface - the
    // data-lrd-field keys came with it, and they exist nowhere else.)
    _buildPortNameField(caption, fieldKey, value, placeholder, manual,
                        titles, onCommit) {
        const cell = document.createElement('div');
        cell.style.flex = '1 1 70px';
        cell.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.display = 'block';
        cap.style.fontSize = '10px';
        cap.style.color = '#888';
        cap.textContent = caption;
        cell.appendChild(cap);

        const input = document.createElement('input');
        input.type = 'text';
        input.value = value || '';
        input.placeholder = placeholder || 'unnamed';
        input.title = manual ? titles.named : titles.unnamed;
        input.dataset.lrdField = fieldKey;
        input.style.padding = '0 3px';
        input.style.background = 'transparent';
        input.style.border = '1px solid transparent';
        input.style.borderRadius = '3px';
        input.style.color = manual ? '#e0c98a' : '#ccc';
        input.style.fontFamily = 'monospace';
        input.style.fontSize = '11px';
        input.style.width = '100%';
        input.style.minWidth = '0';
        input.style.boxSizing = 'border-box';
        input.addEventListener('focus', () => {
            input.style.borderColor = '#3a3a3a';
            input.style.background = '#0d0d0d';
        });
        input.addEventListener('blur', () => {
            input.style.borderColor = 'transparent';
            input.style.background = 'transparent';
        });
        input.addEventListener('change', () => onCommit(input.value.trim()));
        cell.appendChild(input);
        return cell;
    }

    // The open chip's editor: the two name boxes on a wrapping line, then
    // the occupancy detail. Naming and reading only - putting a screen ON
    // the socket stays the chip's own drag, so no set/place control ever
    // grows here: one gesture, one set of rules.
    _buildPortRow(proc, card, port) {
        const wrap = document.createElement('div');
        const row = document.createElement('div');
        // The names are inputs rather than text because a port is a socket
        // someone has to be able to call what the house already calls it,
        // and since the processor beats a screen's own override for an
        // assigned port, these boxes are the ONLY place left to do it.
        // Making it a mode to find would strand every port that needs one.
        row.style.display = 'flex';
        row.style.flexWrap = 'wrap';
        row.style.gap = '4px';
        row.style.alignItems = 'center';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';
        row.style.marginBottom = '2px';

        const rename = (body, action) => this._processorRequest(
            `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
            'PUT', body, action);

        // Two ends of one socket, named side by side. The fields share a
        // wrapping line of their own: two 70px boxes fit abreast in a chip
        // opened across its grid row and stack where a narrow unit squeezes
        // them, exactly as the soca rows' captioned fields do.
        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '4px';
        names.style.margin = '0 0 4px 0';
        names.appendChild(this._buildPortNameField(
            'Name',
            `processor-port-name-${card.id}-${port.number}`,
            (card.portNames || {})[String(port.number)],
            // No name anywhere upstream means no processor-derived label at
            // all, and the screen's own template is still the thing doing
            // the work - which is what "unnamed" has always meant here.
            port.label,
            port.labelSource === 'manual',
            {
                named: 'Named by hand. Clear the box to go back to the '
                    + 'card’s template.',
                unnamed: 'Name this port. It beats the card’s template for '
                    + 'this port only.',
            },
            (val) => rename({ name: val }, 'Rename Processor Port')));
        names.appendChild(this._buildPortNameField(
            'Return',
            `processor-port-return-${card.id}-${port.number}`,
            (card.returnPortNames || {})[String(port.number)],
            port.returnLabel,
            port.returnLabelSource === 'manual',
            {
                named: 'Named by hand. Clear the box to go back to the '
                    + 'name derived from the primary (R1-1 for P1-1).',
                unnamed: 'Name this port’s redundancy run. Left blank it is '
                    + 'derived from the primary: its leading P becomes R '
                    + '(R1-1 for P1-1), any other name takes an R after it.',
            },
            (val) => rename({ returnName: val },
                            'Rename Processor Port Return')));

        const who = document.createElement('div');
        // the one elastic cell of its line, same shape as the assignment rows
        who.style.flex = '1 1 60px';
        who.style.minWidth = '0';
        who.style.overflow = 'hidden';
        who.style.textOverflow = 'ellipsis';
        who.style.whiteSpace = 'nowrap';
        const occupants = this._portOccupants(card.id, port.number);
        if (!occupants.length) {
            // A port with nothing on it says so. The chip face says it too,
            // but the open editor must not go silent where the face spoke.
            who.style.color = '#4a4a4a';
            who.textContent = 'free';
            who.title = 'No screen is on this port.';
        } else {
            const parts = occupants.map(o => `${o.name} p${o.number}`
                + (o.role === 'return' ? ' return' : ''));
            const derived = occupants.length === 1
                && occupants[0].role === 'return';
            who.style.color = occupants.length > 1 ? '#d05a52'
                : (derived ? '#c8a04a' : '#888');
            who.textContent = parts.join(', ')
                + (occupants.length > 1 ? ' - clash' : '');
            who.title = occupants.length > 1
                ? `${parts.join(' and ')} both claim this port. Nothing has `
                  + 'been renumbered - see Port Numbering.'
                : (derived
                    ? `${occupants[0].name} port ${occupants[0].number}'s `
                      + 'return end - it follows the main and clears with it.'
                    : `${occupants[0].name}, its port ${occupants[0].number}`);
        }
        row.appendChild(who);
        wrap.appendChild(names);

        // The port's place in the redundancy mapping, stated where its
        // labels are edited. A consumed port says whose return it carries; a
        // backed main says which physical socket its return comes back on -
        // the same socket its Return placeholder is already named after.
        if (port.backsUp) {
            const role = document.createElement('div');
            role.style.fontSize = '11px';
            role.style.color = '#c8a04a';
            role.style.margin = '0 0 4px 0';
            role.textContent = `Backs up ${port.backsUp.label
                || `port ${port.backsUp.port} on ${port.backsUp.cardTitle}`}`
                + ' - this socket carries its return.';
            wrap.appendChild(role);
        } else if (port.backedBy) {
            const back = document.createElement('div');
            back.style.fontSize = '11px';
            back.style.color = '#888';
            back.style.margin = '0 0 4px 0';
            back.textContent = `Return comes back on ${port.backedBy.label
                || `port ${port.backedBy.port} on ${port.backedBy.cardTitle}`}.`;
            wrap.appendChild(back);
        }

        // Manual mode's per-port pick: which socket backs THIS one. Sparse
        // by design - a blank port number clears the pick and the main
        // simply has no backup, because manual is explicit.
        const shape = card.redundancyShape;
        if (shape && !shape.forced && shape.mode === 'manual'
                && !card.backupFor && !port.backsUp) {
            const picked = (card.backupPorts || {})[String(port.number)] || null;
            const pick = document.createElement('div');
            pick.style.display = 'flex';
            pick.style.gap = '4px';
            pick.style.alignItems = 'center';
            pick.style.margin = '0 0 4px 0';
            const cap = document.createElement('span');
            cap.style.fontSize = '10px';
            cap.style.color = '#888';
            cap.textContent = 'Backed by';
            pick.appendChild(cap);

            const cardSel = document.createElement('select');
            cardSel.dataset.lrdField =
                `processor-port-backup-card-${card.id}-${port.number}`;
            cardSel.style.flex = '1';
            cardSel.style.minWidth = '0';
            const own = document.createElement('option');
            own.value = card.id;
            own.textContent = card.name || proc.name || card.deviceName;
            cardSel.appendChild(own);
            this._otherCards(card.id).forEach(({ proc: p, card: c }) => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name || p.name || c.deviceName;
                if (picked && picked.cardId === c.id) opt.selected = true;
                cardSel.appendChild(opt);
            });

            const portBox = document.createElement('input');
            portBox.type = 'number';
            portBox.min = '1';
            portBox.dataset.lrdField =
                `processor-port-backup-port-${card.id}-${port.number}`;
            portBox.style.width = '52px';
            portBox.placeholder = 'port';
            portBox.value = picked ? String(picked.port) : '';
            portBox.title = 'The port whose socket carries this one’s '
                + 'return. Blank means no backup.';

            // Through the same PUT the name boxes use - one route, one rule
            // about what a port edit is.
            const commit = () => {
                const value = parseInt(portBox.value, 10);
                const body = portBox.value.trim() === '' || !(value >= 1)
                    ? { backup: null }
                    : { backup: { cardId: cardSel.value, port: value } };
                rename(body, 'Change Port Backup');
            };
            cardSel.addEventListener('change', commit);
            portBox.addEventListener('change', commit);
            pick.appendChild(cardSel);
            pick.appendChild(portBox);
            wrap.appendChild(pick);
        }

        wrap.appendChild(row);
        return wrap;
    }

    _dockRenderPower(host) {
        const distros = this.getDistros ? this.getDistros() : [];
        if (!distros.length) {
            this._dockNote(host,
                'No distros. Add one in the Power panel and its multi slots '
                + 'appear here to drag onto circuits.');
            return;
        }
        distros.forEach(d => {
            host.appendChild(this._dockBuildDistro(d));
        });
    }

    _dockBuildDistro(d) {
        const unit = document.createElement('div');
        unit.className = 'hw-dock-unit';
        const phase = Number(d.phase) === 3 ? '3ph' : '1ph';
        unit.appendChild(this._dockBuildHandle(
            { type: 'distro', distroId: d.id, title: d.name || d.id },
            `distro-${d.id}`,
            d.name || d.id,
            `${d.ratingA || '?'} A · ${d.voltage || '?'} V · ${phase}`,
            'Drag the whole distro onto a screen: its unassigned multis all '
            + 'land on this distro, numbered automatically.'));

        // The slots a distro offers are demand-driven, the same unbounded
        // rule the old number select used: every occupied or pinned number,
        // plus exactly one spare on the end, so there is always a free slot
        // to drag and never a wall of empty ones.
        const inUse = this._distroMultiNumbers(d.id);
        const maxN = Math.max(0, ...inUse.keys()) + 1;
        const grid = document.createElement('div');
        grid.className = 'lrd-tile-grid lrd-tile-grid-wide hw-dock-grid';
        for (let n = 1; n <= maxN; n++) {
            grid.appendChild(this._dockBuildSlotChip(d, n, inUse.get(n) || []));
        }
        unit.appendChild(grid);
        return unit;
    }

    _dockBuildSlotChip(d, n, members) {
        const tile = document.createElement('div');
        tile.className = 'lrd-tile hw-dock-tile';

        // A multi IS a 6-tail box, so the chip carries the six tails as
        // cells: which screen's circuit holds each one (the same rendered
        // positions the soca tiles and the shared-box notes read), which
        // are free, and a tail two stored sets both claim wears the clash
        // red. Over six legs on one box is the overflow the soca tiles
        // flag - the chip wears the same clash ground.
        const byTail = new Map();   // tail 1..6 -> [{who, label}]
        let legs = 0;
        members.forEach(m => {
            const l = (this.project.layers || []).find(x => x.id === m.layerId);
            if (!l) return;
            const rec = this._powerNaming(l).socas.get(m.soca);
            if (rec) {
                (rec.positions || []).forEach((t, i) => {
                    const list = byTail.get(t) || [];
                    list.push({
                        who: l.name,
                        label: this.getPowerCircuitLabel(l, rec.circuits[i]),
                    });
                    byTail.set(t, list);
                });
            }
            legs += m.legs || 0;
        });
        const free = [1, 2, 3, 4, 5, 6].filter(t => !byTail.has(t));
        if (legs > 6) tile.classList.add('lrd-tile-clash');
        else if (members.length) tile.classList.add('lrd-tile-occupied');

        const face = document.createElement('div');
        face.className = 'lrd-tile-face';
        const top = document.createElement('div');
        top.className = 'lrd-tile-line';
        const num = document.createElement('span');
        num.style.color = '#666';
        num.textContent = String(n);
        top.appendChild(num);
        const cap = document.createElement('span');
        cap.style.color = '#ccc';
        top.appendChild(document.createTextNode(' '));
        cap.textContent = members.length
            ? (free.length ? `tails ${this._fmtTails(free)} free` : 'full')
            : 'multi';
        top.appendChild(cap);
        face.appendChild(top);
        const who = document.createElement('div');
        who.className = 'lrd-tile-line';
        if (!members.length) {
            who.style.color = '#4a4a4a';
            who.textContent = 'free';
        } else {
            who.style.color = legs > 6 ? '#d05a52' : '#999';
            who.textContent = members.map(m => m.layerName).join(' + ');
        }
        face.appendChild(who);
        // The six tail sockets, one cell each, in the port-chip register:
        // lit when a circuit holds the tail, clash-red when two stored sets
        // claim it, dim when free. Each cell says who on hover, so the fan
        // can be read tail by tail without opening the Power sidebar.
        const row = document.createElement('div');
        row.className = 'hw-dock-tails';
        for (let t = 1; t <= 6; t++) {
            const cell = document.createElement('span');
            const holders = byTail.get(t) || [];
            cell.className = 'hw-dock-tail'
                + (holders.length > 1 ? ' hw-dock-tail-clash'
                    : (holders.length ? ' hw-dock-tail-used' : ''));
            cell.textContent = String(t);
            cell.title = `Tail ${t} - ` + (holders.length
                ? holders.map(h => `${h.who} ${h.label}`).join(', ')
                    + (holders.length > 1 ? ' (claimed twice)' : '')
                : 'free');
            row.appendChild(cell);
        }
        face.appendChild(row);
        tile.appendChild(face);

        face.title = `${d.name || d.id} multi ${n} - `
            + (members.length
                ? `${members.map(m => m.layerName).join(' and ')}, `
                    + (free.length
                        ? `tails ${this._fmtTails(free)} free`
                        : 'no tails free')
                : 'free')
            + '. Drag onto a circuit to land that circuit\'s multi here - '
            + 'the first circuit takes the whole multi, a later circuit '
            + 'splits it there and this box takes the rest'
            + (members.length
                ? '; drag back onto this tray to unassign it.' : '.');

        this._dockWireDraggable(face, {
            type: 'slot', distroId: d.id, number: n,
            title: `${d.name || d.id} ${n}`,
        }, `slot-${d.id}-${n}`);
        return tile;
    }

    // A unit's title strip, which is also the unit's drag handle. The grip
    // glyph is the affordance the canvas-group rows already use.
    _dockBuildHandle(payload, key, name, detail, tip) {
        const head = document.createElement('div');
        head.className = 'hw-dock-head-row';
        const grip = document.createElement('span');
        grip.className = 'hw-dock-grip';
        grip.textContent = '⋮⋮';
        head.appendChild(grip);
        const label = document.createElement('span');
        label.className = 'hw-dock-unit-name';
        label.textContent = name;
        head.appendChild(label);
        if (detail) {
            const info = document.createElement('span');
            info.className = 'hw-dock-unit-info';
            info.textContent = detail;
            head.appendChild(info);
        }
        head.title = tip;
        this._dockWireDraggable(head, payload, key);
        return head;
    }

    // ── the drag itself ───────────────────────────────────────────────────

    _dockWireDraggable(el, payload, key) {
        el.dataset.hwdock = key;
        // The payload rides on the element too, so a right-click can know
        // what chip it landed on (_prepareClearMenu reads it back) without
        // re-deriving card ids and spans from the key string.
        el.dataset.hwdockPayload = JSON.stringify(payload);
        // A real tab stop, like the panel tiles' faces: the dock must stay
        // reachable by keyboard even though the drag gesture itself has no
        // keyboard equivalent yet.
        el.tabIndex = 0;
        el.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            this._dockArmDrag(e, payload, el);
        });
    }

    _dockArmDrag(e, payload, el) {
        const startX = e.clientX;
        const startY = e.clientY;
        let live = false;
        const move = (ev) => {
            if (!live) {
                // A 4px threshold keeps a plain click from twitching into a
                // drag - same latitude every drag on the canvas gives. It is
                // also the whole click-vs-open split for the openable port
                // chips: press-and-move past 4px is the drag, press released
                // inside it is the click that opens the editor.
                if (Math.abs(ev.clientX - startX) < 4
                        && Math.abs(ev.clientY - startY) < 4) return;
                live = true;
                this._dockStartDrag(payload, el);
            }
            this._dockMoveDrag(ev);
        };
        const up = (ev) => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            if (live) {
                // A drag that ends back over its own chip still synthesizes
                // a click after mouseup, and on an openable port chip that
                // click would open the editor the drop never asked for.
                // Swallow exactly that one click - the guard lifts on the
                // next macrotask, after the browser has dispatched (or
                // skipped) the click for THIS gesture, so the next real
                // click opens as normal.
                const swallow = (ce) => {
                    ce.stopPropagation();
                    ce.preventDefault();
                };
                document.addEventListener('click', swallow, true);
                setTimeout(() => {
                    document.removeEventListener('click', swallow, true);
                }, 0);
                this._dockEndDrag(ev);
            }
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
    }

    _dockStartDrag(payload, el) {
        this._dockDrag = {
            payload,
            // The data view's run geometry, frozen at pickup: which panel
            // belongs to which port of which screen. The power side reads
            // the renderer's own retained circuit maps live instead.
            dataMap: (window.canvasRenderer
                && window.canvasRenderer.viewMode === 'data-flow')
                ? this._dockBuildDataMap() : null,
        };
        this._dockDropTarget = null;
        const ghost = document.createElement('div');
        ghost.id = 'hw-dock-ghost';
        ghost.textContent = payload.title || payload.type;
        document.body.appendChild(ghost);
        this._dockDrag.ghost = ghost;
        document.body.style.cursor = 'grabbing';
        document.body.style.userSelect = 'none';
        if (el && el.classList) el.classList.add('hw-dock-dragging');
        this._dockDrag.source = el;
        sendClientLog('dock_drag_started', { payload });
    }

    _dockMoveDrag(ev) {
        const drag = this._dockDrag;
        if (!drag) return;
        drag.ghost.style.left = `${ev.clientX + 14}px`;
        drag.ghost.style.top = `${ev.clientY + 10}px`;
        const target = this._dockHitTest(ev, drag);
        const changed = JSON.stringify(target)
            !== JSON.stringify(this._dockDropTarget);
        this._dockDropTarget = target;
        const dock = document.getElementById('hardware-dock');
        if (dock) {
            dock.classList.toggle('hw-dock-drop-target',
                !!(target && target.kind === 'dock'));
        }
        if (changed && window.canvasRenderer) {
            // One paint per target change, not per mousemove: the highlight
            // only moves when the run under the cursor does.
            window.canvasRenderer.render();
        }
    }

    _dockEndDrag(ev) {
        const drag = this._dockDrag;
        const target = this._dockDropTarget;
        this._dockDrag = null;
        this._dockDropTarget = null;
        if (drag) {
            if (drag.ghost) drag.ghost.remove();
            if (drag.source && drag.source.classList) {
                drag.source.classList.remove('hw-dock-dragging');
            }
        }
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        const dock = document.getElementById('hardware-dock');
        if (dock) dock.classList.remove('hw-dock-drop-target');
        if (window.canvasRenderer) window.canvasRenderer.render();
        if (drag && target) this._dockPerformDrop(drag.payload, target);
    }

    // What is under the cursor, in the drop matrix's terms. Returns one of
    //   { kind: 'dock' }
    //   { kind: 'run', layerId, num, socaIndex? }   (single-item drags)
    //   { kind: 'screen', layerId }                 (whole-unit drags)
    // or null. Whole-unit drags land screen-wide by design, so a panel hit
    // normalizes to its owner screen for them.
    _dockHitTest(ev, drag) {
        const dock = document.getElementById('hardware-dock');
        if (dock && !dock.classList.contains('view-hidden')) {
            const r = dock.getBoundingClientRect();
            if (ev.clientX >= r.left && ev.clientX <= r.right
                    && ev.clientY >= r.top && ev.clientY <= r.bottom) {
                const t = drag.payload.type;
                return (t === 'port' || t === 'slot') ? { kind: 'dock' } : null;
            }
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas) return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (ev.clientX < rect.left || ev.clientX > rect.right
                || ev.clientY < rect.top || ev.clientY > rect.bottom) {
            return null;
        }
        // The same client-to-world walk every canvas gesture does, mirror
        // included - a drop in the mirrored rear view must land on the panel
        // the cursor is over, not its reflection.
        const worldY = ((ev.clientY - rect.top) - renderer.panY)
            / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((ev.clientX - rect.left) - renderer.panX) / renderer.zoom,
            worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        const whole = drag.payload.type !== 'port'
            && drag.payload.type !== 'slot';

        if (renderer.viewMode === 'data-flow') {
            if (hit && drag.dataMap && drag.dataMap.has(hit.panel)) {
                const run = drag.dataMap.get(hit.panel);
                return whole
                    ? { kind: 'screen', layerId: run.ownerId }
                    : { kind: 'run', layerId: run.ownerId, num: run.portNum };
            }
            if (whole) {
                // Any layer under the cursor is a target, screen or not: the
                // drop matrix refuses non-screens with a reason, which tells
                // the user more than a drop that silently does nothing.
                const layer = renderer.getLayerAt(worldX, worldY);
                if (layer) return { kind: 'screen', layerId: layer.id };
            }
            return null;
        }
        if (renderer.viewMode === 'power') {
            if (hit) {
                const layer = (this.project.layers || [])
                    .find(l => l.id === hit.layerId);
                const circuit = layer
                    ? renderer._powerCircuitForPanel(layer, hit.panel) : null;
                if (circuit) {
                    if (whole) {
                        return { kind: 'screen', layerId: circuit.owner.id };
                    }
                    const slot = this._powerNaming(circuit.owner)
                        .slots.get(circuit.circuitNum);
                    if (slot) {
                        return {
                            kind: 'run', layerId: circuit.owner.id,
                            num: circuit.circuitNum, socaIndex: slot.multi,
                        };
                    }
                }
            }
            if (whole) {
                // Any layer under the cursor is a target, screen or not: the
                // drop matrix refuses non-screens with a reason, which tells
                // the user more than a drop that silently does nothing.
                const layer = renderer.getLayerAt(worldX, worldY);
                if (layer) return { kind: 'screen', layerId: layer.id };
            }
            return null;
        }
        return null;
    }

    // Which panel belongs to which port of which screen, frozen at pickup.
    // The data view recomputes its runs every frame and retains nothing, so
    // the dock derives the same picture once per drag from the same single
    // implementation (calculatePortAssignments / the drawn custom paths) and
    // keys it by panel identity - group peers' cabinets arrive as the
    // owner's own items, so a drop on a peer lands on the owner's run.
    _dockBuildDataMap() {
        const map = new Map();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            if (layer.visible === false) continue;
            if ((layer.flowPattern || 'tl-h') === 'custom'
                    && layer.customPortPaths) {
                Object.keys(layer.customPortPaths).forEach(numStr => {
                    const num = parseInt(numStr, 10);
                    (layer.customPortPaths[numStr] || []).forEach(pos => {
                        const panel = (layer.panels || []).find(
                            p => p.row === pos.row && p.col === pos.col);
                        if (panel && !panel.hidden) {
                            map.set(panel,
                                    { ownerId: layer.id, portNum: num });
                        }
                    });
                });
                continue;
            }
            const items = typeof this.calculatePortAssignments === 'function'
                ? this.calculatePortAssignments(layer) : [];
            items.forEach(item => {
                if (item && item.panel && !item.panel.hidden) {
                    map.set(item.panel,
                            { ownerId: layer.id, portNum: item.port });
                }
            });
        }
        return map;
    }

    // ── the drop matrix ───────────────────────────────────────────────────

    _dockPerformDrop(payload, target) {
        sendClientLog('dock_drop', { payload, target });
        if (payload.type === 'port') return this._dockDropPort(payload, target);
        if (payload.type === 'card' || payload.type === 'box') {
            return this._dockDropCardOrBox(payload, target);
        }
        if (payload.type === 'slot') return this._dockDropSlot(payload, target);
        if (payload.type === 'distro') {
            return this._dockDropDistro(payload, target);
        }
    }

    _dockDropPort(payload, target) {
        if (target.kind === 'run') {
            // The same request, question and undo entry the panels' Place
            // buttons sent: this plugs in there.
            return this._placePort({
                layerId: String(target.layerId),
                index: target.num - 1,
                cardId: payload.cardId,
                port: payload.port,
            });
        }
        if (target.kind === 'dock') {
            const all = this._portOccupants(payload.cardId, payload.port);
            // A mirrored return is not a claim of its own: it follows the
            // main, so the release is refused HERE, pointed at the socket
            // where clearing actually lands.
            const occupants = all.filter(o => !o.role);
            if (!occupants.length) {
                const back = all.find(o => o.role === 'return');
                if (back) this._dockSay(this._returnFollowsNote(payload, back));
                return;
            }
            const pinned = occupants.filter(o => o.source === 'pin');
            if (!pinned.length) {
                this._dockSay(
                    `${occupants[0].name} is numbered automatically - there `
                    + 'is no pin to release. Turn off auto-numbering to '
                    + 'empty the port.');
                return;
            }
            // One release per claimant, one history entry for the gesture:
            // the snapshot is taken after the last request lands, so a
            // single Ctrl+Z empties the socket back to how it was.
            let chain = Promise.resolve();
            pinned.forEach((o, i) => {
                chain = chain.then(() => this._assignmentRequest(
                    '/api/port-assignments/unpin', 'POST',
                    { layerId: o.layerId, index: o.number - 1 },
                    null, i === pinned.length - 1 ? 'Release Port' : null));
            });
            return chain;
        }
    }

    _dockDropCardOrBox(payload, target) {
        if (target.kind !== 'screen') return;
        if (payload.type === 'box' && payload.beyondTrunks) {
            // The same fact the Processors panel prints on the box's info
            // line: with no trunk feeding it, its ports are not delivered.
            this._dockSay(`${payload.title} has no trunk on its card - its `
                + 'ports are not delivered, so nothing can land on them.');
            return;
        }
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(target.layerId));
        if (!scr) {
            this._dockSay('That screen needs no ports.');
            return;
        }
        const window_ = payload.type === 'box'
            ? { firstPort: payload.first, lastPort: payload.last } : {};
        if (scr.unplaced.length) {
            // "In order from the first unassigned" - the existing overflow
            // fill: spare screen ports, in order, onto the lowest free
            // sockets (of the box's span, for a box).
            return this._takeOffer(Object.assign({
                action: 'place-overflow', layerId: scr.layerId,
                cardId: payload.cardId,
            }, window_));
        }
        // Nothing unassigned: the gesture means "this screen goes on this
        // hardware", which is the existing whole-block move.
        return this._takeOffer(Object.assign({
            action: 'move-block', layerId: scr.layerId,
            cardId: payload.cardId,
        }, window_));
    }

    _dockDropSlot(payload, target) {
        if (target.kind === 'run') {
            const layer = (this.project.layers || [])
                .find(l => l.id === target.layerId);
            if (!layer) return;
            // WHICH circuit of the multi took the drop decides the gesture:
            // the first circuit means the whole multi (as it always has),
            // and a later circuit means "from here on, feed from this box"
            // - the split the sidebar's Split select used to spell out,
            // implied by where the drop landed (splitSocaOnto, one undo
            // entry for the boundary and the assignment together).
            const rec = this._powerNaming(layer).socas.get(target.socaIndex);
            const at = rec ? rec.circuits.indexOf(target.num) : -1;
            if (rec && at > 0) {
                const label = this.getPowerCircuitLabel(layer, target.num);
                const r = this.splitSocaOnto(
                    layer, target.socaIndex, at,
                    payload.distroId, payload.number);
                if (!r.ok) {
                    // The place-overflow refusal, in tails: a box with no
                    // free tail takes nothing, and the split does not
                    // happen for nothing.
                    this._dockSay(`${payload.title} has no free tails - `
                        + `the ${r.tailLen} circuit`
                        + `${r.tailLen === 1 ? '' : 's'} from ${label} on `
                        + `stay with ${rec.name || 'their multi'}.`);
                    return;
                }
                if (r.took < r.tailLen) {
                    // Take-what-fits, said out loud - the same convention
                    // place-overflow follows with spare ports.
                    this._dockSay(`${payload.title} had ${r.free} free `
                        + `tail${r.free === 1 ? '' : 's'} - took ${r.took} `
                        + `of the ${r.tailLen} circuits from ${label} on; `
                        + 'the rest stay as their own unassigned multi.');
                }
                this._restateNaming();
                return;
            }
            // The two existing setters, in the canonical order the panel's
            // selects fired them: distro first (a number means nothing off a
            // distro), then the pin. Landing on an occupied slot is the join
            // gesture, exactly as picking the number was - the incumbents'
            // tails freeze and this multi deals into what is free.
            const current = (layer.powerSocaDistro || {})[target.socaIndex];
            if (current !== payload.distroId) {
                this.setSocaDistro(layer, target.socaIndex, payload.distroId);
            }
            this.setSocaNumber(layer, target.socaIndex, payload.number);
            this._restateNaming();
            return;
        }
        if (target.kind === 'dock') {
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) return;
            // Unassign every multi the chip names - the chip is the box, and
            // pulling the box off the wall pulls all its feeds. Same two
            // setters the panel's selects drove, so the entries undo the way
            // every other power edit does.
            members.forEach(m => {
                const layer = (this.project.layers || [])
                    .find(l => l.id === m.layerId);
                if (!layer) return;
                this.setSocaNumber(layer, m.soca, null);
                this.setSocaDistro(layer, m.soca, null);
            });
            this._restateNaming();
        }
    }

    _dockDropDistro(payload, target) {
        if (target.kind !== 'screen') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        if ((layer.type || 'screen') !== 'screen') {
            this._dockSay(`${layer.name || 'That layer'} draws no power.`);
            return;
        }
        const plan = this.getSocaPlan(layer);
        const unassigned = plan.filter(s => !s.distroId);
        if (!unassigned.length) {
            this._dockSay(plan.length
                ? `Every multi on ${layer.name} already has a distro. Drag a `
                    + 'slot onto a circuit to move one, or drag it back onto '
                    + 'the tray to unassign it.'
                : `${layer.name} has no circuits to feed.`);
            return;
        }
        // The existing per-multi assignment, once per unassigned multi, in
        // plan order - the numbers fall out of the distro's own sequence.
        unassigned.forEach(s => {
            this.setSocaDistro(layer, s.soca, payload.distroId);
        });
        this._restateNaming();
    }

    // ── the right-click clears ────────────────────────────────────────────
    //
    // What the context menu's "Clear …" item should be for the point that was
    // right-clicked, or null when the click landed on nothing clearable (the
    // item then stays off the menu entirely). Returns { label, title, run }
    // for a clear that can happen, { label, title, disabled: true } for one
    // that cannot - disabled WITH the reason as the title, because "greyed
    // out and silent" teaches nothing.
    //
    // Every clear here runs the release operations the dock's drag-back runs,
    // and confirms nothing: clearing is undoable and touches only the
    // assignment - names, templates and the hardware itself stay.
    _prepareClearMenu(x, y) {
        // The dock chip under the cursor first: chips carry their payload on
        // the element, and the tray sits outside the canvas so the two tests
        // cannot both hit.
        const el = document.elementFromPoint(x, y);
        const chip = el && el.closest
            ? el.closest('[data-hwdock-payload]') : null;
        if (chip) {
            let payload = null;
            try {
                payload = JSON.parse(chip.dataset.hwdockPayload);
            } catch (_) { /* a chip with unreadable payload arms nothing */ }
            return payload ? this._clearMenuForDock(payload) : null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas) return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        // The same client-to-world walk every canvas gesture does, mirror
        // included - the clear must land on the run under the cursor, not
        // its reflection.
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        if (renderer.viewMode === 'data-flow') {
            return this._clearMenuForDataRun(hit);
        }
        if (renderer.viewMode === 'power') {
            return this._clearMenuForCircuit(hit);
        }
        return null;
    }

    // A drawn port run in Data view: clear = release that screen-port's pin,
    // the same unpin the panel's release buttons and the drag-back send.
    _clearMenuForDataRun(hit) {
        const run = this._dockBuildDataMap().get(hit.panel);
        if (!run) return null;
        const layer = (this.project.layers || [])
            .find(l => l.id === run.ownerId);
        // The label the run is drawn with, so the menu names what the user
        // is looking at - SR-3 when a card names it, P3 off the template.
        const label = (layer && typeof this.getPortLabelText === 'function'
            && this.getPortLabelText(layer, run.portNum))
            || `port ${run.portNum}`;
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(run.ownerId));
        const port = scr
            && (scr.ports || []).find(p => p.number === run.portNum);
        if (!port || !port.cardId) {
            return {
                label: `Clear port ${label}`, disabled: true,
                title: `${label} is not on a sending card - there is `
                    + 'nothing to clear.',
            };
        }
        if (port.source !== 'pin') {
            // The drag-back rule, said before the gesture instead of after.
            return {
                label: `Clear port ${label}`, disabled: true,
                title: `${label} is numbered automatically - there is no pin `
                    + 'to release. Turn off auto-numbering to empty the port.',
            };
        }
        return {
            label: `Clear port ${label}`,
            title: 'Hand this port back to auto-numbering. Names and '
                + 'templates are untouched, and undo puts it back.',
            run: () => {
                sendClientLog('dock_clear', { kind: 'run',
                    layerId: scr.layerId, index: port.index });
                return this._assignmentRequest(
                    '/api/port-assignments/unpin', 'POST',
                    { layerId: scr.layerId, index: port.index },
                    null, 'Release Port');
            },
        };
    }

    // A drawn circuit run in Power view: clear = un-assign that circuit's
    // multi, number then distro, the drag-back semantics in one gesture.
    _clearMenuForCircuit(hit) {
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        const circuit = under && window.canvasRenderer
            ? window.canvasRenderer._powerCircuitForPanel(under, hit.panel)
            : null;
        if (!circuit) return null;
        const owner = circuit.owner;
        const nm = this._powerNaming(owner);
        const slot = nm.slots.get(circuit.circuitNum);
        const rec = slot ? nm.socas.get(slot.multi) : null;
        if (!rec) return null;
        const name = rec.name || `multi ${rec.number}`;
        if (!rec.distroId) {
            return {
                label: `Clear multi ${name}`, disabled: true,
                title: `${name} is not on a distro - there is nothing to `
                    + 'clear.',
            };
        }
        return {
            label: `Clear multi ${name}`,
            title: 'Unassign this multi - its number, then its distro. '
                + 'Names are untouched, and undo puts it back.',
            run: () => this._clearMultis(
                [{ layerId: owner.id, soca: rec.index }], 'Clear Multi'),
        };
    }

    // ── the right-click merge-back ────────────────────────────────────────
    //
    // The reverse of the drop-implied split. With the sidebar's Un-split
    // button gone, the way back is the same surface the split now lives on:
    // right-click the circuit run (or the slot chip holding the split-off
    // part) and "Merge back into <name>" removes the stored boundary
    // through the existing un-split - undoable, like every clear above.
    // Unlike the clear there is no disabled state: a multi with no stored
    // boundary simply has nothing to merge, which is its ordinary condition,
    // not a refused gesture - so the item stays off the menu entirely.
    _prepareMergeMenu(x, y) {
        const el = document.elementFromPoint(x, y);
        const chip = el && el.closest
            ? el.closest('[data-hwdock-payload]') : null;
        if (chip) {
            let payload = null;
            try {
                payload = JSON.parse(chip.dataset.hwdockPayload);
            } catch (_) { /* a chip with unreadable payload arms nothing */ }
            if (!payload || payload.type !== 'slot') return null;
            // The chip is the box, so it offers to hand back only a
            // SPLIT-OFF part it holds - a head member whose tail lives on
            // another box is that other surface's merge, not this chip's.
            for (const m of (this._distroMultiNumbers(payload.distroId)
                    .get(payload.number) || [])) {
                const layer = (this.project.layers || [])
                    .find(l => l.id === m.layerId);
                if (!layer) continue;
                const offer = this._mergeMenuForMulti(layer, m.soca, true);
                if (offer) return offer;
            }
            return null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas
                || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        // The same client-to-world walk _prepareClearMenu makes, mirror
        // included, for the same reason.
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        const circuit = under
            ? renderer._powerCircuitForPanel(under, hit.panel) : null;
        if (!circuit) return null;
        const slot = this._powerNaming(circuit.owner)
            .slots.get(circuit.circuitNum);
        return slot
            ? this._mergeMenuForMulti(circuit.owner, slot.multi, false)
            : null;
    }

    // The merge offer for one multi, or null when no stored boundary
    // touches it. The clicked part can sit on either side of the boundary:
    // the split-off TAIL merges back into the part before it, and the HEAD
    // takes its split-off tail back - the surviving multi is the head
    // either way (unsplitSocaAfter's rule), so the label names it.
    // `tailOnly` restricts to the tail side, for surfaces that hold the
    // split-off part specifically (the slot chip).
    _mergeMenuForMulti(layer, socaIndex, tailOnly) {
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const idx = Number(socaIndex);
        const seg = segs.find(s => s.index === idx);
        if (!seg) return null;
        const prev = segs.find(s => s.index === idx - 1);
        const headIdx = (prev && prev.userEnd) ? prev.index
            : (!tailOnly && seg.userEnd ? seg.index : null);
        if (headIdx == null) return null;
        const head = this._powerNaming(layer).socas.get(headIdx);
        const name = (head && head.name) || `multi ${headIdx}`;
        return {
            label: `Merge back into ${name}`,
            title: 'Remove the split boundary: the circuits fall back into '
                + `one multi under ${name}, and the split-off part's `
                + 'assignment goes with its identity. Undo puts the split '
                + 'back.',
            run: () => {
                sendClientLog('dock_merge',
                              { layerId: layer.id, soca: headIdx });
                this.unsplitSocaAfter(layer, headIdx);
                this._restateNaming();
            },
        };
    }

    // A dock chip: the same clears, from the hardware end of the cable.
    _clearMenuForDock(payload) {
        if (payload.type === 'port') {
            const label = `Clear ${payload.title}`;
            const all = this._portOccupants(payload.cardId, payload.port);
            const occupants = all.filter(o => !o.role);
            if (!occupants.length) {
                // A backup socket carrying a mirrored return refuses by the
                // role, naming the screen and the main the display follows
                // - "free" would deny exactly what the tile shows.
                const back = all.find(o => o.role === 'return');
                if (back) {
                    return {
                        label, disabled: true,
                        title: this._returnFollowsNote(payload, back),
                    };
                }
                // An idle backup socket is not "free" either - it is
                // role-claimed and just carrying no return yet, and its
                // own tile says so; the menu must not contradict it.
                const rp = this._dockResolvedPort(payload.cardId,
                                                  payload.port);
                if (rp && rp.backsUp) {
                    return {
                        label, disabled: true,
                        title: `${payload.title} backs up ${rp.backsUp.label
                            || `port ${rp.backsUp.port}`} - it is that `
                            + 'port\'s return end and holds no claim of '
                            + 'its own.',
                    };
                }
                return {
                    label, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            const pinned = occupants.filter(o => o.source === 'pin');
            if (!pinned.length) {
                return {
                    label, disabled: true,
                    title: `${occupants[0].name} is numbered automatically - `
                        + 'there is no pin to release. Turn off '
                        + 'auto-numbering to empty the port.',
                };
            }
            return {
                label,
                title: 'Release the pinned claim on this socket back to '
                    + 'auto-numbering. Undo puts it back.',
                run: () => {
                    sendClientLog('dock_clear', { kind: 'port', payload });
                    return this._dockReleasePins(
                        pinned.map(o => ({ layerId: o.layerId,
                                           index: o.number - 1 })),
                        'Release Port');
                },
            };
        }
        if (payload.type === 'card' || payload.type === 'box') {
            const label = `Clear ${payload.title}`;
            const first = payload.type === 'box' ? payload.first : -Infinity;
            const last = payload.type === 'box' ? payload.last : Infinity;
            const pins = [];
            ((this._assignment && this._assignment.screens) || [])
                .forEach(scr => (scr.ports || []).forEach(p => {
                    if (p.source === 'pin' && p.cardId === payload.cardId
                            && p.port >= first && p.port <= last) {
                        pins.push({ layerId: scr.layerId, index: p.index });
                    }
                }));
            if (!pins.length) {
                return {
                    label, disabled: true,
                    title: `${payload.title} holds no pins - its occupied `
                        + 'ports are numbered automatically, and there is no '
                        + 'pin to release.',
                };
            }
            return {
                label,
                title: `Release every pin on ${payload.title} back to `
                    + 'auto-numbering, as one undoable step.',
                run: () => {
                    sendClientLog('dock_clear',
                                  { kind: payload.type, payload,
                                    count: pins.length });
                    return this._dockReleasePins(pins, 'Release Ports');
                },
            };
        }
        if (payload.type === 'slot') {
            const label = `Clear ${payload.title}`;
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) {
                return {
                    label, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            return {
                label,
                title: 'Unassign every multi on this slot - the chip is the '
                    + 'box, and clearing the box takes all its feeds. One '
                    + 'undoable step.',
                run: () => this._clearMultis(
                    members.map(m => ({ layerId: m.layerId, soca: m.soca })),
                    'Clear Multi'),
            };
        }
        if (payload.type === 'distro') {
            const label = `Clear ${payload.title}`;
            const members = [];
            for (const l of (this.project.layers || [])) {
                if ((l.type || 'screen') !== 'screen') continue;
                for (const rec of this._powerNaming(l).socas.values()) {
                    if (rec.distroId === payload.distroId) {
                        members.push({ layerId: l.id, soca: rec.index });
                    }
                }
            }
            if (!members.length) {
                return {
                    label, disabled: true,
                    title: `No multis are assigned to ${payload.title} - `
                        + 'there is nothing to clear.',
                };
            }
            return {
                label,
                title: `Unassign every multi on ${payload.title}, as one `
                    + 'undoable step.',
                run: () => this._clearMultis(members, 'Clear Distro'),
            };
        }
        return null;
    }

    // One release per pin, ONE history entry for the gesture - the snapshot
    // rides the last request the way the drag-back's does, so a single
    // Ctrl+Z puts the whole card back.
    _dockReleasePins(pins, action) {
        let chain = Promise.resolve();
        pins.forEach((p, i) => {
            chain = chain.then(() => this._assignmentRequest(
                '/api/port-assignments/unpin', 'POST',
                { layerId: p.layerId, index: p.index },
                null, i === pins.length - 1 ? action : null));
        });
        return chain;
    }

    // Un-assign a set of multis - number, then distro, the order the panel's
    // selects always fired - as ONE gesture with ONE history entry: a
    // distro-level clear is one decision, and Ctrl+Z must put every feed
    // back at once. The deletions mirror setSocaNumber(null) /
    // setSocaDistro(null) exactly, minus their per-call snapshots; the
    // objects are always left behind, never the properties deleted whole -
    // an absent key is missing from the update payload and the server keeps
    // whatever it had, so "cleared" would silently not clear.
    _clearMultis(members, action) {
        sendClientLog('dock_clear', { kind: 'multis', action,
                                      count: members.length });
        const touched = [];
        members.forEach(m => {
            const layer = (this.project.layers || [])
                .find(l => l.id === m.layerId);
            if (!layer) return;
            const nums = layer.powerSocaNumber
                || (layer.powerSocaNumber = {});
            delete nums[m.soca];
            const dist = layer.powerSocaDistro
                || (layer.powerSocaDistro = {});
            delete dist[m.soca];
            touched.push(layer);
        });
        if (!touched.length) return;
        // Un-assignment renumbers both buckets it touches, so every label
        // on the show can move - same cache drop the setters make.
        this._circuitTailCache = null;
        this.updateLayers([...new Set(touched)], true, action);
        this._restateNaming();
    }

    // One resolved port off the same tree the tiles drew, so a menu can
    // read the role facts (backsUp) the occupancy alone cannot carry.
    _dockResolvedPort(cardId, number) {
        for (const proc of this._processorsResolved || []) {
            for (const slot of proc.slots || []) {
                const card = slot.card;
                if (card && card.id === cardId) {
                    return (card.ports || [])
                        .find(p => p.number === number) || null;
                }
            }
        }
        return null;
    }

    // The one sentence every refusal on a mirrored backup socket says:
    // whose return the socket carries, and where the clear actually lands.
    // The display is derived - it follows the main through the backup link
    // - so the main is the only thing there is to clear.
    _returnFollowsNote(payload, occupant) {
        const main = occupant.main || {};
        const mainName = main.label
            || (main.port ? `port ${main.port}` : 'its main port');
        return `${payload.title} carries ${occupant.name} `
            + `p${occupant.number}'s return - it follows ${mainName}; `
            + 'clear that port to clear both ends.';
    }

    // A refusal the server never saw still deserves a sentence somewhere
    // visible; the status bar is the one strip that exists in every view.
    _dockSay(text) {
        const el = document.getElementById('status-message');
        if (!el) return;
        el.textContent = text;
        clearTimeout(this._dockSayTimer);
        this._dockSayTimer = setTimeout(() => {
            el.textContent = 'Ready';
        }, 6000);
    }
}

for (const k of Object.getOwnPropertyNames(_HardwareDock.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_HardwareDock.prototype, k));
    }
}
