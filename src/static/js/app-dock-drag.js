// app-dock-drag: the dock's pointer-based drag engine - reordering
// processors and distros within the tray, the arm/start/move/end lifecycle,
// hit-testing over the canvas, the drop plans and refusals for plugs and
// boxes, and every _dockDrop* that performs an assignment through the shared
// operations. Moved verbatim out of app-dock.js and attached to the
// prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _DockDrag {
    // ── reorder by drag (2026-09-09) ─────────────────────────────────────
    //
    // "also being able to drag them around and reorder them would be nice
    // too". The things that reorder are the two the tray is a list OF: the
    // processors (data) and the distros (power). A card inside a processor
    // is not one of them - its slot is where the metal is - and a
    // designated backup rides with the main it backs, because a redundant
    // pair is one thing everywhere else too.

    // The reorderable items of the current view, in STORED order: the
    // tray's top-level cells on the data side (a cell is a processor wrap
    // or a pair wrapper), the distro units on the power side (which the
    // column deal spreads across cells, so the cells are not the list).
    _dockReorderItems() {
        const body = document.getElementById('hardware-dock-body');
        if (!body) return [];
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : '';
        if (mode === 'power') {
            const byId = new Map(
                [...body.querySelectorAll('[data-lrd-distro]')]
                    .map(el => [el.dataset.lrdDistro, el]));
            return (typeof this.getDistros === 'function'
                ? this.getDistros() : [])
                .map(d => byId.get(d.id)).filter(Boolean);
        }
        return [...body.children].filter(el => el.classList
            && !el.classList.contains('hw-dock-drop-mark')
            && !el.classList.contains('hw-dock-note'));
    }

    // Which gap the cursor is nearest, as an insertion index: every item's
    // leading edge is a candidate, plus the trailing edge of the last. One
    // rule for both layouts (a wrapped grid of processors, stacked columns
    // of distros) - the nearest gap wins, so "drop it left of that one"
    // reads the same either way.
    _dockReorderIndex(ev) {
        const items = this._dockReorderItems();
        if (!items.length) return 0;
        let best = 0;
        let bestD = Infinity;
        const consider = (i, x, y) => {
            const d = Math.hypot(ev.clientX - x, ev.clientY - y);
            if (d < bestD) { bestD = d; best = i; }
        };
        items.forEach((el, i) => {
            const r = el.getBoundingClientRect();
            consider(i, r.left, r.top + r.height / 2);
        });
        const last = items[items.length - 1].getBoundingClientRect();
        consider(items.length, last.right, last.top + last.height / 2);
        return best;
    }

    // The 3px accent bar in the gap the drop would land in.
    _dockMarkReorder(index) {
        const body = document.getElementById('hardware-dock-body');
        if (!body) return;
        const items = this._dockReorderItems();
        let mark = body.querySelector(':scope > .hw-dock-drop-mark');
        if (!items.length) {
            if (mark) mark.remove();
            return;
        }
        if (!mark) {
            mark = document.createElement('div');
            mark.className = 'hw-dock-drop-mark';
            body.appendChild(mark);
        }
        const after = index >= items.length;
        const el = items[after ? items.length - 1 : index];
        mark.style.top = `${el.offsetTop}px`;
        mark.style.height = `${el.offsetHeight}px`;
        mark.style.left = `${after
            ? el.offsetLeft + el.offsetWidth + 3 : el.offsetLeft - 6}px`;
        mark.dataset.lrdIndex = String(index);
    }

    _dockClearReorderMark() {
        const body = document.getElementById('hardware-dock-body');
        const mark = body && body.querySelector(':scope > .hw-dock-drop-mark');
        if (mark) mark.remove();
    }

    // The processor ids a top-level cell holds, in the order it holds them
    // - one for a lone processor, main then backup for a pair.
    _dockCellProcIds(cell) {
        return [...cell.querySelectorAll('[data-hwdock^="processor-"]')]
            .map(el => el.dataset.hwdock.slice('processor-'.length));
    }

    // Move a processor (with its pair, if it is in one) to a cell index.
    // The stored order is the one thing that changes: the tray, the pull
    // list's hardware order and the binder's 'data' screen order all read
    // it, so one PUT moves the lot. ONE 'Reorder Processors' entry.
    _dockReorderProcessors(procId, index) {
        const groups = this._dockReorderItems()
            .map(cell => this._dockCellProcIds(cell))
            .filter(g => g.length);
        const gi = groups.findIndex(g => g.includes(procId));
        if (gi < 0) return null;
        const before = [].concat(...groups);
        const moving = groups[gi];
        const rest = groups.filter((_, i) => i !== gi);
        const to = Math.max(0, Math.min(rest.length,
                                        index > gi ? index - 1 : index));
        rest.splice(to, 0, moving);
        const ids = [].concat(...rest);
        if (ids.length === before.length
                && ids.every((id, i) => id === before[i])) return null;
        return this._processorRequest('/api/processors/order', 'PUT',
                                      { ids }, 'Reorder Processors');
    }

    // The distros live on the project, so their order rides the project's
    // own push and the project-wide snapshot - the same path every other
    // distro edit takes. ONE 'Reorder Distros' entry.
    _dockReorderDistros(distroId, index) {
        const list = this.getDistros();
        const from = list.findIndex(d => d.id === distroId);
        if (from < 0) return;
        const next = list.slice();
        const [moved] = next.splice(from, 1);
        const to = Math.max(0, Math.min(next.length,
                                        index > from ? index - 1 : index));
        next.splice(to, 0, moved);
        if (next.every((d, i) => d.id === list[i].id)) return;
        this.project.distros = next;
        this._circuitTailCache = null;
        this._persistDistros();
        this.saveState('Reorder Distros');
        this.renderHardwareDock();
        if (window.canvasRenderer) window.canvasRenderer.render();
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
            // The headers carry live controls now - the inline name field,
            // the gear, Balance - and a press on one is that control's
            // gesture, not a drag pickup: preventDefault here would eat the
            // click that focuses the input or opens the popover.
            if (e.target !== el && e.target.closest
                    && e.target.closest('input, select, button, textarea')) {
                return;
            }
            e.preventDefault();
            // Alt+press on a port chip ARMS the tray sweep - the gesture
            // the canvas 2fer taught, transposed ("B to form it",
            // 2026-09-06) - never a drag: dragging is placement, and a
            // snake moves nothing, it only names the run the ports share.
            if (e.altKey && payload.type === 'port') {
                this._traySweepStart(e, payload, el);
                return;
            }
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
        // Escape mid-drag cancels: the chip goes home, no drop, nothing
        // said - the same way out every canvas gesture offers.
        const key = (ke) => {
            if (ke.key !== 'Escape') return;
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            document.removeEventListener('keydown', key, true);
            if (live) {
                this._dockDropTarget = null;
                this._dockEndDrag(ke);
            }
        };
        const up = (ev) => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            document.removeEventListener('keydown', key, true);
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
        document.addEventListener('keydown', key, true);
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
        if (payload.type === 'plug'
                || (payload.type === 'slot' && payload.output)) {
            // The chip itself rides the cursor - the connector is the
            // thing being carried, so the ghost wears its face. A typed
            // spare box is that plug with a number on it.
            const t = this.getDistroOutputTypes()
                .find(x => x.id === payload.output);
            if (t) {
                ghost.textContent = '';
                ghost.classList.add('hw-dock-ghost-plug');
                const chip = this._plugChip(t, true);
                if (payload.type === 'slot') {
                    chip.querySelector('b').textContent =
                        `${payload.title} · ${t.name}`;
                }
                ghost.appendChild(chip);
            }
        }
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
        if (target && target.kind === 'reorder') {
            this._dockMarkReorder(target.index);
        } else {
            this._dockClearReorderMark();
        }
        if (drag.payload.type === 'plug' || drag.payload.output) {
            this._dockPlugPill(drag, ev, target);
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
            if (drag.pill) drag.pill.remove();
            if (drag.source && drag.source.classList) {
                drag.source.classList.remove('hw-dock-dragging');
            }
        }
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        this._dockClearReorderMark();
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
                // A processor's or a distro's own header dragged ALONG the
                // tray is a reorder: the gap it is nearest is the place it
                // lands (2026-09-09). Anything else keeps the tray's one
                // meaning - a chip dropped back on the dock is a clear.
                if (t === 'processor' || t === 'distro') {
                    const body = document.getElementById('hardware-dock-body');
                    const br = body && body.getBoundingClientRect();
                    if (br && ev.clientX >= br.left && ev.clientX <= br.right
                            && ev.clientY >= br.top && ev.clientY <= br.bottom) {
                        return { kind: 'reorder',
                                 index: this._dockReorderIndex(ev) };
                    }
                    return null;
                }
                return (t === 'port' || t === 'slot' || t === 'tail')
                    ? { kind: 'dock' } : null;
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
            && drag.payload.type !== 'slot'
            && drag.payload.type !== 'tail';

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
                        return this._dockScreenTarget(circuit.owner, drag);
                    }
                    const slot = this._powerNaming(circuit.owner)
                        .slots.get(circuit.circuitNum);
                    if (slot) {
                        const target = {
                            kind: 'run', layerId: circuit.owner.id,
                            num: circuit.circuitNum, socaIndex: slot.multi,
                        };
                        // The drop's true reach rides on the target so the
                        // underlay can light everything the release will
                        // touch - the data tab's rule, where a port drop
                        // lights exactly the run it takes. A slot takes
                        // the box cell's circuits from its FIRST up to
                        // the hovered one, as many as the box has room
                        // for (user, 2026-09-05: "start at the 1st
                        // circuit regardless of naming. should just be
                        // in order") - the drop's own resolution
                        // (_socaTakePlan), so what lights is what lands,
                        // and nothing where the drop would refuse; a tail
                        // pip takes the hovered circuit alone.
                        if (drag.payload.type === 'slot'
                                && drag.payload.output) {
                            // A typed spare box: the plug gate first (a
                            // mismatch lights nothing and reddens the
                            // pill with the fix), then the same anchored
                            // take - the drop's own resolution.
                            const ordinal = this.screenCircuits(circuit.owner)
                                .findIndex(c => c.num === circuit.circuitNum)
                                + 1;
                            const plan = this._boxPlanFor(
                                drag, circuit.owner, ordinal);
                            target.nums = plan.ok ? plan.nums.slice() : [];
                            target.plug = plan.ok
                                ? { ok: true, socaIndex: plan.socaIndex,
                                    number: plan.number,
                                    boxName: plan.boxName, badge: plan.badge,
                                    glyph: plan.glyph, text: plan.text,
                                    warn: plan.warn }
                                : { ok: false, glyph: plan.glyph,
                                    message: plan.message };
                        } else if (drag.payload.type === 'slot') {
                            const ordinal = this.screenCircuits(circuit.owner)
                                .findIndex(c => c.num === circuit.circuitNum)
                                + 1;
                            const plan = this._socaTakePlan(
                                circuit.owner, ordinal,
                                drag.payload.distroId, drag.payload.number);
                            target.nums = plan.ok ? plan.nums.slice() : [];
                        } else if (drag.payload.type === 'tail') {
                            target.nums = [circuit.circuitNum];
                        }
                        return target;
                    }
                }
            }
            if (whole) {
                // Any layer under the cursor is a target, screen or not: the
                // drop matrix refuses non-screens with a reason, which tells
                // the user more than a drop that silently does nothing.
                const layer = renderer.getLayerAt(worldX, worldY);
                if (layer) return this._dockScreenTarget(layer, drag);
            }
            return null;
        }
        return null;
    }

    // A screen-wide power target, carrying the drop's true reach for a
    // DISTRO drag: the release feeds only the screen's unassigned multis,
    // so those multis' circuits are what the preview lights - a screen with
    // nothing unassigned lights nothing, which is exactly what the drop
    // would do. Every other whole-unit drag really is screen-wide and
    // carries no `nums`.
    _dockScreenTarget(layer, drag) {
        const target = { kind: 'screen', layerId: layer.id };
        if (drag.payload.type === 'distro'
                && (layer.type || 'screen') === 'screen') {
            // The drop's own gate, per multi (all or nothing, as the drop
            // is): where _dockDropDistro would refuse, nothing lights -
            // the chip path's rule.
            const unassigned = this.getSocaPlan(layer).filter(s => !s.distroId);
            const refused = unassigned.some(
                s => !!this._distroDropRefusal(drag.payload, layer, s));
            target.nums = refused ? []
                : unassigned.flatMap(s => s.legs.map(g => g.circuit));
        }
        if (drag.payload.type === 'plug') {
            // A plug lights EXACTLY the circuits its drop would feed - the
            // drop's own resolution, read once per screen per drag - and
            // nothing at all where the drop would be refused. The pill and
            // the pending bracket read the same record off the target.
            const plan = this._plugPlanFor(drag, layer);
            target.nums = plan.ok ? plan.nums.slice() : [];
            target.plug = plan.ok
                ? { ok: true, socaIndex: plan.socaIndex, number: plan.number,
                    boxName: plan.boxName, badge: plan.badge,
                    glyph: plan.glyph, text: plan.text, warn: plan.warn }
                : { ok: false, glyph: plan.glyph, message: plan.message };
        }
        return target;
    }

    // ── plug drops: one box of one connector type ─────────────────────────
    //
    // The ONE resolution both the preview and the release read, so what
    // lights under the cursor is exactly what the drop assigns (user
    // ruling, 2026-08-31: preview == result). The box is the screen's next
    // unassigned multi in plan order - the split-aware segmentation, so a
    // split-off remainder is its own next box - and its number is what the
    // distro's own sequence would deal it, found by asking the naming
    // index with the assignment tried on (and taken straight back off).
    // Returns
    //   { ok: true, socaIndex, nums, number, boxName, amps, text, badge,
    //     glyph, warn }             - warn: the LEGS-past-rating sentence
    //   { ok: false, message, glyph }
    _plugDropPlan(payload, layer) {
        const gate = this._plugGate(payload, layer);
        if (!gate.ok) return gate;
        const { d, type, glyph } = gate;
        const plan = this.getSocaPlan(layer);
        const s = plan.find(x => !x.distroId);
        if (!s) {
            return { ok: false, glyph,
                     message: plan.length
                        ? `Every multi on ${layer.name} already has a `
                            + 'distro. Drag a slot onto a circuit to move '
                            + 'one, or drag it back onto the tray to '
                            + 'unassign it.'
                        : `${layer.name} has no circuits to feed.` };
        }
        // Dry run: the number this box would get, and where the distro's
        // legs would land with it on - read off the real naming index and
        // the real roll-up with the assignment tried on, then put back
        // exactly as found. The cache is dropped on both sides so no
        // frame reads the trial.
        const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
        const had = Object.prototype.hasOwnProperty.call(map, s.soca);
        const prev = map[s.soca];
        map[s.soca] = d.id;
        this._circuitTailCache = null;
        let number = null;
        let name = null;
        let warn = null;
        try {
            const rec = this._powerNaming(layer).socas.get(s.soca);
            number = rec ? rec.number : null;
            // The box's name as the wall will print it (the naming index's
            // own derivation - "PD1" - or a hand name), so the pending
            // bracket and the committed one read the same.
            name = rec ? rec.name : null;
            const load = (this.getDistroLoads() || [])
                .find(l => l.id === d.id);
            if (load && load.ratingA > 0) {
                if (load.legs) {
                    const worst = Math.max(load.legs.X.amps, load.legs.Y.amps,
                                           load.legs.Z.amps);
                    if (worst > load.ratingA) {
                        warn = `${d.name || d.id} legs to `
                            + `${worst.toFixed(0)} A of ${load.ratingA} A`;
                    }
                } else if (load.amps > load.ratingA) {
                    warn = `${d.name || d.id} to ${load.amps.toFixed(0)} A `
                        + `of ${load.ratingA} A`;
                }
            }
        } finally {
            if (had) map[s.soca] = prev; else delete map[s.soca];
            this._circuitTailCache = null;
        }
        const nums = s.legs.map(g => g.circuit);
        const boxName = name
            || `${d.name || d.id}${number != null ? ` ${number}` : ''}`;
        return {
            ok: true, glyph, socaIndex: s.soca, nums, number, boxName,
            amps: s.amps, badge: type.badge, warn,
            text: `${boxName} → circuit${nums.length === 1 ? '' : 's'} `
                + `${this._fmtTails(nums).replace(/-/g, '–')} · `
                + `${Math.round(s.amps)} A`,
        };
    }

    // The gate every plug-shaped drop passes first - the OUTPUTS chip and
    // the typed spare box alike (ONE rule, so preview == drop for both):
    // the output and distro still exist, the layer draws power, the type
    // feeds the screen's VOLTAGE (2026-09-22: a Multi 208 feeds 208V
    // screens, a Multi 120 feeds 110V / 120V screens - True1 and powerCON
    // breakouts exist at both, so the connector alone no longer decides)
    // and the connector matches the screen's effective breakout. The
    // screen always has one (getPowerBreakout defaults a 110V / 120V
    // screen to the preference or Edison, everything else to True1), so
    // the match is always against something real; a mismatch names the
    // screen and the fix and never re-types the screen. The voltage is
    // checked first: a 120V Edison screen refused by a Multi 208 is
    // refused for its voltage, not sent to change a breakout that would
    // not help. Returns { ok: true, d, type, glyph } or the refusal
    // { ok: false, glyph, message }.
    _plugGate(payload, layer) {
        const d = this.getDistros().find(x => x.id === payload.distroId);
        const type = this.getDistroOutputTypes()
            .find(t => t.id === payload.output);
        const glyph = type ? type.glyph : 'soca';
        if (!d || !type) {
            return { ok: false, glyph, message: 'That output no longer exists.' };
        }
        if (!layer || (layer.type || 'screen') !== 'screen') {
            return { ok: false, glyph,
                     message: `${(layer && layer.name) || 'That layer'} `
                        + 'draws no power.' };
        }
        const voltsMsg = this._voltageMismatchMessage(type, layer);
        if (voltsMsg) return { ok: false, glyph, message: voltsMsg };
        const bt = this.getPowerBreakout(layer);
        if (!type.breakouts.includes(bt.id)) {
            return { ok: false, glyph,
                     message: `${layer.name} is set to `
                        + `${this._breakoutShortName(bt)} — change its `
                        + 'breakout first' };
        }
        return { ok: true, d, type, glyph };
    }

    // A typed spare box dropped on a specific circuit: the plug gate, then
    // the anchored take (_socaTakePlan, the 2026-09-05 rule - the box
    // takes its cell's circuits from the FIRST up to the dropped one, as
    // many as it has free). The pill and the underlay read this; the
    // release runs it again and takes exactly this. `socaIndex` names the
    // multi for the pending bracket only when the take is that whole
    // multi - a partial take has no committed shape to preview yet.
    // Returns the plug plan's shape: { ok, glyph, socaIndex, nums, number,
    // boxName, amps, badge, warn, text } or { ok: false, glyph, message }.
    _boxDropPlan(payload, layer, ordinal) {
        const gate = this._plugGate(payload, layer);
        if (!gate.ok) return gate;
        const { d, type, glyph } = gate;
        const plan = this._socaTakePlan(layer, ordinal, payload.distroId,
                                        payload.number);
        if (!plan.ok) {
            const c = this.screenCircuits(layer)[ordinal - 1];
            const label = c ? this.getPowerCircuitLabel(layer, c.num) : '';
            return { ok: false, glyph,
                     message: this._takeRefusalText(payload, plan, label, layer) };
        }
        const nums = plan.nums;
        const amps = this.getSocaPlan(layer)
            .flatMap(s => s.legs)
            .filter(g => nums.includes(g.circuit))
            .reduce((t, g) => t + (g.amps || 0), 0);
        const boxName = `${d.name || d.id} ${plan.number}`;
        const whole = plan.seg && plan.spanStart === plan.seg.start
            && plan.spanEnd === plan.seg.end;
        return {
            ok: true, glyph, socaIndex: whole ? plan.seg.index : null,
            nums, number: plan.number, boxName, amps, badge: type.badge,
            warn: null,
            text: `${boxName} → circuit${nums.length === 1 ? '' : 's'} `
                + `${this._fmtTails(nums).replace(/-/g, '–')} · `
                + `${Math.round(amps)} A`,
        };
    }

    // The take's refusals in one voice, for the pill and the strip alike.
    _takeRefusalText(payload, r, label, layer) {
        if (r.why === 'other-box') {
            // A circuit on another box is somebody's feed: the drop never
            // pulls it off. Clear it first. The holder is named - "SR1" -
            // not called a box or a breakout.
            const rec = layer && r.seg && typeof this._powerNaming === 'function'
                ? this._powerNaming(layer).socas.get(r.seg.index) : null;
            const where = rec && rec.name ? rec.name : 'another distro';
            return `${label} is already on ${where} - clear it first; `
                + `${payload.title} never takes a circuit that is already fed.`;
        }
        // The place-overflow refusal, in circuits: a box with no free
        // circuit takes nothing, and no cut happens for nothing.
        const len = r.tailLen != null ? r.tailLen : r.remaining;
        return `${payload.title} has no free circuits - the ${len} circuit`
            + `${len === 1 ? '' : 's'} up to ${label} stay where they are.`;
    }

    // The box plan per (screen, circuit), once per drag - the hit test
    // runs per mousemove and the state cannot change mid-drag.
    _boxPlanFor(drag, layer, ordinal) {
        if (!drag.plans) drag.plans = new Map();
        const key = `${layer.id}:${ordinal}`;
        if (!drag.plans.has(key)) {
            drag.plans.set(key, this._boxDropPlan(drag.payload, layer, ordinal));
        }
        return drag.plans.get(key);
    }

    // The plan for one screen, once per drag: the state cannot change
    // mid-drag, and the hit test runs per mousemove.
    _plugPlanFor(drag, layer) {
        if (!drag.plans) drag.plans = new Map();
        if (!drag.plans.has(layer.id)) {
            drag.plans.set(layer.id, this._plugDropPlan(drag.payload, layer));
        }
        return drag.plans.get(layer.id);
    }

    // The cursor pill of a plug drag: what the release will do ("SL 3 →
    // circuits 7–12 · 81 A"), amber when the box would push the distro's
    // legs past its rating (allowed, said), red with the reason where the
    // drop is refused. Hidden over nothing.
    _dockPlugPill(drag, ev, target) {
        let pill = drag.pill;
        if (!pill) {
            pill = document.createElement('div');
            pill.id = 'hw-dock-pill';
            document.body.appendChild(pill);
            drag.pill = pill;
        }
        const p = target && target.plug;
        if (!p) {
            pill.style.display = 'none';
            return;
        }
        const key = JSON.stringify(p);
        if (drag.pillKey !== key) {
            drag.pillKey = key;
            pill.innerHTML = '';
            pill.className = p.ok
                ? (p.warn ? 'hw-dock-pill-warn' : '') : 'hw-dock-pill-bad';
            pill.appendChild(this.plugGlyph(p.glyph));
            const t = document.createElement('span');
            t.textContent = p.ok
                ? p.text + (p.warn ? ` — ${p.warn}` : '') : p.message;
            pill.appendChild(t);
        }
        pill.style.display = '';
        const w = pill.offsetWidth;
        pill.style.left = `${Math.max(8, Math.min(ev.clientX + 16,
            window.innerWidth - w - 8))}px`;
        pill.style.top = `${Math.max(8, ev.clientY - 30)}px`;
    }

    // The release: the same resolution the preview showed, then the
    // existing setter, one 'Assign Multi Distro' entry - the distro drop's
    // own undo name, for one box instead of all of them. A refusal is said
    // on the strip and changes nothing.
    _dockDropPlug(payload, target) {
        if (!target || target.kind !== 'screen') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        const plan = this._plugDropPlan(payload, layer);
        if (!plan.ok) {
            this._dockSay(plan.message);
            return;
        }
        // The box this makes wears the type it was dragged as - stamped
        // before the assignment's entry, so the gesture stays one step.
        if (plan.number != null) {
            this._stampBoxType(payload.distroId, plan.number, payload.output);
        }
        const touched = this.setSocaDistro(layer, plan.socaIndex,
                                           payload.distroId, false);
        this.updateLayers([...new Set(touched)], true, 'Assign Multi Distro');
        this._restateNaming();
        if (plan.warn) {
            this._dockSay(`${plan.boxName} landed on ${layer.name} — `
                + `${plan.warn}.`);
        }
    }

    // The click path (user pick C-as-submenu, 2026-08-31): right-click a
    // screen in the power view - its cabinets on the canvas, or its
    // circuit chips in the tray - and "Add <type> from…" lists every
    // distro: the ones offering the screen's connector with their load,
    // the rest greyed with the reason. Picking one is the plug drop,
    // verbatim - same resolution, same setter, same undo entry. The type
    // is the screen's own: its effective breakout and its voltage decide
    // what it can take, so an L21-30 screen asks for an L21-30, a 120V
    // screen for a Soca 120 and a 208V True1 screen for a Soca 208. A
    // screen whose breakout no type names offers nothing here, exactly as
    // its drops would refuse.
    _prepareOutputsMenu(x, y) {
        const layer = this._outputsMenuLayer(x, y);
        if (!layer) return null;
        const distros = this.getDistros();
        if (!distros.length) return null;
        const type = this.outputTypeForBreakout(this.getPowerBreakout(layer),
                                                layer.powerVoltage);
        if (!type) return null;
        const loads = (typeof this.getDistroLoads === 'function'
            && this.getDistroLoads()) || [];
        const entries = distros.map(d => {
            const name = d.name || d.id;
            if (!this.distroOffers(d, type.id)) {
                return {
                    label: `${name} — does not offer ${type.name}`,
                    disabled: true,
                    title: `Tick ${type.name} under ${name}'s ⚙ Outputs to `
                        + 'offer it.',
                };
            }
            const load = loads.find(l => l.id === d.id);
            const fig = load && load.ratingA > 0
                ? ` ${load.amps.toFixed(0)}/${load.ratingA} A` : '';
            const payload = { type: 'plug', distroId: d.id, output: type.id,
                              title: `${name} · ${type.name}` };
            const plan = this._plugDropPlan(payload, layer);
            return {
                label: `${name}${fig}`,
                disabled: !plan.ok,
                title: plan.ok
                    ? `${plan.text}${plan.warn ? ` — ${plan.warn}` : ''}. `
                        + 'One undoable step.'
                    : plan.message,
                run: () => {
                    sendClientLog('dock_output_pick',
                                  { payload, layerId: layer.id });
                    this._dockDropPlug(payload,
                                       { kind: 'screen', layerId: layer.id });
                },
            };
        });
        return { label: `Add ${type.name} from…`, type: type.id, entries };
    }

    // The screen a right-click names, for the outputs submenu: a circuit
    // chip in the tray speaks for the screen holding that circuit; on the
    // canvas, in the power view, the circuit under the cursor names its
    // owner (a group peer's cabinet lands on the owner's run), and a
    // cabinet on no drawn circuit still names its screen.
    _outputsMenuLayer(x, y) {
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload || payload.type !== 'tail') return null;
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            return held ? held.layer : null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas
                || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        if (!under) return null;
        const circuit = renderer._powerCircuitForPanel(under, hit.panel);
        const layer = circuit ? circuit.owner : under;
        return (layer.type || 'screen') === 'screen' ? layer : null;
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
        if (target && target.kind === 'reorder') {
            if (payload.type === 'processor') {
                return this._dockReorderProcessors(payload.processorId,
                                                   target.index);
            }
            if (payload.type === 'distro') {
                return this._dockReorderDistros(payload.distroId,
                                                target.index);
            }
            return;
        }
        // A processor dropped on a SCREEN assigns the way its first card
        // does - the tooltip's promise, and the only sense a whole
        // processor can land on a wall in.
        if (payload.type === 'processor') {
            const proc = (this._processorsResolved || [])
                .find(p => p.id === payload.processorId);
            const slot = ((proc && proc.slots) || []).find(s => s && s.card);
            if (!slot) return;
            return this._dockDropCardOrBox({
                type: 'card', cardId: slot.card.id,
                title: slot.card.name || slot.card.deviceName,
            }, target);
        }
        if (payload.type === 'port') return this._dockDropPort(payload, target);
        if (payload.type === 'card' || payload.type === 'box') {
            return this._dockDropCardOrBox(payload, target);
        }
        if (payload.type === 'slot') return this._dockDropSlot(payload, target);
        if (payload.type === 'tail') return this._dockDropTail(payload, target);
        if (payload.type === 'distro') {
            return this._dockDropDistro(payload, target);
        }
        if (payload.type === 'plug') return this._dockDropPlug(payload, target);
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
            // Every claim on a socket is a pin - nothing lands any other
            // way - so every claimant is released. One release per
            // claimant, one history entry for the gesture: the snapshot is
            // taken after the last request lands, so a single Ctrl+Z
            // empties the socket back to how it was.
            let chain = Promise.resolve();
            occupants.forEach((o, i) => {
                chain = chain.then(() => this._assignmentRequest(
                    '/api/port-assignments/unpin', 'POST',
                    { layerId: o.layerId, index: o.number - 1 },
                    null, i === occupants.length - 1 ? 'Release Port' : null));
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
            // ONE rule for the whole-multi drop and the mid-multi drop
            // (user, 2026-09-04: "drag multi 2 onto 6 ports it only lets
            // me do 1 ... it should allow me to do up to 6"; 2026-09-05:
            // "i need it to start at 1-1 instead and increase to 1-6"):
            // the box takes its cell's circuits from the FIRST up to the
            // dropped one, as many as it has free - absorbing the
            // one-circuit leftovers a run of pip drops left behind,
            // skipping the head circuits already on another box, never
            // crossing the grid line. takeSocaOnto resegments, re-keys
            // and assigns in ONE history entry; the tray talks.
            const rec = this._powerNaming(layer).socas.get(target.socaIndex);
            const at = rec ? rec.circuits.indexOf(target.num) : -1;
            const ordinal = this.screenCircuits(layer)
                .findIndex(c => c.num === target.num) + 1;
            if (!rec || at < 0 || ordinal < 1) return;
            const label = this.getPowerCircuitLabel(layer, target.num);
            if (payload.output) {
                // A typed spare box: the plug gate and the take, exactly
                // as the preview resolved them (_boxDropPlan); a refusal
                // is said and changes nothing. The box wears its type
                // from the drop on - stamped before the take's own entry.
                const plan = this._boxDropPlan(payload, layer, ordinal);
                if (!plan.ok) {
                    this._dockSay(plan.message);
                    return;
                }
                this._stampBoxType(payload.distroId, payload.number,
                                   payload.output);
            }
            const r = this.takeSocaOnto(layer, ordinal, payload.distroId,
                                        payload.number, 'Assign Multi Distro');
            if (!r.ok) {
                this._dockSay(this._takeRefusalText(payload, r, label, layer));
                return;
            }
            if (r.took < r.tailLen) {
                // Take-what-fits, said out loud - the same convention
                // place-overflow follows with spare ports: the FIRST
                // circuits land, the rest wait.
                this._dockSay(`${payload.title} had ${r.free} free `
                    + `circuit${r.free === 1 ? '' : 's'} - took ${r.took} `
                    + `of the ${r.tailLen} circuits up to ${label}; `
                    + 'the rest stay as their own unassigned multi.');
            }
            this._restateNaming();
            return;
        }
        if (target.kind === 'dock') {
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) return;
            // Clear every multi the chip names - the chip is the box, and
            // pulling the box off the wall pulls all its feeds. The SAME
            // clear the right-click of this very chip runs (_clearMultis):
            // one gesture, one 'Clear Multi' entry, and the stored
            // programming is forgotten with the assignment - two gestures
            // wearing one history name must not keep different paperwork.
            this._clearMultis(
                members.map(m => ({ layerId: m.layerId, soca: m.soca })),
                'Clear Multi');
        }
    }

    // A tail pip lands on ONE circuit: that circuit alone goes to this
    // box's tail N - the tray's finest grain, for the wall where no whole
    // multi is wanted. Composed entirely from the machinery the other drops
    // already run: the drop-implied split isolates the circuit where it is
    // not a multi of its own (one cut before it, one after the remainder),
    // the incumbents on the box freeze exactly as every join freezes them,
    // and the stored tail set [N] is how a one-circuit multi lands on pip N
    // under the wall-order rule - a set of one has nothing to reorder. ONE
    // history entry for the whole gesture, like the split-drop above.
    _dockDropTail(payload, target) {
        if (target.kind === 'dock') {
            // The drag-back: the chip is the circuit, and pulling it off
            // the wall takes that one circuit off its box - the SAME clear
            // the right-click of this very chip runs (_clearCircuitChip),
            // one gesture, one 'Clear Circuit' entry. A free chip has
            // nothing to release.
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) return;
            return this._clearCircuitChip(held.layer, held.rec.index,
                                          held.circuit);
        }
        if (target.kind !== 'run') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        const nm = this._powerNaming(layer);
        const slot = nm.slots.get(target.num);
        const rec = slot ? nm.socas.get(slot.multi) : null;
        if (!rec) return;
        const label = this.getPowerCircuitLabel(layer, target.num);
        const n = parseInt(payload.number, 10);
        if (rec.pinned && rec.distroId === payload.distroId
                && rec.number === n && slot.tail === payload.tail) {
            // Already exactly there - a no-op said out loud, not a refusal.
            this._dockSay(`${label} is already on ${payload.title}.`);
            return;
        }
        // The pips' own occupancy convention: a tail a PINNED member holds
        // is taken (an auto at this number re-deals and defends nothing,
        // the rule every join follows). The dragged circuit's own seat is
        // not in its way - landing there is the no-op above.
        for (const m of (this._distroMultiNumbers(payload.distroId)
                .get(n) || [])) {
            if (!m.pinned) continue;
            const ml = (this.project.layers || [])
                .find(l => l.id === m.layerId);
            const mr = ml && this._powerNaming(ml).socas.get(m.soca);
            if (!mr || !Array.isArray(mr.positions)) continue;
            const i = mr.positions.indexOf(payload.tail);
            if (i < 0) continue;
            if (ml === layer && m.soca === rec.index
                    && mr.circuits[i] === target.num) continue;
            this._dockSay(`Circuit ${payload.tail} is held by ${ml.name} `
                + `${this.getPowerCircuitLabel(ml, mr.circuits[i])} - `
                + 'clear it first, or drop on a free pip.');
            return;
        }
        const at = rec.circuits.indexOf(target.num);
        if (at < 0) return;
        const touched = new Set([layer]);
        let idx = rec.index;
        if (at > 0) {
            // Cut BEFORE the circuit: it becomes the head of the next part.
            const stamped = this._splitSocaApply(layer, idx, at);
            if (!stamped) return;
            stamped.forEach(l => touched.add(l));
            idx += 1;
        }
        if (rec.circuits.length - at > 1) {
            // Cut AFTER it: the remainder stays behind as its own multi
            // (unassigned, the split rule), and the moving part is exactly
            // the one circuit the pip was aimed at.
            const stamped = this._splitSocaApply(layer, idx, 1);
            if (!stamped) return;
            stamped.forEach(l => touched.add(l));
        }
        this._materializeSocaBox(payload.distroId, n, layer, idx)
            .forEach(l => touched.add(l));
        (layer.powerSocaDistro || (layer.powerSocaDistro = {}))[idx]
            = payload.distroId;
        (layer.powerSocaNumber || (layer.powerSocaNumber = {}))[idx] = n;
        (layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {}))[idx]
            = [payload.tail];
        this._circuitTailCache = null;
        this.updateLayers([...touched], true, 'Assign Circuit');
        this._restateNaming();
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
        // The plug gate, per multi the drop would feed (2026-09-22): a
        // whole-distro drag has no chip type, so each multi lands as the
        // type its screen's breakout AND voltage imply - exactly what
        // distroBoxType's rung 2 would read off the box afterwards - and
        // that type passes the same gate a single-output drag does, with
        // the same refusal on the strip. All or nothing: one multi the
        // distro would not feed refuses the whole drop and nothing
        // mutates. A screen whose breakout no output type names (L6-20)
        // is refused naming the breakout, as its chip drops are; a distro
        // whose explicit OUTPUTS list leaves the type out is refused the
        // way the right-click submenu greys it.
        for (const s of unassigned) {
            const refusal = this._distroDropRefusal(payload, layer, s);
            if (refusal) {
                this._dockSay(refusal);
                return;
            }
        }
        // The existing per-multi assignment, once per unassigned multi, in
        // plan order - the numbers fall out of the distro's own sequence.
        // Undo audit: one drag, one entry. The handle's own tooltip calls
        // this one act ("its unassigned multis ALL land on this distro");
        // recorded per-multi it cost N Ctrl+Z presses through half-cabled
        // intermediate walls.
        const touched = new Set();
        unassigned.forEach(s => {
            this.setSocaDistro(layer, s.soca, payload.distroId, false)
                .forEach(l => touched.add(l));
        });
        // The boxes this makes wear the type each multi landed as - the
        // type the gate above passed them on - stamped the way a chip
        // drop stamps its one box: before the assignment's entry, so the
        // gesture stays one undo step. The numbers are read off the
        // naming index now that the assignments are in.
        const landedType = this.outputTypeForBreakout(
            this.getPowerBreakout(layer), layer.powerVoltage);
        if (landedType) {
            this._circuitTailCache = null;
            const naming = this._powerNaming(layer);
            // Stamp every box, persist once: one POST for the gesture,
            // not one per multi the handle fed.
            let stamped = false;
            unassigned.forEach(s => {
                const rec = naming.socas.get(s.soca);
                if (rec && rec.number != null) {
                    if (this._stampBoxType(payload.distroId, rec.number, landedType.id, false)) {
                        stamped = true;
                    }
                }
            });
            if (stamped) this._persistDistros();
        }
        this.updateLayers([...touched], true, 'Assign Multi Distro');
        this._restateNaming();
    }

    // Why a whole-distro drop would refuse ONE of the screen's multis, or
    // null when the distro feeds it: the plug gate (_plugGate - the
    // output exists, the screen draws power, the type feeds the screen's
    // voltage and names its breakout) run for the output type the multi
    // would land as. `s` is the plan record of the multi (unused by the
    // gate today - every multi of one screen shares its breakout and
    // voltage - carried so a per-multi rule has its seat).
    _distroDropRefusal(payload, layer, s) {
        const d = this.getDistros().find(x => x.id === payload.distroId);
        if (!d) return 'That distro no longer exists.';
        const bt = this.getPowerBreakout(layer);
        const type = this.outputTypeForBreakout(bt, layer.powerVoltage);
        if (!type) {
            return `${layer.name} is set to ${this._breakoutShortName(bt)} `
                + '— change its breakout first';
        }
        if (!this.distroOffers(d, type.id)) {
            return `${d.name || d.id} does not offer `
                + `${type.name} — tick ${type.name} under its `
                + '⚙ Outputs first';
        }
        const gate = this._plugGate({ distroId: d.id, output: type.id }, layer);
        return gate.ok ? null : gate.message;
    }
}

for (const k of Object.getOwnPropertyNames(_DockDrag.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_DockDrag.prototype, k));
    }
}
