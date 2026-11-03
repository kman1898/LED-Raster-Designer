// app-dock-menus: the dock's right-click menus - the Clear, Merge,
// Share / Remove Nfer and batch items armed for a chip, run, card, box or
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
                title: `${label} is not attached to ${this.showUnitWord() === 'card' ? 'a sending card' : `a ${this.showUnitWord()}`}, so there `
                    + 'is nothing to clear.',
            };
        }
        return {
            label: `Clear port ${label}`,
            title: `Take this port off its ${this.unitWordForCard(port.cardId)}; it stays unattached until `
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
        // A multi on no distro has nothing to unplug: the item is left off
        // the menu, as the merge item is with nothing to merge (QA
        // 1.6.0-beta.4: offered greyed, it read as an item that did
        // nothing).
        if (!rec.distroId) return null;
        // The multi is the BOX, (distro, number): every part on it goes,
        // as the tray's own Unplug on this box does (the slot chip). An
        // Unplug circuit leaves a multi in parts on one box - 1-2 and 4-5
        // with 3 taken off - and unplugging only the clicked part left the
        // rest plugged while the home run, carried by the first part, went
        // with it (QA 1.6.0-beta.4).
        const members = this._distroMultiNumbers(rec.distroId)
            .get(rec.number) || [];
        const jobs = members.length
            ? members.map(m => ({ layerId: m.layerId, soca: m.soca }))
            : [{ layerId: owner.id, soca: rec.index }];
        // A DIRECT output is one circuit on its own connector, not a
        // multi: the item names the connector it is (a TRUE1, a
        // stage pin), as the tray's chip for it does.
        if (typeof this._isDirectBox === 'function'
                && this._isDirectBox(rec.distroId, rec.number)) {
            const d = this.getDistros().find(x => x.id === rec.distroId);
            const box = this.faceBox(d, rec.number);
            const plug = box ? box.conn.short : this.distroBoxType(d, rec.number).type.name;
            return {
                label: `Unplug ${plug} ${name}`,
                title: `Unplug this circuit from its ${plug} output. `
                    + 'Its stored position, home-run length and label '
                    + 'override are forgotten. One undo puts everything '
                    + 'back.',
                run: () => this._clearMultis(jobs, 'Unplug Multi'),
            };
        }
        return {
            label: `Unplug multi ${name}`,
            title: 'Unplug this multi, every circuit on it. Its distro, '
                + 'number, stored positions, typed name, home-run length '
                + 'and label overrides are all forgotten. One undo puts '
                + 'everything back.',
            run: () => this._clearMultis(jobs, 'Unplug Multi'),
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
        // A head on a DIRECT output holds one circuit: merging the next
        // part into it piled every circuit onto one connector and the app
        // then flagged its own result OVER (QA 1.6.0-beta.4). Not offered.
        if (head && head.distroId && this._isDirectBox(head.distroId, head.number)) return null;
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
    // with the run after it (mergeSplitterCircuits), "Remove 3fer" un-gangs a
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
        // With a sweep selection of two or more circuits armed, the batch
        // entries ARE the sharing story for this opening - a single-run
        // "Share with next" beside "3fer them" would be two grammars for one
        // gesture. A sweep that picked ONE circuit is that circuit's pick:
        // its single-circuit items answer for it (_sweptCircuit).
        const swept = this._sweptCircuit();
        if (swept === false) return none;
        const at = swept || this._dockCircuitAt(x, y);
        if (!at) return none;
        const { layer, num } = at;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        // On a custom group the wall is ONE screen (app-power.js): the run
        // after the last one a member holds is the next member's first, and
        // a share reaching it adopts it into the wall's owner.
        const wallOwner = this.powerPathOwner(layer);
        const onWall = !!this._customPowerWall(layer);
        if (!sp.enabled && !custom && !onWall) return none;
        const circuits = this._wallCircuits(layer);
        const idx = circuits.findIndex(w => w.layer.id === layer.id && w.c.num === num);
        if (idx < 0) return none;
        const c = circuits[idx].c;
        // A circuit taken over by hand keeps the runs it was drawn with -
        // it is neither shared on nor un-shared from here
        // (_shareRunSegments says why).
        if (this._isTakenOverCircuit(layer, c.num)) return none;
        const label = this.getPowerCircuitLabel(layer, c.num);
        const out = { share: null, unshare: null };
        const nextAt = circuits[idx + 1];
        const crosses = !!nextAt && nextAt.layer.id !== layer.id;
        const next = nextAt ? nextAt.c : null;
        if (next && !this._isTakenOverCircuit(nextAt.layer, next.num)) {
            const pair = [{ layerId: layer.id, num: c.num },
                          { layerId: nextAt.layer.id, num: next.num }];
            // The splitter the merge would need: every run already ganged
            // on either side, plus the join.
            const joined = crosses ? this._wallRunSegments(wallOwner, pair).flat()
                : (c.runIds || [c.num]).concat(next.runIds || [next.num]);
            const ways = joined.length;
            const shareLabel = `Share with next run via ${ways}fer`;
            // Custom mode joins only single-run circuits (customShareBlock,
            // the owner's ruling 12): a 2fer, a 3fer or a circuit drawn
            // across several columns keeps the entry, disabled, the reason
            // as its title, and its own "Nfer it" splits a wide one.
            const block = this.isCustomPower(layer)
                ? this.customShareBlock([{ layer, c }, { layer: nextAt.layer, c: next }])
                : null;
            // An automatic share never builds a splitter past the wall's
            // Max splitter (the owner, 2026-10-21).
            const maxWays = sp.maxWays;
            const tooBig = !this.isCustomPower(layer) && ways > maxWays
                ? `A ${ways}fer is bigger than the Max splitter set in Power `
                    + `Settings (${maxWays}fer), so ${label} shares no further.`
                : null;
            // The amps rule (app-power.js): in automatic mode a share whose
            // runs together draw past the screen's amps stays on the menu
            // DISABLED, the reason as its title - the gesture is found, the
            // rule is read. Custom mode honors it and flags OVER.
            const refusal = (crosses || block || tooBig) ? null
                : this.shareRefusal(layer, [joined]);
            if (block) {
                out.share = { label: 'Share with next run', disabled: true,
                              title: block };
            } else if (tooBig) {
                out.share = { label: shareLabel, disabled: true, title: tooBig };
            } else if (refusal) {
                out.share = { label: shareLabel, disabled: true,
                              title: refusal.text };
            } else {
                const load = crosses
                    ? this.shareLoad(wallOwner, joined, this._wallRunAmps(wallOwner))
                    : this.shareLoad(layer, joined);
                const figure = load.cap > 0
                    ? `, ${load.amps.toFixed(1)} A of ${+load.cap.toFixed(1)} A`
                    : '';
                out.share = {
                    label: shareLabel,
                    title: `Share ${label} and `
                        + `${this.getPowerCircuitLabel(nextAt.layer, next.num)} on `
                        + `one circuit through a splitter${figure}. `
                        + (this.isCustomPower(layer)
                            ? 'Custom mode: a share past the amps is '
                                + 'honored and the chip flags OVER. '
                            : '')
                        + 'Undo takes it back off.',
                    run: () => {
                        sendClientLog('dock_share',
                                      { layerId: layer.id, num: c.num });
                        if (crosses || layer.id !== wallOwner.id) {
                            this.mergeWallCircuits(wallOwner, pair);
                        } else {
                            this.mergeSplitterCircuits(layer, [c.num, next.num]);
                        }
                    },
                };
            }
        }
        if ((c.runIds || []).length > 1) {
            // Named by what it takes apart (the owner, 2026-10-20:
            // "unshare doesnt sound correct"): a 3fer reads "Remove 3fer".
            const ways = c.runIds.length;
            out.unshare = {
                label: `Remove ${ways}fer`,
                // Custom never packs on its own, so only an automatic
                // wall pins the legs out of packing.
                title: `Put the ${ways} legs of ${label} back on circuits of `
                    + (custom ? 'their own. '
                        : 'their own, and pin them out of auto packing. ')
                    + `Undo puts the ${ways}fer back.`,
                run: () => {
                    sendClientLog('dock_unshare',
                                  { layerId: layer.id, num: c.num });
                    this.splitSplitterCircuits(layer, [c.num]);
                },
            };
        }
        return out;
    }

    // The circuit an armed canvas sweep picked: { layer, num } when it holds
    // exactly ONE circuit, false when it holds several (the batch entries'
    // turn), null with no sweep armed.
    _sweptCircuit() {
        const sel = this._sweepSelection;
        if (!sel) return null;
        const refs = Array.isArray(sel.refs) && sel.refs.length ? sel.refs
            : (sel.nums || []).map(num => ({ layerId: sel.layerId, num }));
        if (!refs.length) return null;
        if (refs.length > 1) return false;
        const layer = (this.project.layers || []).find(l => l.id === refs[0].layerId);
        return layer ? { layer, num: refs[0].num } : null;
    }

    // "3fer it" (app-power.js, "a wide circuit splits into its own legs"):
    // on the circuit right-clicked - or the one circuit an Alt pick swept -
    // the entry that splits a circuit drawn as ONE run across several
    // columns into a run per column on the same circuit. Its label says
    // what it will make - the circuit's own Nfer, one per column, and no
    // other size; a circuit that cannot be split (one column, over the
    // amps) keeps the entry,
    // disabled, the reason as its title. Absent on a circuit already shared
    // and off a circuit. Canvas only: a tray chip is hardware, and its menu
    // carries the chip's own actions.
    _prepareNferItMenu(x, y) {
        const renderer = window.canvasRenderer;
        if (!renderer || renderer.viewMode !== 'power') return null;
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('#hardware-dock')) return null;
        const swept = this._sweptCircuit();
        if (swept === false) return null;
        const at = swept || this._dockCircuitAt(x, y);
        if (!at) return null;
        const plan = this.nferCircuitPlan(at.layer, at.num);
        if (!plan) return null;
        if (plan.reason) {
            return { label: plan.label, disabled: true, title: plan.reason };
        }
        const name = this.getPowerCircuitLabel(at.layer, at.num);
        const figure = plan.cap > 0
            ? `, ${plan.amps.toFixed(1)} A of ${+plan.cap.toFixed(1)} A` : '';
        return {
            label: plan.label,
            title: `Split ${name} into ${plan.ways} ${plan.noun} runs on the `
                + `same circuit through a ${plan.ways}fer${figure}. `
                + 'One undoable step.',
            run: () => {
                sendClientLog('power_nfer_circuit', { layerId: at.layer.id,
                    num: at.num, ways: plan.ways, mode: plan.mode });
                this.nferCircuit(at.layer, at.num);
            },
        };
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
        // A custom group deals as ONE wall (app-power.js, "custom mode: a
        // group is ONE wall"): `refs` then names every circuit dealt,
        // whichever member holds it, and `layer` is the wall's owner.
        let refs = null;
        if (sel && ((Array.isArray(sel.nums) && sel.nums.length)
                || (Array.isArray(sel.refs) && sel.refs.length))) {
            layer = (this.project.layers || [])
                .find(l => l.id === sel.layerId);
            if (!layer) return null;
            // Degrade-on-read: circuits the plan no longer produces fall
            // out of the selection instead of poisoning the deal.
            if (Array.isArray(sel.refs) && this._customPowerWall(layer)) {
                const have = new Set(this._wallCircuits(layer)
                    .map(x => `${x.layer.id}:${x.c.num}`));
                refs = sel.refs.filter(r => have.has(`${r.layerId}:${r.num}`));
                nums = refs.filter(r => r.layerId === layer.id).map(r => r.num);
            } else {
                const have = new Set(this.screenCircuits(layer).map(c => c.num));
                nums = (sel.nums || []).filter(n => have.has(n));
            }
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
            layer = this.powerPathOwner(circuit.owner);
            if (this._customPowerWall(layer)) refs = this._wallRefs(layer);
            nums = refs ? refs.filter(r => r.layerId === layer.id).map(r => r.num)
                : this.screenCircuits(layer).map(c => c.num);
            scope = 'screen';
        }
        if (!layer || !nums) return null;
        // "2fer / 3fer this screen" on an automatic screen with sharing off
        // is offered too (the owner's ruling, 2026-10-22): picking it ticks
        // "Share circuits via splitters" and deals the screen in the one
        // step, so the entries are worked out on the runs sharing gives.
        if (scope === 'screen' && !this.usesCustomCircuits(layer)
                && !this.getPowerSplitters(layer).enabled) {
            return this._withWallSharingOn(layer, () => this._batchMenuEntries(
                layer, this.screenCircuits(layer).map(c => c.num), null, scope, true));
        }
        return this._batchMenuEntries(layer, nums, refs, scope);
    }

    // "A", "A and B", "A, B and C".
    _namesListText(names) {
        const list = (names || []).filter(Boolean);
        if (list.length < 2) return list[0] || '';
        return `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`;
    }

    // The batch entries for `nums` (or a custom wall's `refs`) of `layer`.
    // `ticking`: worked out with sharing on for a screen that has it off,
    // so every entry ticks it, and nothing shared yet can be removed.
    _batchMenuEntries(layer, nums, refs, scope, ticking = false) {
        if (!layer || !nums || (refs ? refs.length : nums.length) < 2) return null;
        // The deal is at RUN grain, so existing gangs inside the batch
        // re-deal with everything else - count the runs, not the circuits.
        // A circuit taken over by hand is not dealt (_shareRunSegments).
        const runCount = (refs ? this._wallRunSegments(layer, refs)
            : this._shareRunSegments(layer, nums))
            .reduce((t, seg) => t + seg.length, 0);
        const picked = refs ? new Set(refs.map(r => `${r.layerId}:${r.num}`))
            : new Set(nums.map(n => `${layer.id}:${n}`));
        const hasGang = this._wallCircuits(layer).some(x =>
            picked.has(`${x.layer.id}:${x.c.num}`)
            && !this._isTakenOverCircuit(x.layer, x.c.num)
            && (x.c.runIds || []).length > 1);
        if (runCount < 2) return null;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        // Sharing off gates the selection's entries; the whole screen's
        // turn sharing on (above).
        const gated = !sp.enabled && !custom && scope !== 'screen';
        const verb = scope === 'screen' ? 'this screen' : 'them';
        const entries = [];
        // The batch never deals past the wall's Max splitter (the owner,
        // 2026-10-21): at 3fer there is no "4fer this screen".
        [2, 3, 4].filter(n => n <= sp.maxWays).forEach(n => {
            if (gated) {
                if (runCount < n) return;
                entries.push({
                    label: `${n}fer ${verb} (${this.batchNferLabel(runCount, n)})`,
                    disabled: true,
                    title: `Sharing is off for ${layer.name}. Turn on `
                        + '"Share circuits via splitters" in Power Settings '
                        + '(or route its circuits custom) to share runs.',
                });
                return;
            }
            // The deal as it will land: groups that fit the circuit, the
            // rest left plain (the owner's ruling, 2026-10-19 - never an
            // OVER gang, in either mode). A deal that shares nothing stays
            // on the menu disabled, the first pair that does not fit named
            // in the title. A size whose deal produces none of itself is
            // another size's entry wearing the wrong name - "3fer them"
            // where the load only lets runs pair up deals 2fers, which IS
            // the 2fer entry - so it is not offered under this name.
            // A custom circuit drawn across several columns is split into
            // its own legs, never joined (app-power.js batchShareGroups), so
            // the deal's sizes count each split at its ways.
            const deal = this.batchShareGroups(layer, nums, n, refs);
            const sizes = deal.sizes;
            if (runCount < n && !sizes.includes(n)) return;
            const label = `${n}fer ${verb} (${this._nferSizesLabel(sizes)})`;
            if (!sizes.some(sz => sz >= 2)) {
                const load = deal.over
                    ? this.shareLoad(layer, deal.over,
                        refs ? this._wallRunAmps(layer) : undefined) : null;
                entries.push({
                    label, disabled: true,
                    title: load
                        ? `${this._runListText(deal.over, layer)} together draw `
                            + `${load.amps.toFixed(1)} A on `
                            + `${this.circuitLimitText(layer)}, so no runs `
                            + 'here fit on one circuit together'
                        : (deal.tooWide.length
                            ? this._tooWideText(layer, deal.tooWide, n)
                            : 'No runs here fit on one circuit together'),
                });
                return;
            }
            if (!sizes.includes(n)) return;
            const leftPlain = deal.over ? ' Runs that do not fit together '
                + 'stay on circuits of their own.' : '';
            const legs = deal.splits.length ? ' A circuit drawn across several '
                + 'columns splits into a run per column on its own circuit.' : '';
            // "2fer / 3fer this screen" ticks the wall's "Share circuits via
            // splitters" in the same step (batchShareCircuits tickSharing).
            // On a grouped wall the box is the group's: it goes on for
            // every member, and the title says so.
            const ticks = ticking || (scope === 'screen' && !sp.enabled);
            const wall = ticks ? this._splitterWallMembers(layer) : [];
            const tickText = !ticks ? ''
                : (wall.length > 1
                    ? ' Also turns on "Share circuits via splitters" for every screen '
                        + `in its group (${this._namesListText(wall.map(m => m.name || `Screen ${m.id}`))}).`
                    : ' Also turns on "Share circuits via splitters" for this screen.');
            entries.push({
                label,
                title: `Deal ${runCount} run${runCount === 1 ? '' : 's'} `
                    + `left to right as ${this._nferSizesLabel(sizes)}: `
                    + 'adjacent groups, each its own circuit, every group '
                    + `within the amps.${leftPlain}${legs}${tickText} One undoable step.`,
                run: () => {
                    sendClientLog('power_batch_nfer',
                                  { layerId: layer.id, n, scope,
                                    runs: runCount });
                    this.batchShareCircuits(layer, nums, n,
                        `${n}fer ${scope === 'screen'
                            ? 'Screen' : 'Selection'}`, refs,
                        { tickSharing: ticks });
                    this._sweepSelection = null;
                },
            });
        });
        if (!entries.length) return null;
        const out = { entries, scope };
        if (hasGang && !gated && !ticking) {
            // "Remove 3fers from this screen", naming the sizes it takes
            // apart, like the single circuit's "Remove 3fer".
            const removed = this._nferKindsText(this._wallCircuits(layer)
                .filter(x => picked.has(`${x.layer.id}:${x.c.num}`)
                    && !this._isTakenOverCircuit(x.layer, x.c.num)
                    && (x.c.runIds || []).length > 1)
                .map(x => x.c.runIds.length));
            out.unshare = {
                label: `Remove ${removed} from `
                    + (scope === 'screen' ? 'this screen' : 'these'),
                title: `Put every leg of the ${removed} `
                    + (scope === 'screen'
                        ? 'on this screen' : 'in the selection')
                    + ' back on a circuit of its own. One undoable step.',
                run: () => {
                    sendClientLog('power_batch_unshare',
                                  { layerId: layer.id, scope });
                    const action = `Remove ${removed}`;
                    if (refs) {
                        // Across the wall each member un-shares in its own
                        // store - one PUT, one history entry.
                        // A locked member refuses the whole verb and is
                        // named, as "Remove 3fer" names it.
                        const by = new Map();
                        refs.forEach(r => by.set(r.layerId,
                            (by.get(r.layerId) || []).concat([r.num])));
                        const locked = [...by.keys()]
                            .map(id => (this.project.layers || []).find(l => l.id === id))
                            .filter(m => m && this._layerLocked(m));
                        if (locked.length) {
                            this._showLockedError(locked);
                            return;
                        }
                        // Refused whole when it would repack a locked
                        // member (owner, 2026-10-23): written, checked,
                        // put back before the commit.
                        const repacked = this._repackTrial([layer]);
                        const written = [];
                        by.forEach((ns, id) => {
                            const m = (this.project.layers || []).find(l => l.id === id);
                            if (!m) return;
                            this.splitSplitterCircuits(m, ns, null, { silent: true });
                            written.push(m);
                        });
                        if (repacked()) return;
                        if (written.length) this._commitWallShare(written, action);
                    } else {
                        this.splitSplitterCircuits(layer, nums, action);
                    }
                    this._sweepSelection = null;
                },
            };
        }
        return out;
    }

    // The splitter sizes in a list of ways, as words: [3, 3] -> "3fers",
    // [2, 3] -> "2fers and 3fers", [2, 3, 4] -> "2fers, 3fers and 4fers".
    _nferKindsText(ways) {
        const kinds = [...new Set(ways)].sort((a, b) => a - b).map(n => `${n}fers`);
        if (kinds.length <= 1) return kinds[0] || 'shares';
        return `${kinds.slice(0, -1).join(', ')} and ${kinds[kinds.length - 1]}`;
    }

    // Why a deal of size `n` shares nothing when its runs span more columns
    // than an `n`fer has ways: "S1-1, S1-2 and S1-3 span more columns than a
    // 2fer has ways. ...". `wide` is batchShareGroups' tooWide.
    _tooWideText(owner, wide, n) {
        const names = wide.map(w => {
            if (typeof w.id === 'string') {
                const [lid, num] = w.id.split(':').map(v => parseInt(v, 10));
                const m = (this.project.layers || []).find(l => l.id === lid);
                return m ? this.getPowerCircuitLabel(m, num) : w.id;
            }
            return this.getPowerCircuitLabel(owner, w.id);
        });
        const list = names.length === 1 ? names[0]
            : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
        const noun = wide[0].noun || 'column';
        return `${list} ${names.length === 1 ? 'spans' : 'span'} more ${noun}s `
            + `than a ${n}fer has ways. A circuit across several ${noun}s `
            + 'splits into its own legs and never joins another.';
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
                    + 'a backup port. Clear that pick; undo puts it '
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
                                    || rp.backsUp.port}`}. It is that `
                            + 'port\'s return end and holds no claim of '
                            + 'its own.',
                    };
                }
                if (pick) return pickOnly();
                return {
                    label, disabled: true,
                    title: `${payload.title} is free, so there is nothing to `
                        + 'unplug.',
                };
            }
            // Every claim is a pin (nothing lands any other way), so an
            // occupied socket always clears: every claimant comes off.
            return {
                label,
                title: 'Take the screen port off this socket. It stays '
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
                        + 'holds no per-port backup picks, so there is '
                        + 'nothing to clear.',
                };
            }
            return {
                label,
                title: `Take every screen port off ${payload.title}. They `
                    + 'stay unattached until placed again'
                    + (picks.length
                        ? ', and clear its per-port backup picks' : '')
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
                            found, picks, `Clear ${this.unitWordTitle(this.unitWordForCard(payload.cardId))}`))
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
                    label: `Unplug ${payload.title}`, disabled: true,
                    title: `${payload.title} is free, so there is nothing to `
                        + 'unplug.',
                };
            }
            const label = this.getPowerCircuitLabel(held.layer,
                                                    held.circuit);
            const rest = held.rec.circuits.length - 1;
            return {
                label: `Unplug circuit ${label}`,
                title: `Unplug this circuit from ${held.rec.name || 'its multi'} `
                    + 'and forget how it was programmed: its stored position and its '
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
            const label = `Unplug ${payload.title}`;
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) {
                return {
                    label, disabled: true,
                    title: `${payload.title} is free, so there is nothing to `
                        + 'unplug.',
                };
            }
            const slotDistro = this.getDistros()
                .find(x => x.id === payload.distroId) || null;
            const slotType = this.distroBoxType(slotDistro, payload.number).type;
            return {
                label,
                title: `Unplug every multi on this slot. The chip is the `
                    + `${slotType.name}, and unplugging it takes all its feeds and `
                    + 'forgets how they were programmed: stored positions, '
                    + 'typed names, home-run lengths and label overrides. '
                    + 'One undoable step.',
                run: () => this._clearMultis(
                    members.map(m => ({ layerId: m.layerId, soca: m.soca })),
                    'Unplug Multi'),
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
                    title: `No multis are assigned to ${payload.title}, so `
                        + 'there is nothing to clear.',
                };
            }
            return {
                label,
                title: `Clear every multi on ${payload.title}: the `
                    + 'assignments and the stored programming (positions, '
                    + 'typed names, home-run lengths, label overrides), '
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
