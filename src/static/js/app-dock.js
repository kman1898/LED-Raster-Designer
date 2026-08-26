// app-dock: the hardware dock, a tray under the canvas that holds the view's
// hardware and makes DRAG the way assignments are made.
//
// The Signal and Power panels stay the place hardware is named, inspected and
// templated; the dock is the place it is AIMED. Data view lays out every
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
//     existing join gesture, exactly as picking the number was;
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
        // Remember which tile held focus through the wipe, by its stable key
        // - the same reason the panels carry data-lrd-field. Dock tiles are
        // plain drag handles, so the key is all there is to restore.
        const focused = document.activeElement
            && document.activeElement.dataset
            && document.activeElement.dataset.hwdock;
        const before = dock.offsetHeight;
        body.innerHTML = '';
        if (mode === 'data-flow') this._dockRenderData(body);
        else if (mode === 'power') this._dockRenderPower(body);
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
            unit.appendChild(this._dockBuildPortGrid(card, loose));
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
            box.appendChild(this._dockBuildPortGrid(card, cvt.ports || []));
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

    _dockBuildPortGrid(card, ports) {
        const grid = document.createElement('div');
        grid.className = 'lrd-tile-grid hw-dock-grid';
        ports.forEach(port => {
            grid.appendChild(this._dockBuildPortTile(card, port));
        });
        return grid;
    }

    // The same compact face the Processors panel's tiles wear - number,
    // label, occupant, the occupied/clash ground - shrunk to a drag handle.
    // No editor unfolds here; naming stays in the panel.
    _dockBuildPortTile(card, port) {
        const tile = document.createElement('div');
        tile.className = 'lrd-tile hw-dock-tile';
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
            + (port.backsUp
                ? '. A backup port is that port\'s return end - nothing '
                    + 'else can land on it.'
                : '. Drag onto a port run to place it there'
                    + (occupants.some(o => o.source === 'pin')
                        ? '; drag back onto this tray to release it.' : '.'));

        this._dockWireDraggable(face, {
            type: 'port', cardId: card.id, port: port.number,
            title: port.label || `${card.name || card.deviceName} `
                + `port ${port.number}`,
        }, `port-${card.id}-${port.number}`);
        return tile;
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

        // Free tails: six minus every tail a member's rendering holds. Over
        // six legs on one box is the overflow the soca tiles flag - the chip
        // wears the same clash ground.
        const used = new Set();
        let legs = 0;
        members.forEach(m => {
            const l = (this.project.layers || []).find(x => x.id === m.layerId);
            if (!l) return;
            const rec = this._powerNaming(l).socas.get(m.soca);
            if (rec) (rec.positions || []).forEach(t => used.add(t));
            legs += m.legs || 0;
        });
        const free = [1, 2, 3, 4, 5, 6].filter(t => !used.has(t));
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
        tile.appendChild(face);

        face.title = `${d.name || d.id} multi ${n} - `
            + (members.length
                ? `${members.map(m => m.layerName).join(' and ')}, `
                    + (free.length
                        ? `tails ${this._fmtTails(free)} free`
                        : 'no tails free')
                : 'free')
            + '. Drag onto a circuit to land that circuit\'s multi here'
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
                // drag - same latitude every drag on the canvas gives.
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
            if (live) this._dockEndDrag(ev);
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
