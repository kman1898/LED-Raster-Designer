// app-custom-runs: hand-drawn runs for LEDRasterApp - the capacity a custom
// port or circuit may take, adding a cabinet to a path by click or arrow
// key, stepping across member boundaries, and the pattern fill that lays
// a selection out as numbered runs cut at capacity.
import { LEDRasterApp } from './app-core.js';

// Float sums of derated watts land a hair over an exact multiple; a circuit
// that is precisely full is full, not over. See customRunCapacity.
const CUSTOM_RUN_EPS = 1e-6;

class _CustomRuns {

    // ── Capacity while drawing by hand ────────────────────────────────────
    //
    // The wall this was built for: 28 cabinets wide on 110 V / 15 A, so
    // automatic power refuses ("a full row is N W and a circuit carries
    // M W"). The way round it is custom mode - select a 14 x 6 block, press
    // serpentine, get circuits 1..6 at 14 apiece - which only works if the
    // pattern fill CUTS at capacity instead of pouring the whole selection
    // into the one active circuit, and if a click past the cap is refused
    // instead of quietly overloading the run. The cut falls between whole
    // rows (or columns): a run takes another line only when all of it fits,
    // so a circuit never starts part-way along a row, and each of those six
    // reads from the SAME side: a new run restarts the snake at the
    // pattern's start corner rather than continuing it
    // (_chunkPicksByCapacity).
    //
    // ONE authority per side, and each is the sidebar's own readout:
    //   power  "Panels/Circuit" - watts per circuit (V x A) against each
    //          cabinet's watt-equivalent: panelWatts x getPanelLoadFactor,
    //          the half-tile derate calculatePowerAssignments' loadOf
    //          charges, at the cabinet's OWN member's wattage the way
    //          getSocaPlan charges a crossing circuit.
    //   data   "Panels/Port" - pixels per port (calculatePortCapacity, Low
    //          Latency factor included) against each cabinet's pixel area.
    // Nothing is re-derived here, so a capacity change lands in both.
    //
    // A run is FULL when one more whole cabinet would not fit; a click is
    // refused when THAT cabinet would not fit, so a half-tile can still land
    // on a run the badge calls full - the badge speaks of whole cabinets. No
    // capacity at all (no voltage or wattage set, no published pixel figure
    // for the processor) means no cap, and the run takes whatever is drawn
    // exactly as it always has.
    customRunCapacity(layer, kind) {
        const none = { known: false, limit: 0, unit: 0, count: 0, at: '', describe: '' };
        if (!layer) return none;
        if (kind === 'power') {
            const voltage = parseFloat(layer.powerVoltage) || 0;
            const amperage = parseFloat(layer.powerAmperage) || 0;
            const unit = parseFloat(layer.panelWatts) || 0;
            const limit = voltage * amperage;
            if (!(limit > 0 && unit > 0)) return none;
            const count = Math.floor(limit / unit);
            const at = `${voltage}V/${amperage}A`;
            return { known: true, limit, unit, count, at,
                describe: `${count} panels at ${at}` };
        }
        const limit = this.calculatePortCapacity(
            layer.bitDepth || 8, layer.frameRate || 60,
            layer.processorType || 'novastar-armor', !!layer.lowLatency);
        const unit = this.getFullPanelPixels(layer);
        if (!(limit > 0 && unit > 0)) return none;
        const count = Math.floor(limit / unit);
        const at = `${limit.toLocaleString()} px/port`;
        return { known: true, limit, unit, count, at,
            describe: `${count} panels at ${at}` };
    }

    // What ONE cabinet costs against the run it is being drawn onto.
    customHitLoad(kind, hitLayer, panel) {
        if (!panel) return 0;
        if (kind === 'power') {
            return (parseFloat(hitLayer && hitLayer.panelWatts) || 0)
                * this.getPanelLoadFactor(hitLayer, panel);
        }
        return this.getPanelPixelArea(panel);
    }

    // One run's fill: the load drawn so far, the cap it is drawn against, and
    // whether another whole cabinet still fits. `used` is in whole-cabinet
    // equivalents so the badge can read "9/14".
    customRunFill(owner, kind, num) {
        const cap = this.customRunCapacity(owner, kind);
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const path = (owner && owner[pathsKey] && owner[pathsKey][num]) || [];
        const load = this.getResolvedPathPanels(owner, path)
            .reduce((s, hit) => s + this.customHitLoad(kind, hit.layer, hit.panel), 0);
        const used = cap.unit > 0 ? load / cap.unit : 0;
        const eps = CUSTOM_RUN_EPS;
        return Object.assign({}, cap, {
            load, used,
            full: cap.known && (load + cap.unit > cap.limit + eps),
        });
    }

    // Does this cabinet still fit on the run?
    customRunAccepts(owner, kind, num, hitLayer, panel) {
        const fill = this.customRunFill(owner, kind, num);
        if (!fill.known) return true;
        return fill.load + this.customHitLoad(kind, hitLayer, panel)
            <= fill.limit + CUSTOM_RUN_EPS;
    }

    // "9", "13.7" - a whole count where it is one, a tenth where a half-tile
    // made it a fraction.
    _formatRunUsed(used) {
        const r = Math.round((Number(used) || 0) * 10) / 10;
        return Number.isInteger(r) ? `${r}` : r.toFixed(1);
    }

    _customRunLabel(owner, kind, num) {
        return kind === 'power'
            ? this.getPowerCircuitLabel(owner, num)
            : this.getPortLabelText(owner, num, 'primary');
    }

    // The refusal the click gets. Tab and ] are named because the run does
    // NOT advance on its own: a click that silently moved the cursor to the
    // next circuit would put the cabinet somewhere the user did not look.
    _customRunFullMessage(owner, kind, num) {
        const cap = this.customRunCapacity(owner, kind);
        const noun = kind === 'power' ? 'Circuit' : 'Port';
        return `${noun} ${this._customRunLabel(owner, kind, num)} is full — `
            + `${cap.describe}. Step to the next ${noun.toLowerCase()} (Tab / ]).`;
    }

    // The small line under the custom controls: the active run's fill against
    // the same cap the badge and the click use, so the limit is on screen
    // while the user is drawing and not only after the refusal.
    _syncCustomFillReadout(kind) {
        const el = document.getElementById(kind === 'power'
            ? 'power-custom-fill-readout' : 'custom-fill-readout');
        if (!el) return;
        const layer = this.currentLayer;
        const editing = layer && (layer.type || 'screen') === 'screen' && (kind === 'power'
            ? this.isCustomPowerEditing(layer) : this.isCustomFlowEditing(layer));
        if (!editing) {
            el.textContent = '';
            el.style.color = '';
            return;
        }
        const num = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        const fill = this.customRunFill(layer, kind, num);
        const head = `${kind === 'power' ? 'Circuit' : 'Port'} ${this._customRunLabel(layer, kind, num)}`;
        if (!fill.known) {
            const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
            const n = this.getResolvedPathPanels(layer,
                (layer[pathsKey] && layer[pathsKey][num]) || []).length;
            el.textContent = `${head}: ${n} panels — no cap (`
                + (kind === 'power'
                    ? 'set voltage, amperage and watts per panel)'
                    : 'no published port capacity for this processor)');
            el.style.color = '';
            return;
        }
        el.textContent = `${head}: ${this._formatRunUsed(fill.used)}/${fill.count} panels`
            + `${fill.full ? ' · full' : ''} (${fill.at})`;
        el.style.color = fill.full ? '#ffcc00' : '';
    }

    /**
     * Append a cabinet to the active port's path. `panelLayer` names the
     * screen the cabinet came from when it is not currentLayer; leaving it out
     * resolves it, so every existing single-screen caller is unchanged.
     *
     * The PORT stays on currentLayer even when the user clicked a peer's
     * cabinet - a port is one physical output on one processor, and only the
     * step records which screen the cable ran onto.
     */
    addPanelToCustomPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomFlowEditing(this.currentLayer)) return;
        if (this.customSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomFlowState(owner);
        const portNum = owner.customPortIndex || 1;
        if (!owner.customPortPaths[portNum]) owner.customPortPaths[portNum] = [];
        // Scoped key, not getPanelKey: R0C0 of the owner and R0C0 of a peer
        // are two different cabinets, and a bare `${row},${col}` compare would
        // refuse to add the second one.
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.customPortPaths[portNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        // Reject if the panel already belongs to a different port, user
        // must clear the existing assignment first. Avoids silent
        // double-mapping that the user has to undo manually.
        const conflict = this._findPanelOwnerPort(owner, panel, portNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'port');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        // Capacity: refused, not advanced. See customRunCapacity.
        if (!this.customRunAccepts(owner, 'data', portNum, source, panel)) {
            if (typeof this._toast === 'function') {
                this._toast(this._customRunFullMessage(owner, 'data', portNum), true);
            }
            return;
        }
        owner.customPortPaths[portNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel port assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.customDebug) {
            console.log('[CustomFlow] Add panel', {
                portNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        this.updatePortLabelEditor();
        this._syncCustomFillReadout('data');
        window.canvasRenderer.render();
    }

    addPanelToCustomPowerPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomPowerEditing(this.currentLayer)) return;
        if (this.powerCustomSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomPowerState(owner);
        const circuitNum = owner.powerCustomIndex || 1;
        if (!owner.powerCustomPaths[circuitNum]) owner.powerCustomPaths[circuitNum] = [];
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.powerCustomPaths[circuitNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        const conflict = this._findPanelOwnerCircuit(owner, panel, circuitNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'circuit');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        // Capacity: refused, not advanced. See customRunCapacity.
        if (!this.customRunAccepts(owner, 'power', circuitNum, source, panel)) {
            if (typeof this._toast === 'function') {
                this._toast(this._customRunFullMessage(owner, 'power', circuitNum), true);
            }
            return;
        }
        owner.powerCustomPaths[circuitNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Power Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel circuit assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.powerCustomDebug) {
            console.log('[CustomPower] Add panel', {
                circuitNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        this._syncCustomFillReadout('power');
        window.canvasRenderer.render();
    }

    /**
     * Where an arrow key takes the path from its current end.
     *
     * Returns `false` when there is nothing drawn yet (the key is NOT ours,
     * the caller lets it fall through), `null` when there is nowhere to go
     * (the key is swallowed, exactly as before), or {layer, panel}.
     */
    // Is the view this path is drawn in mirrored left-to-right?
    //
    // Rear perspective draws the canvas through ctx.scale(-1, 1), so world +X
    // appears on the viewer's LEFT. Anything that turns a user's intent into a
    // world-space direction has to account for that - the screen-name drag
    // already does (canvas.js, `_visualDx`).
    _pathViewIsMirrored(layer) {
        const cr = window.canvasRenderer;
        if (!cr || !layer || typeof cr._effectiveLayerCanvasId !== 'function') return false;
        if (typeof cr._isCanvasMirrored !== 'function') return false;
        const canvases = (this.project && this.project.canvases) || [];
        if (!Array.isArray(canvases)) return false;
        const cid = cr._effectiveLayerCanvasId(layer);
        const canvas = canvases.find(c => c && c.id === cid);
        return !!(canvas && cr._isCanvasMirrored(canvas));
    }

    _stepPathFromLastEntry(ownerLayer, path, dir) {
        if (!Array.isArray(path) || path.length === 0) return false;
        const last = this.resolvePathEntry(ownerLayer, path[path.length - 1]);
        if (!last) return null;
        const drow = dir === 'ArrowUp' ? -1 : (dir === 'ArrowDown' ? 1 : 0);
        let dcol = dir === 'ArrowLeft' ? -1 : (dir === 'ArrowRight' ? 1 : 0);
        // Issue #111: in Rear view the arrows walked the cable backwards -
        // Right went left and Left went right. The keys were never wrong; the
        // CANVAS is mirrored and the step was computed in unmirrored world
        // space. Flip the horizontal component so the cable follows the arrow
        // the user actually pressed. Vertical is unaffected: the mirror is
        // left-to-right only.
        //
        // Applied HERE rather than in handleCustomArrowKey so the cross-member
        // handoff below inherits it too - stepping off the right-hand edge in
        // Rear view has to look for the neighbour on the viewer's right.
        if (dcol !== 0 && this._pathViewIsMirrored(last.layer)) dcol = -dcol;
        // Step inside the END STEP'S OWN grid first. row/col are per-layer
        // indices, and this branch is byte-for-byte what the key did before.
        const within = this.getPanelByRowCol(
            last.layer, last.panel.row + drow, last.panel.col + dcol);
        if (within) return within.hidden ? null : { layer: last.layer, panel: within };
        // Grid edge. Before v0.11.0 the key was swallowed here with no feedback
        // at all, which inside a group is simply wrong: the wall continues, it
        // just continues on a different layer. Hand off GEOMETRICALLY, because
        // a member built from a different cabinet size has a completely
        // different index space - "row + 1" means nothing across the boundary
        // and only world coordinates do.
        return this._panelAcrossPathBoundary(ownerLayer, last, drow, dcol);
    }

    _panelAcrossPathBoundary(ownerLayer, from, drow, dcol) {
        if (!window.canvasRenderer || !from) return null;
        // An arrow key hands the cable to the cabinet the user can see next
        // door, so a hidden member is not a candidate - the same rule the
        // marquee and click-to-add follow. The hidden member's cabinets are
        // still where they were, so this walks PAST it exactly as it walks
        // past a gap: nothing is added and the key is swallowed.
        const peers = this.getSelectionScopeLayers(ownerLayer)
            .filter(l => l && l.id !== from.layer.id);
        if (peers.length === 0) return null;
        const p = from.panel;
        // Probe a hair PAST the edge we just walked off, centred on the other
        // axis. Aiming at "where the next cell would have been" instead would
        // land exactly on a shared cabinet boundary whenever the neighbouring
        // member's cabinets are a different size, and the hit-test is
        // inclusive at both edges - so it would be a coin flip which of the
        // peer's two cabinets answered.
        const eps = 1;
        const lx = p.x + (dcol > 0 ? p.width + eps : (dcol < 0 ? -eps : p.width / 2));
        const ly = p.y + (drow > 0 ? p.height + eps : (drow < 0 ? -eps : p.height / 2));
        const world = this._pathPointToWorld(from.layer, lx, ly);
        if (!world) return null;
        for (const peer of peers) {
            const local = this._pathPointFromWorld(peer, world.x, world.y);
            if (!local) continue;
            const hit = (peer.panels || []).find(q => local.x >= q.x
                && local.x <= q.x + q.width
                && local.y >= q.y && local.y <= q.y + q.height);
            if (hit) return hit.hidden ? null : { layer: peer, panel: hit };
        }
        return null;
    }

    // Layer space -> world, the exact inverse of canvas.js getPanelAt. The
    // offsets belong to the renderer, so they are CALLED here rather than
    // re-derived: a rotated or cross-canvas member would silently drift the
    // day one of them changed there and not here.
    _pathPointToWorld(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (!cr) return null;
        const r = this._rotatePathPoint(layer, lx, ly);
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return { x: r.x + dx + wx, y: r.y + dy + wy };
    }

    _pathPointFromWorld(layer, worldX, worldY) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr._unrotatePointForLayer !== 'function') return null;
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return cr._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
    }

    // Forward rotation. canvas.js ships the inverse (_unrotatePointForLayer)
    // and the pivot geometry (_layerRotationGeom) but not yet this direction;
    // the moment it grows a _rotatePointForLayer this picks it up instead, so
    // the two can never end up disagreeing about where a rotated screen's
    // cabinet actually sits.
    _rotatePathPoint(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (cr && typeof cr._rotatePointForLayer === 'function') {
            return cr._rotatePointForLayer(lx, ly, layer);
        }
        const g = (cr && typeof cr._layerRotationGeom === 'function')
            ? cr._layerRotationGeom(layer) : null;
        if (!g || (g.deg !== 90 && g.deg !== 180 && g.deg !== 270)) return { x: lx, y: ly };
        const rad = g.deg * Math.PI / 180;
        const cos = Math.cos(rad), sin = Math.sin(rad);
        const dx = lx - g.cx, dy = ly - g.cy;
        return { x: g.cx + (dx * cos - dy * sin), y: g.cy + (dx * sin + dy * cos) };
    }

    handleCustomArrowKey(e) {
        const dir = e.code;
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(dir)) return false;
        if (!this.currentLayer) return false;
        const isPower = window.canvasRenderer && window.canvasRenderer.viewMode === 'power';
        if (isPower) {
            if (!this.isCustomPowerEditing(this.currentLayer)) return false;
            this.ensureCustomPowerState(this.currentLayer);
            const circuitNum = this.currentLayer.powerCustomIndex || 1;
            const path = this.currentLayer.powerCustomPaths[circuitNum] || [];
            const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
            if (next === false) return false;
            if (next) this.addPanelToCustomPowerPath(next.panel, next.layer);
            return true;
        }
        if (!this.isCustomFlowEditing(this.currentLayer)) return false;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = this.currentLayer.customPortPaths[portNum] || [];
        const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
        if (next === false) return false;
        if (next) this.addPanelToCustomPath(next.panel, next.layer);
        return true;
    }

    // The wall lattice a pattern is ordered on. ONE implementation, and it is
    // the renderer's getPositionLattice - the same one the cabinet ID numbers
    // are assigned with (canvas.js _groupNumberingPlan). Two copies would
    // eventually disagree, and a serpentine that snakes the wall in a different
    // order than the IDs read is worse than no serpentine at all. It lives on
    // the renderer because the ranking needs getLayerRenderOffset.
    //
    // Null only when the renderer is missing entirely, and _orderPicksForPattern
    // then falls back to the panels' own row/col - the ordering this had before
    // v0.11.0. A degradation, deliberately, rather than a second lattice.
    _pathLattice(ownerLayer) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr.getPositionLattice !== 'function') return null;
        return cr.getPositionLattice(this.getPathScopeLayers(ownerLayer));
    }

    /**
     * The cabinets a scoped selection Set actually names, as {layer, panel}.
     *
     * Walked in path-scope order (owner first, then peers in group order) and
     * then in each member's own panel order, so an ungrouped screen yields the
     * exact list - and the exact order - the old `currentLayer.panels.filter()`
     * did. Hidden cabinets are dropped here, matching that filter.
     */
    _selectedPathPanels(ownerLayer, selection) {
        const out = [];
        if (!ownerLayer || !selection || selection.size === 0) return out;
        // Selection scope again, so a key that was already in the Set when its
        // screen was hidden cannot be committed by a later Apply Pattern. The
        // marquee is filtered at source; this is the same rule applied at the
        // moment of writing, which is the one that reaches the wall.
        this.getSelectionScopeLayers(ownerLayer).forEach(member => {
            if (!member || !Array.isArray(member.panels)) return;
            member.panels.forEach(panel => {
                if (panel.hidden) return;
                if (selection.has(this.getScopedPanelKey(member.id, panel))) {
                    out.push({ layer: member, panel });
                }
            });
        });
        return out;
    }

    /**
     * Put a cross-member selection into pattern order.
     *
     * The picks are placed on the WALL LATTICE (canvas.js getPositionLattice:
     * every member's column and row slots pooled and ranked by where they
     * physically sit), the lattice is compacted to just the rows and columns
     * the selection actually touches - exactly what the old uniqueRows /
     * uniqueCols pass did, only over positions rather than indices - and
     * getPatternOrderForGrid walks it. A serpentine therefore alternates
     * direction per LATTICE row and snakes across the whole wall instead of
     * per member.
     *
     * WHY position and not row/col indices. A 1m member's row 1 and a 0.5m
     * member's row 1 are different physical heights, so a pattern ordered by
     * the panels' own indices - which is what this did - zig-zags through an
     * order that exists nowhere on site. A cabinet spanning two lattice rows
     * ranks by its own top-left, exactly as step 5 numbers it.
     *
     * For a single ungrouped screen the lattice ranks that screen's own columns
     * by x and rows by y, which for any grid _build_panels produces is the
     * column and row index itself. The compacted grid is therefore identical
     * to the one this built before, and so is the order.
     *
     * The bucket is for genuinely OVERLAPPING members - two cabinets whose
     * top-left corners coincide land in one lattice cell. A plain grid write
     * would drop one of them from the path with no error; keeping the cell's
     * later arrivals and emitting them right behind the representative means a
     * selected cabinet can never silently vanish.
     */
    _orderPicksForPattern(ownerLayer, pattern, picks, grid = null) {
        if (!picks || picks.length === 0) return [];
        const g = grid || this._latticeGridForPicks(ownerLayer, picks);
        const ordered = this.getPatternOrderForGrid(pattern, g.grid);
        const out = [];
        ordered.forEach(pick => {
            const group = g.bucket.get(pick);
            if (group) out.push(...group);
            else out.push(pick);
        });
        return out;
    }

    // The picks laid out on the wall lattice, compacted to a dense grid: the
    // step above that getPatternOrderForGrid then walks.
    //
    // Split out of _orderPicksForPattern - not a second copy of it - because
    // automatic routing across a group's members (app-screen-info.js
    // getAutoRoutePlan) needs the same ranking AND needs to keep each cabinet's
    // compacted row and column afterwards: the Organized branch of the port and
    // circuit walks packs whole rows or columns, and on a group those are the
    // WALL's rows and columns, not one member's. Every expression here came
    // across unchanged, so the hand-drawn Apply Pattern order is untouched.
    _latticeGridForPicks(ownerLayer, picks) {
        const lattice = this._pathLattice(ownerLayer);
        const cells = (picks || []).map(pick => ({
            pick,
            row: lattice ? lattice.rowOf(pick.layer, pick.panel) : pick.panel.row,
            col: lattice ? lattice.colOf(pick.layer, pick.panel) : pick.panel.col,
        }));

        const uniqueRows = [...new Set(cells.map(c => c.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(cells.map(c => c.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const grid = Array.from({ length: uniqueRows.length },
            () => Array(uniqueCols.length).fill(null));
        const bucket = new Map();   // representative pick -> every pick in its cell
        // Panel object -> its compacted slot. Keyed by the object because
        // `${row},${col}` is exactly the address that names two cabinets at once
        // inside a group, which is the whole reason this lattice exists.
        const rowOf = new Map();
        const colOf = new Map();
        cells.forEach(c => {
            const r = rowIndex.get(c.row);
            const k = colIndex.get(c.col);
            rowOf.set(c.pick.panel, r);
            colOf.set(c.pick.panel, k);
            const held = grid[r][k];
            if (held === null) {
                grid[r][k] = c.pick;
                bucket.set(c.pick, [c.pick]);
            } else {
                bucket.get(held).push(c.pick);
            }
        });

        return {
            grid, bucket, rowOf, colOf,
            rows: uniqueRows.length, cols: uniqueCols.length,
        };
    }

    applyPatternToSelection(pattern) {
        this._applyPatternFill('data', pattern);
    }

    applyPowerPatternToSelection(pattern) {
        this._applyPatternFill('power', pattern);
    }

    // The pattern buttons on a selection, both sides through ONE walk.
    //
    // Used to write the WHOLE selection into the one active port or circuit.
    // Now it walks the selection in pattern order, a whole row (or column)
    // at a time, and fills the active run with as many whole lines as its
    // capacity takes (customRunCapacity - the sidebar's Panels/Circuit and
    // Panels/Port), then steps to the next number and keeps going until the
    // selection is consumed: a 14 x 6 block on serpentine at 14 a circuit
    // is circuits 1..6 at 14 apiece, in one gesture, every one of them read
    // from the side the first one started on; 18-wide rows at 24 a circuit
    // are one row per circuit, not 24-and-a-bit.
    //
    // The numbers it fills are OVERWRITTEN - the active one always was, and
    // the ones it advances into are told on in the toast. A cabinet already
    // on a run OUTSIDE that set is a conflict and nothing is written, the
    // rule this has always had. One undo entry for the whole fill, and the
    // active index ends on the LAST number filled so the badge names what
    // was just drawn.
    //
    // With one overridden run open for redrawing, the numbers the fill may
    // step into are the layer's overrides after the open one - the same list
    // Tab walks - and a selection that needs more than those is refused
    // rather than spilled onto runs the user never took over.
    _applyPatternFill(kind, pattern) {
        const isPower = kind === 'power';
        if (!this.currentLayer || !window.canvasRenderer) return;
        // The PORT / CIRCUIT stays on currentLayer even when the selection
        // spans peers - a port is one physical output on one processor. Only
        // the individual step records which screen the cable ran onto.
        const owner = this.currentLayer;
        if (isPower ? !this.isCustomPowerEditing(owner) : !this.isCustomFlowEditing(owner)) return;
        const selection = isPower ? this.powerCustomSelection : this.customSelection;
        if (!selection || selection.size === 0) return;
        if (isPower) this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        const picks = this._selectedPathPanels(owner, selection);
        if (picks.length === 0) return;

        const lattice = this._latticeGridForPicks(owner, picks);
        const lines = this._patternLines(pattern, lattice.grid, lattice.bucket);
        if (lines.length === 0) return;

        const pathsKey = isPower ? 'powerCustomPaths' : 'customPortPaths';
        const idxKey = isPower ? 'powerCustomIndex' : 'customPortIndex';
        const noun = isPower ? 'circuit' : 'port';
        const startNum = owner[idxKey] || 1;
        const toast = (msg, isError) => {
            if (typeof this._toast === 'function') this._toast(msg, isError);
        };

        const cut = this._chunkPicksByCapacity(owner, kind, startNum, lines);
        if (cut.error) {
            toast(`Cannot apply: ${cut.error}`, true);
            return;
        }
        const chunks = cut.chunks;
        // The picks in the order they were dealt, run after run.
        const ordered = chunks.flatMap(c => c.picks);
        if (ordered.length === 0) return;
        const filled = new Set(chunks.map(c => c.num));

        // Reject the entire apply if any selected panel already belongs to a
        // run this fill will not overwrite. Prevents silent double-mapping.
        // The claim may live on a peer, which is why the sample names both
        // the cabinet's screen and the conflicting run's.
        const conflicts = [];
        for (const pick of ordered) {
            const claim = isPower
                ? this._findPanelOwnerCircuit(owner, pick.panel, startNum, pick.layer)
                : this._findPanelOwnerPort(owner, pick.panel, startNum, pick.layer);
            if (!claim) continue;
            if (!claim.foreign && filled.has(claim.number)) continue;
            conflicts.push({ pick, owner: claim });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `${this._describePathPanel(owner, c.pick.layer, c.pick.panel)}→${this._describePathConflict(c.owner, noun)}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ${noun}s, ${sample}${more}.`, true);
            return;
        }

        // Runs beyond the active one that held a drawing before this fill
        // replaced it - the toast says so.
        const replaced = chunks.map(c => c.num).filter(n => n !== startNum
            && ((owner[pathsKey][n] || []).length > 0));
        // makePathEntry omits layerId for the owner's own cabinets, so a path
        // that never leaves its screen is byte-for-byte the shape it has
        // always been written in.
        chunks.forEach(c => {
            owner[pathsKey][c.num] = c.picks
                .map(pick => this.makePathEntry(owner, pick.layer, pick.panel));
        });
        const lastNum = chunks[chunks.length - 1].num;
        owner[idxKey] = lastNum;
        if (this._overrideEditing && this._overrideEditing.kind === kind
                && this._overrideEditing.layerId === owner.id) {
            this._overrideEditing.num = lastNum;
        }
        this.saveState(isPower ? 'Power Custom Pattern Apply' : 'Custom Pattern Apply');
        this.saveClientSideProperties();
        // PUT to server so the bulk pattern assignment persists. The OWNER is
        // added explicitly - a marquee that ended on a peer can leave
        // currentLayer out of the layer selection entirely.
        this.updateLayers(this._pathPersistLayers(owner));
        if (chunks.length > 1) {
            const cap = this.customRunCapacity(owner, kind);
            const lineNoun = String(pattern).endsWith('-v') ? 'column' : 'row';
            let msg = `Filled ${noun}s ${this._customRunLabel(owner, kind, chunks[0].num)} to `
                + `${this._customRunLabel(owner, kind, lastNum)} from the selection`
                + ` (whole ${lineNoun}s, up to ${cap.count} panels each at ${cap.at})`;
            if (replaced.length > 0) {
                msg += `; replaced ${noun}${replaced.length === 1 ? '' : 's'} `
                    + replaced.map(n => this._customRunLabel(owner, kind, n)).join(', ');
            }
            toast(`${msg}.`, false);
        }
        if (isPower ? this.powerCustomDebug : this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log(isPower ? '[CustomPower] Apply pattern' : '[CustomFlow] Apply pattern', {
                pattern,
                startNum,
                lastNum,
                count: ordered.length,
                runs: chunks.map(c => ({ num: c.num, count: c.picks.length })),
                first: first ? { row: first.panel.row, col: first.panel.col, layerId: first.layer.id } : null,
                last: last ? { row: last.panel.row, col: last.panel.col, layerId: last.layer.id } : null
            });
        }
        // The marquee has done its job: drop it, so the next arrow key or
        // cabinet click draws on the last run filled instead of being
        // swallowed by a pending selection (addPanelToCustomPath returns on
        // one). A REFUSED fill above keeps the selection so the user can fix
        // the conflict and press the tile again. User's ruling, 2026-09-22.
        selection.clear();
        if (isPower) {
            this.updateCustomPowerUI();
        } else {
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        window.canvasRenderer.render();
    }

    // The next number a fill may step into after `num`: the open number line
    // in whole-screen custom, the layer's override list while one overridden
    // run is being redrawn (null when that list is exhausted). Mirrors
    // _steppedCustomIndex, which is what Tab does.
    _nextCustomRunNumber(owner, kind, num) {
        if (!this._isOverrideEditing(owner, kind)) return num + 1;
        const nums = this.getOverrideNums(owner, kind);
        const at = nums.indexOf(num);
        return (at >= 0 && at + 1 < nums.length) ? nums[at + 1] : null;
    }

    // Cut the pattern's lines into runs at capacity: [{num, picks, load}]
    // starting at `startNum`. No cap known means one run with everything.
    //
    // THE WALK is by whole LINES - rows for a horizontal pattern, columns
    // for a vertical one - the same unit the automatic Organized walk packs
    // (calculatePowerAssignments). A run takes a line only when the WHOLE
    // line still fits; a line that does not fit opens the next run. The
    // user, 2026-09-22, with 18-wide rows at 24 a circuit: "it is supposed
    // to start at the beginning and then fill a max, not jump down a row
    // unless it fits a whole other row/column." Before this the fill poured
    // cabinets in and cut wherever the cap fell, so circuit 1 was row 0 plus
    // the far end of row 1 read backwards, and circuit 2 the rest of row 1
    // plus most of row 2 - runs that started nowhere a cable comes from.
    //
    // Within one run the lines snake - the first in the pattern's own
    // direction, the next back, and so on - because a run is one cable
    // daisy-chained through the block. A NEW run does not continue the
    // snake: it starts again from the pattern's start side, because its
    // cable comes from where the first one's came from. The user,
    // 2026-09-04, on a 14-wide wall at 14 a circuit: "the next row needs
    // to restart on the same side as the serpentine started. because the
    // cables typically come from the same side."
    //
    // A line LONGER than a run on its own (28 wide at 14 a circuit) is the
    // one case a line is cut: it is filled from its start to the cap, run
    // after run, and the remainder is a run of its own. The run in hand is
    // closed first - a run that ended part-way along the line above would
    // otherwise start this one mid-row.
    //
    // `error` instead when a single cabinet is over the cap on its own or
    // the override list runs out - nothing is written in either case.
    _chunkPicksByCapacity(owner, kind, startNum, lines) {
        const cap = this.customRunCapacity(owner, kind);
        const limit = cap.known ? cap.limit : Infinity;
        const eps = CUSTOM_RUN_EPS;
        const noun = kind === 'power' ? 'circuit' : 'port';
        const fmt = (v) => (kind === 'power'
            ? `${Math.round(v).toLocaleString()} W` : `${Math.round(v).toLocaleString()} px`);
        const loadOf = (pick) => this.customHitLoad(kind, pick.layer, pick.panel);
        const chunks = [];
        let cur = { num: startNum, picks: [], load: 0 };
        let lineInRun = 0;
        // Close the run in hand and open the next number - or say why not.
        const closeRun = () => {
            chunks.push(cur);
            const next = this._nextCustomRunNumber(owner, kind, cur.num);
            if (next === null) {
                const taken = this.getOverrideNums(owner, kind)
                    .map(n => this._customRunLabel(owner, kind, n)).join(', ');
                return `the selection does not fit on the taken-over `
                    + `${noun}s (${taken}) - ${cap.describe}. Take over another `
                    + `run or select a narrower block.`;
            }
            cur = { num: next, picks: [], load: 0 };
            lineInRun = 0;
            return null;
        };
        const lay = (seq) => {
            for (const pick of seq) {
                cur.picks.push(pick);
                cur.load += loadOf(pick);
            }
        };
        for (const line of lines) {
            // An empty line (hidden cabinets, a group's gap) still counts
            // toward the snake's alternation - the rule this has always had.
            if (line.length === 0) {
                lineInRun += 1;
                continue;
            }
            for (const pick of line) {
                const load = loadOf(pick);
                if (cap.known && load > limit + eps) {
                    return { error: `panel ${this._describePathPanel(owner, pick.layer, pick.panel)} `
                        + `is ${fmt(load)} and a ${noun} carries ${fmt(limit)}.` };
                }
            }
            const lineLoad = line.reduce((s, pick) => s + loadOf(pick), 0);
            if (lineLoad <= limit + eps) {
                // A whole line: onto the run in hand if it fits, else it
                // opens the next run from the start side.
                if (cur.picks.length > 0 && cur.load + lineLoad > limit + eps) {
                    const why = closeRun();
                    if (why) return { error: why };
                }
                lay(lineInRun % 2 === 1 ? line.slice().reverse() : line);
                lineInRun += 1;
                continue;
            }
            // Longer than a run on its own: cut it, from its start, run
            // after run. Never onto a run already holding part of the
            // line above.
            if (cur.picks.length > 0) {
                const why = closeRun();
                if (why) return { error: why };
            }
            let cells = line;
            while (cells.length > 0) {
                let took = 0;
                for (const pick of cells) {
                    const load = loadOf(pick);
                    if (cur.picks.length > 0 && cur.load + load > limit + eps) break;
                    cur.picks.push(pick);
                    cur.load += load;
                    took += 1;
                }
                cells = cells.slice(took);
                if (cells.length > 0) {
                    const why = closeRun();
                    if (why) return { error: why };
                }
            }
            // The remainder is the first line on its run, read in the
            // pattern's direction; a line that follows it snakes back.
            lineInRun = 1;
        }
        chunks.push(cur);
        return { chunks };
    }

    // The compacted grid's lines - rows for a horizontal-first pattern,
    // columns for a vertical-first one - in the order the pattern visits
    // them, each line's cells in the pattern's own direction and never
    // reversed here. The serpentine's alternation belongs to whoever walks
    // the lines: getPatternOrderForGrid for one continuous snake,
    // _chunkPicksByCapacity per run. ONE home for the corner and direction
    // logic, so the two walks cannot drift apart. `bucket` expands a
    // representative pick into every pick sharing its cell.
    _patternLines(pattern, grid, bucket = null) {
        const rows = grid.length;
        const cols = rows > 0 ? grid[0].length : 0;
        if (rows === 0 || cols === 0) return [];

        const [startCorner, direction] = pattern.split('-');
        let startRow, startCol, rowDir, colDir;

        switch (startCorner) {
            case 'tl':
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1; break;
            case 'tr':
                startRow = 0; startCol = cols - 1; rowDir = 1; colDir = -1; break;
            case 'bl':
                startRow = rows - 1; startCol = 0; rowDir = -1; colDir = 1; break;
            case 'br':
                startRow = rows - 1; startCol = cols - 1; rowDir = -1; colDir = -1; break;
            default:
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1;
        }

        const expand = (pick) => (bucket && bucket.get(pick)) || [pick];
        const lines = [];
        if (direction === 'v') {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const line = [];
                for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                    if (grid[r] && grid[r][c]) line.push(...expand(grid[r][c]));
                }
                lines.push(line);
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const line = [];
                for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                    if (grid[r] && grid[r][c]) line.push(...expand(grid[r][c]));
                }
                lines.push(line);
            }
        }
        return lines;
    }

    // One continuous snake over the grid: the first line in the pattern's
    // own direction, every second line back. A line that is empty (hidden
    // cabinets, or a group's gap) still counts, so it does not reverse the
    // line after it - the rule this has always had.
    getPatternOrderForGrid(pattern, grid) {
        const ordered = [];
        this._patternLines(pattern, grid).forEach((line, i) => {
            ordered.push(...(i % 2 === 1 ? line.slice().reverse() : line));
        });
        return ordered;
    }
}

for (const k of Object.getOwnPropertyNames(_CustomRuns.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CustomRuns.prototype, k));
    }
}
