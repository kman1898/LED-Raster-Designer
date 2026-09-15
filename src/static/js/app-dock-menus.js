// app-dock-menus: the dock's right-click menus - the Clear, Merge,
// Share / Un-share and batch items armed for a chip, run, card, box or
// distro, and the chip payload reader they all start from. Moved verbatim
// out of app-dock.js and attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _DockMenus {
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
    // The payload of the chip under an element, for the right-click
    // surfaces. A circuit chip speaks for ITSELF now that it is a real chip
    // (its clear and merge are the drawn circuit run's own items, re-aimed
    // from the hardware end); the multi header answers as the slot and the
    // distro header as the distro. A chip whose payload cannot be read arms
    // nothing, as before.
    _dockChipPayload(el) {
        const chip = el && el.closest
            ? el.closest('[data-hwdock-payload]') : null;
        if (!chip) return null;
        try {
            return JSON.parse(chip.dataset.hwdockPayload) || null;
        } catch (_) {
            return null;
        }
    }

    // Which circuit holds one tail of box (distroId, number), read off the
    // naming index's rendered positions - the same map the chips drew from.
    // Returns { layer, rec, circuit } for the first claimant, or null for a
    // free tail.
    _dockTailHolder(distroId, number, tail) {
        for (const m of (this._distroMultiNumbers(distroId)
                .get(number) || [])) {
            const l = (this.project.layers || [])
                .find(x => x.id === m.layerId);
            const rec = l && this._powerNaming(l).socas.get(m.soca);
            if (!rec || !Array.isArray(rec.positions)) continue;
            const i = rec.positions.indexOf(tail);
            if (i >= 0) return { layer: l, rec, circuit: rec.circuits[i] };
        }
        return null;
    }

    _prepareClearMenu(x, y) {
        // The dock chip under the cursor first: chips carry their payload on
        // the element, and the tray sits outside the canvas so the two tests
        // cannot both hit.
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
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
    // the same unpin the strip's release buttons and the drag-back send. A
    // port on a card is always a pin (auto-numbering is retired - user
    // ruling, 2026-09-03), so the clear is offered live whenever the port
    // is attached and disabled only when it is not.
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
                title: `${label} is not attached to a sending card - there `
                    + 'is nothing to clear.',
            };
        }
        return {
            label: `Clear port ${label}`,
            title: 'Take this port off its card; it stays unattached until '
                + 'you place it again. Names and templates are untouched, '
                + 'and undo puts it back.',
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
            title: 'Clear this multi - its distro, number, stored '
                + 'positions, typed name, home-run length and label '
                + 'overrides are all forgotten. One undo puts everything '
                + 'back.',
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
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload) return null;
            if (payload.type === 'tail') {
                // A circuit chip merges as the drawn circuit run does: both
                // sides of a boundary touching its holder's multi.
                const held = this._dockTailHolder(
                    payload.distroId, parseInt(payload.number, 10),
                    payload.tail);
                return held
                    ? this._mergeMenuForMulti(held.layer, held.rec.index,
                                              false)
                    : null;
            }
            if (payload.type !== 'slot') return null;
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

    // ── the right-click circuit sharing ──────────────────────────────────
    //
    // The manual 2fer lever the retired Splitters panel rows carried, on
    // the surfaces the circuit actually lives on: right-click a drawn
    // circuit run or its chip and "Share with next run via 2fer" gangs it
    // with the run after it (mergeSplitterCircuits), "Un-share" un-gangs a
    // shared one (splitSplitterCircuits) - the existing ops, the existing
    // undo entries. Gated exactly as the panel rows were: packed auto
    // circuits (splitters on), or drawn custom circuits (merge-only by the
    // ops' own rule). Off the gate, or off a circuit, neither item appears
    // - like the merge-back, absence is the ordinary condition, not a
    // refusal.

    // The circuit under a point, for the share menu: a dock circuit chip
    // (its holder names the circuit), or a drawn circuit run on the canvas
    // - the same two surfaces every circuit gesture reads.
    _dockCircuitAt(x, y) {
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload || payload.type !== 'tail') return null;
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) return null;
            return { layer: held.layer, num: held.circuit };
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
        const circuit = under
            ? renderer._powerCircuitForPanel(under, hit.panel) : null;
        return circuit
            ? { layer: circuit.owner, num: circuit.circuitNum } : null;
    }

    _prepareShareMenus(x, y) {
        const none = { share: null, unshare: null };
        if (!window.canvasRenderer
                || window.canvasRenderer.viewMode !== 'power') return none;
        // With a sweep selection armed, the batch entries ARE the sharing
        // story for this opening - a single-run "Share with next" beside
        // "3fer them" would be two grammars for one gesture.
        if (this._sweepSelection && this._sweepSelection.nums
                && this._sweepSelection.nums.length) return none;
        const at = this._dockCircuitAt(x, y);
        if (!at) return none;
        const { layer, num } = at;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        if (!sp.enabled && !custom) return none;
        const circuits = this.screenCircuits(layer);
        const idx = circuits.findIndex(c => c.num === num);
        if (idx < 0) return none;
        const c = circuits[idx];
        const label = this.getPowerCircuitLabel(layer, c.num);
        const out = { share: null, unshare: null };
        const next = circuits[idx + 1];
        if (next) {
            // The splitter the merge would need: every run already ganged
            // on either side, plus the join.
            const ways = (c.runIds || [c.num]).length
                + (next.runIds || [next.num]).length;
            out.share = {
                label: `Share with next run via ${ways}fer`,
                title: `Share ${label} and `
                    + `${this.getPowerCircuitLabel(layer, next.num)} on `
                    + 'one circuit through a splitter. Honored even over '
                    + 'capacity - the chip flags OVER. Undo un-shares it.',
                run: () => {
                    sendClientLog('dock_share',
                                  { layerId: layer.id, num: c.num });
                    this.mergeSplitterCircuits(layer, [c.num, next.num]);
                },
            };
        }
        if ((c.runIds || []).length > 1) {
            out.unshare = {
                label: 'Un-share',
                title: `Un-share ${label}'s runs back onto circuits of `
                    + 'their own, and pin them out of auto packing. Undo '
                    + 'restores the share.',
                run: () => {
                    sendClientLog('dock_unshare',
                                  { layerId: layer.id, num: c.num });
                    this.splitSplitterCircuits(layer, [c.num]);
                },
            };
        }
        return out;
    }

    // ── the batch verb: sweep → right-click → "3fer them" ────────────────
    //
    // 2026-08-30, user pick ("lets go for B and then right click"): the
    // sweep (canvas.js Alt+drag) arms a contiguous run selection, and the
    // right-click menu deals it as Nfers - "3fer them (6 × 3fer)", the
    // group math in the label so the deal reads before it is taken. With
    // NO selection the same entries act on the whole screen under the
    // cursor ("one run per column, 3 columns - right click the whole wall,
    // it makes those 3 columns a 3fer"). Gated exactly as the single-run
    // share items are (splitters on, or custom circuits) - but the batch
    // entries stay ON the menu disabled with the reason, because a gesture
    // nobody can find teaches nothing.
    _prepareBatchMenu(x, y) {
        const renderer = window.canvasRenderer;
        if (!renderer || renderer.viewMode !== 'power'
                || !renderer.canvas) return null;
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('#hardware-dock')) return null;
        const sel = this._sweepSelection;
        let layer = null;
        let nums = null;
        let scope = null;
        if (sel && Array.isArray(sel.nums) && sel.nums.length) {
            layer = (this.project.layers || [])
                .find(l => l.id === sel.layerId);
            if (!layer) return null;
            // Degrade-on-read: circuits the plan no longer produces fall
            // out of the selection instead of poisoning the deal.
            const have = new Set(this.screenCircuits(layer).map(c => c.num));
            nums = sel.nums.filter(n => have.has(n));
            scope = 'selection';
        } else {
            const rect = renderer.canvas.getBoundingClientRect();
            if (x < rect.left || x > rect.right
                    || y < rect.top || y > rect.bottom) return null;
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
            layer = circuit.owner;
            nums = this.screenCircuits(layer).map(c => c.num);
            scope = 'screen';
        }
        if (!layer || !nums || nums.length < 2) return null;
        // The deal is at RUN grain, so existing gangs inside the batch
        // re-deal with everything else - count the runs, not the circuits.
        const chosen = new Set(nums);
        let runCount = 0;
        let hasGang = false;
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            const ids = c.runIds || [c.num];
            runCount += ids.length;
            if (ids.length > 1) hasGang = true;
        });
        if (runCount < 2) return null;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        const gated = !sp.enabled && !custom;
        const verb = scope === 'screen' ? 'this screen' : 'them';
        const entries = [];
        [2, 3, 4].forEach(n => {
            if (runCount < n) return;
            // A size whose deal produces none of itself is another size's
            // entry wearing the wrong name - "4fer them" over five runs
            // deals 3+2, which IS the 3fer entry. Offer only honest sizes.
            if (!this.batchNferGroups(runCount, n).includes(n)) return;
            const label = `${n}fer ${verb} `
                + `(${this.batchNferLabel(runCount, n)})`;
            if (gated) {
                entries.push({
                    label, disabled: true,
                    title: `Sharing is off for ${layer.name} - turn on `
                        + '"Share circuits via splitters" in Power Settings '
                        + '(or route its circuits custom) to share runs.',
                });
                return;
            }
            entries.push({
                label,
                title: `Deal ${runCount} run${runCount === 1 ? '' : 's'} `
                    + `left to right as ${this.batchNferLabel(runCount, n)} `
                    + '- adjacent groups, each its own circuit. Honored '
                    + 'even over capacity - a shared circuit past its amps '
                    + 'flags OVER. One '
                    + 'undoable step.',
                run: () => {
                    sendClientLog('power_batch_nfer',
                                  { layerId: layer.id, n, scope,
                                    runs: runCount });
                    this.batchShareCircuits(layer, nums, n,
                        `${n}fer ${scope === 'screen'
                            ? 'Screen' : 'Selection'}`);
                    this._sweepSelection = null;
                },
            });
        });
        if (!entries.length) return null;
        const out = { entries, scope };
        if (hasGang && !gated) {
            out.unshare = {
                label: scope === 'screen'
                    ? 'Un-share this screen' : 'Un-share all',
                title: 'Un-share every shared circuit '
                    + (scope === 'screen'
                        ? 'on this screen' : 'in the selection')
                    + ' back onto runs of their own. One undoable step.',
                run: () => {
                    sendClientLog('power_batch_unshare',
                                  { layerId: layer.id, scope });
                    this.splitSplitterCircuits(layer, nums,
                        scope === 'screen'
                            ? 'Un-share Screen' : 'Un-share Selection');
                    this._sweepSelection = null;
                },
            };
        }
        return out;
    }

    // A dock chip: the same clears, from the hardware end of the cable.
    _clearMenuForDock(payload) {
        if (payload.type === 'port') {
            const label = `Clear ${payload.title}`;
            const all = this._portOccupants(payload.cardId, payload.port);
            const occupants = all.filter(o => !o.role);
            // The port's hand-picked backup (manual redundancy), part of
            // this socket's programming: the clear forgets it with the
            // claim. Typed port names stay - they are hardware naming,
            // not programming.
            const found = this._dockCardById(payload.cardId);
            const pick = found
                && (found.card.backupPorts || {})[String(payload.port)];
            // The pick-only offer, for a socket with no claim to release
            // but a stored pick to forget. Sits BELOW the role refusals: a
            // socket that is itself a backup end answers by its role.
            const pickOnly = () => ({
                label,
                title: `${payload.title} holds no claim, but it picks `
                    + 'a backup port - clear that pick. Undo puts it '
                    + 'back.',
                run: () => {
                    sendClientLog('dock_clear',
                                  { kind: 'port-pick', payload });
                    return this._dockClearPortPicks(
                        found, [payload.port], 'Clear Port');
                },
            });
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
                            || `${rp.backsUp.boxTitle
                                ? `${rp.backsUp.boxTitle} ` : ''}port `
                                + `${rp.backsUp.localPort
                                    || rp.backsUp.port}`} - it is that `
                            + 'port\'s return end and holds no claim of '
                            + 'its own.',
                    };
                }
                if (pick) return pickOnly();
                return {
                    label, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            // Every claim is a pin (nothing lands any other way), so an
            // occupied socket always clears: every claimant comes off.
            return {
                label,
                title: 'Take the screen port off this socket - it stays '
                    + 'unattached until placed again'
                    + (pick ? ', and clear the socket\'s hand-picked '
                        + 'backup port'
                        : '')
                    + '. Undo puts it back.',
                run: () => {
                    sendClientLog('dock_clear', { kind: 'port', payload });
                    const release = this._dockReleasePins(
                        occupants.map(o => ({ layerId: o.layerId,
                                              index: o.number - 1 })),
                        pick ? null : 'Release Port');
                    // The pick clear rides the same gesture: the snapshot
                    // moves to the LAST request, so the whole clear stays
                    // one history entry.
                    return pick
                        ? release.then(() => this._dockClearPortPicks(
                            found, [payload.port], 'Clear Port'))
                        : release;
                },
            };
        }
        if (payload.type === 'card' || payload.type === 'box') {
            const label = `Clear ${payload.title}`;
            const first = payload.type === 'box' ? payload.first : -Infinity;
            const last = payload.type === 'box' ? payload.last : Infinity;
            // Every screen port on the card (or inside the box's span) is a
            // pin - there is no other way onto a card - and the clear takes
            // all of them off.
            const pins = [];
            ((this._assignment && this._assignment.screens) || [])
                .forEach(scr => (scr.ports || []).forEach(p => {
                    if (p.cardId === payload.cardId
                            && p.port >= first && p.port <= last) {
                        pins.push({ layerId: scr.layerId, index: p.index });
                    }
                }));
            // The card's per-port backup picks in this range are its
            // programming too, and the clear forgets them with the pins.
            // Typed port names stay - hardware naming, not programming.
            const found = this._dockCardById(payload.cardId);
            const picks = [];
            if (found) {
                Object.keys(found.card.backupPorts || {}).forEach(k => {
                    const pn = parseInt(k, 10);
                    if (Number.isFinite(pn) && pn >= first && pn <= last) {
                        picks.push(pn);
                    }
                });
            }
            if (!pins.length && !picks.length) {
                return {
                    label, disabled: true,
                    title: `Nothing is attached to ${payload.title} and it `
                        + 'holds no per-port backup picks - there is '
                        + 'nothing to clear.',
                };
            }
            return {
                label,
                title: `Take every screen port off ${payload.title} - they `
                    + 'stay unattached until placed again'
                    + (picks.length
                        ? ' - and clear its per-port backup picks' : '')
                    + ', as one undoable step.',
                run: () => {
                    sendClientLog('dock_clear',
                                  { kind: payload.type, payload,
                                    count: pins.length,
                                    picks: picks.length });
                    const release = pins.length
                        ? this._dockReleasePins(
                            pins, picks.length ? null : 'Release Ports')
                        : Promise.resolve();
                    // The picks ride the same gesture; the snapshot moves
                    // to the last request so one Ctrl+Z restores pins and
                    // picks together.
                    return picks.length
                        ? release.then(() => this._dockClearPortPicks(
                            found, picks, 'Clear Card'))
                        : release;
                },
            };
        }
        if (payload.type === 'tail') {
            // The circuit chip's clear, re-aimed from the hardware end -
            // the finest grain of the tray's three clears: the CHIP is the
            // circuit (this item), the multi header is the BOX ('Clear
            // multi', the slot branch below) and the distro header is
            // EVERYTHING on it ('Clear <distro>'). A free chip states its
            // freedom. A held chip clears at circuit scope whatever its
            // multi holds (user, 2026-09-05: "i want to delete the 6th
            // circuit from the distro ... can only clear the whole
            // multi"): the circuit comes off the box and forgets how it
            // was programmed - its position, its label override, its
            // manual splitter entries - and the multi's other circuits
            // stay exactly where the wall showed them, the multi's name
            // and home-run length with them (_clearCircuitChip).
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) {
                return {
                    label: `Clear ${payload.title}`, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            const label = this.getPowerCircuitLabel(held.layer,
                                                    held.circuit);
            const rest = held.rec.circuits.length - 1;
            return {
                label: `Clear circuit ${label}`,
                title: `Take this circuit off ${held.rec.name || 'its multi'} `
                    + 'and forget how it was programmed - its stored position and its '
                    + 'label override go with the assignment'
                    + (rest
                        ? `; the multi's other ${rest} circuit`
                            + `${rest === 1 ? ' stays' : 's stay'} where `
                            + `${rest === 1 ? 'it is' : 'they are'}`
                        : '')
                    + '. One undo puts it all back.',
                run: () => this._clearCircuitChip(
                    held.layer, held.rec.index, held.circuit),
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
            const slotDistro = this.getDistros()
                .find(x => x.id === payload.distroId) || null;
            const slotType = this.distroBoxType(slotDistro, payload.number).type;
            return {
                label,
                title: `Clear every multi on this slot - the chip is the `
                    + `${slotType.name}, and clearing it takes all its feeds and `
                    + 'forgets how they were programmed: stored positions, '
                    + 'typed names, home-run lengths and label overrides. '
                    + 'One undoable step.',
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
                title: `Clear every multi on ${payload.title} - the `
                    + 'assignments and the stored programming (positions, '
                    + 'typed names, home-run lengths, label overrides) - '
                    + `as one undoable step. ${payload.title} itself keeps `
                    + 'its name and electrical setup.',
                run: () => this._clearMultis(members, 'Clear Distro'),
            };
        }
        return null;
    }
}

for (const k of Object.getOwnPropertyNames(_DockMenus.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_DockMenus.prototype, k));
    }
}
