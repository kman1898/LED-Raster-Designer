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
        // The dock folds by the standard section machinery (the markup is a
        // .lrd-sec-head/.lrd-sec-body pair initSectionCollapse already
        // wired), but that machinery knows nothing about the canvas - and a
        // tray leaving or entering the flex column changes the height the
        // canvas has to fill, exactly like a sidebar changing width. Watch
        // the class rather than re-implementing the toggle.
        if (typeof MutationObserver === 'function') {
            let folded = dock.classList.contains('lrd-sec-collapsed');
            new MutationObserver(() => {
                const now = dock.classList.contains('lrd-sec-collapsed');
                if (now !== folded) {
                    folded = now;
                    this.settleLayout();
                }
            }).observe(dock, { attributes: true, attributeFilter: ['class'] });
        }
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
        procs.forEach(proc => {
            const wrap = document.createElement('div');
            wrap.className = 'hw-dock-proc';
            const title = document.createElement('div');
            title.className = 'hw-dock-proc-name';
            title.textContent = proc.name || proc.deviceName;
            wrap.appendChild(title);
            (proc.slots || []).forEach(slot => {
                if (!slot.card) return;
                wrap.appendChild(this._dockBuildCard(proc, slot.card));
            });
            host.appendChild(wrap);
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
            unit.appendChild(box);
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
        } else {
            who.style.color = '#999';
            who.textContent = occupants[0].name;
        }
        face.appendChild(who);
        tile.appendChild(face);

        face.title = `Port ${port.number}`
            + (port.label ? ` - ${port.label}` : '')
            + (occupants.length
                ? ` - ${occupants.map(o => `${o.name} p${o.number}`).join(', ')}`
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
            const occupants = this._portOccupants(payload.cardId, payload.port);
            if (!occupants.length) return;
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
