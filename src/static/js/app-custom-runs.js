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
    //          Latency factor included) against the run's load as the port's
    //          badge charges it (customRunLoad: the enclosing rectangle on
    //          NovaStar Armor, the sum of pixel areas elsewhere), and then, for the run's OWN cabinets, the two per-port rules
    //          the automatic walk applies (calculatePortAssignments): the
    //          NovaStar Low Latency (1 - Y/H) derate from the run's topmost
    //          cabinet, and the NovaStar 5G 128 px narrow-port penalty from
    //          the run's bounding box, in that order. Both are read through
    //          the renderer's getPortCapacityForPanels - the figure the
    //          port's load badge is drawn against - so the cut, the click,
    //          the readout and the badge use one number (1.5 audit: custom
    //          used the flat table figure and could fill a port past what
    //          automatic would give it).
    // Nothing is re-derived here, so a capacity change lands in both.
    //
    // A run is FULL when one more whole cabinet would not fit; a click is
    // refused when THAT cabinet would not fit, so a half-tile can still land
    // on a run the badge calls full - the badge speaks of whole cabinets. No
    // capacity at all (no voltage or wattage set, no published pixel figure
    // for the processor) means no cap, and the run takes whatever is drawn
    // exactly as it always has.
    //
    // `panels` (data only): the cabinets of the run being judged. Left out,
    // the limit is the plain per-port figure, which is also what an empty
    // run reads.
    customRunCapacity(layer, kind, panels = null) {
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
        const base = this.calculatePortCapacity(
            layer.bitDepth || 8, layer.frameRate || 60,
            layer.processorType || 'novastar-armor', !!layer.lowLatency);
        const limit = (base > 0 && Array.isArray(panels))
            ? this._customPortLimit(layer, panels, base) : base;
        const unit = this.getFullPanelPixels(layer);
        if (!(limit > 0 && unit > 0)) return none;
        const count = Math.floor(limit / unit);
        const at = `${limit.toLocaleString('en-US')} px/port`;
        return { known: true, limit, unit, count, at,
            describe: `${count} panels at ${at}` };
    }

    // The limit of one port carrying `panels`, owned by `layer`: the
    // renderer's getPortCapacityForPanels (table figure, then the Low Latency
    // (1 - Y/H) derate, then the 5G narrow-port penalty - the order
    // calculatePortAssignments uses). Without a renderer, the plain figure.
    _customPortLimit(layer, panels, base) {
        const cr = (typeof window !== 'undefined') ? window.canvasRenderer : null;
        if (!cr || typeof cr.getPortCapacityForPanels !== 'function') return base;
        const limit = cr.getPortCapacityForPanels(layer, panels || []);
        return limit > 0 ? limit : 0;
    }

    // What ONE cabinet costs against the run it is being drawn onto. A data
    // run is NOT always the sum of these - see customRunLoad, which is what
    // every judgement of a whole run goes through.
    customHitLoad(kind, hitLayer, panel) {
        if (!panel) return 0;
        if (kind === 'power') {
            return (parseFloat(hitLayer && hitLayer.panelWatts) || 0)
                * this.getPanelLoadFactor(hitLayer, panel);
        }
        return this.getPanelPixelArea(panel);
    }

    // What a whole run costs: `hits` are {layer, panel} pairs, the shape
    // getResolvedPathPanels and the pattern fill's picks both carry.
    //   power  the sum of each cabinet's watt-equivalent (customHitLoad).
    //   data   the renderer's getPortPixelLoad over the run's cabinets - the
    //          very number the port's load badge is drawn from, so the click,
    //          the cut, the readout and the badge use ONE load rule for every
    //          processor: NovaStar Armor pays for the pixel rectangle that
    //          encloses the run's cabinets, holes and all (its reserved-
    //          rectangle rule, as the automatic map charges it); every other
    //          processor pays the sum of the cabinets' pixel areas (1.5 audit:
    //          custom summed on Armor too, so an L along the top row and down
    //          the side took 19 cabinets onto a port the badge called 248%).
    //          Without a renderer, the plain sum.
    // Owned by `owner` - the processor the port is on decides the rule.
    customRunLoad(owner, kind, hits) {
        const list = (hits || []).filter(h => h && h.panel);
        if (kind !== 'power') {
            const cr = (typeof window !== 'undefined') ? window.canvasRenderer : null;
            if (owner && cr && typeof cr.getPortPixelLoad === 'function') {
                return cr.getPortPixelLoad(owner, list.map(h => h.panel)) || 0;
            }
        }
        return list.reduce((s, h) => s + this.customHitLoad(kind, h.layer, h.panel), 0);
    }

    // One run's fill: the load drawn so far, the cap it is drawn against, and
    // whether another whole cabinet still fits. `used` is in whole-cabinet
    // equivalents so the badge can read "9/14".
    //
    // A RUN OVER TWO KINDS OF CABINET (2026-10-16, the owner: "Pixels" for
    // data, "watts for mixed" for power). The cap is pixels (data) or watts
    // (power) either way, but a cabinet COUNT only means something for one
    // kind of cabinet: a 192x384 and a 192x192 cabinet are two different
    // fractions of a port, a 200 W and a 115 W cabinet two different
    // fractions of a circuit. So the count is taken in the cabinets the run
    // is actually made of (_customRunSizing): one kind reads "9/17" exactly
    // as before - in that kind's cabinets, which is the owner's own for
    // every run that never leaves its screen - and a run, or the selection
    // being drawn onto it, that covers more than one reads load against
    // cap, "622,592 / 659,722 px" or "1,230 / 4,160 W", the very figures
    // the cut weighs. `mixed` says which; `text` is the "used/count" or the
    // load pair.
    customRunFill(owner, kind, num) {
        const isPower = kind === 'power';
        const pathsKey = isPower ? 'powerCustomPaths' : 'customPortPaths';
        const path = (owner && owner[pathsKey] && owner[pathsKey][num]) || [];
        const hits = this.getResolvedPathPanels(owner, path);
        const cap = this.customRunCapacity(owner, kind, hits.map(h => h.panel));
        const load = this.customRunLoad(owner, kind, hits);
        const eps = CUSTOM_RUN_EPS;
        let sized = Object.assign({ mixed: false }, cap);
        if (cap.known) {
            const layers = hits.map(h => h.layer);
            // The pending marquee is drawn onto this run next, so it counts
            // toward what the readout has to describe.
            const sel = isPower ? this.powerCustomSelection : this.customSelection;
            if (owner && owner === this.currentLayer && sel && sel.size > 0) {
                this._selectedPathPanels(owner, sel).forEach(p => layers.push(p.layer));
            }
            sized = Object.assign({}, cap, this._customRunSizing(owner, kind, layers, cap));
        }
        // NovaStar Armor (a rectangle processor) pays for the rectangle that
        // encloses the run, so its load is no count of cabinets: an L of 7
        // read "12/16". `used` there is the cabinets actually placed (their
        // own pixel areas, a half-tile a fraction) - the figure every other
        // processor's load already is - and the run is full when no free
        // cabinet would still be accepted (_customRunCanGrow): one more
        // cabinet can grow the rectangle by a whole row or column, so
        // "another cabinet's worth of pixels left" says nothing there.
        const rect = !isPower && typeof this.usesRectangleConstraint === 'function'
            && this.usesRectangleConstraint((owner && owner.processorType) || 'novastar-armor');
        const placed = rect
            ? hits.reduce((s, h) => s + this.getPanelPixelArea(h.panel), 0) : load;
        const used = sized.unit > 0 ? placed / sized.unit : 0;
        const full = cap.known && (rect
            ? !this._customRunCanGrow(owner, kind, hits)
            : (load + sized.unit > cap.limit + eps));
        const fill = Object.assign({}, sized, { load, used, full });
        fill.text = fill.mixed
            ? this._formatRunLoadPair(kind, load, cap.limit)
            : `${this._formatRunUsed(used)}/${sized.count}`;
        if (fill.mixed) fill.describe = fill.text;
        return fill;
    }

    // "622,592 / 659,722 px", "1,230 / 4,160 W" - load against cap in the
    // unit the cut weighs, whole numbers with thousands separators.
    _formatRunLoadPair(kind, load, limit) {
        const unit = kind === 'power' ? 'W' : 'px';
        return `${Math.round(load).toLocaleString('en-US')} / ${Math.round(limit).toLocaleString('en-US')} ${unit}`;
    }

    // The kinds of cabinet a run (or a selection) is made of, and the count
    // its readout is taken in. `layers` are the members its cabinets sit
    // on, repeats welcome. A kind is the cabinet SIZE for data (its full
    // pixel area is what a port weighs) and the member's panelWatts for
    // power (what a circuit weighs).
    //   one kind     unit/count/describe in THAT kind's cabinets (the
    //                owner's own when the run never leaves its screen)
    //   two or more  mixed: no honest count. The unit kept is the smallest
    //                cabinet, so "full" still means not one more whole
    //                cabinet of the run's own kinds fits.
    //   none         the owner's figures, as before.
    // `cap` is the run's own capacity when the caller already has it (a
    // data run's limit depends on its cabinets); left out, the plain figure.
    _customRunSizing(owner, kind, layers, cap = null) {
        cap = cap || this.customRunCapacity(owner, kind);
        const out = { mixed: false, unit: cap.unit, count: cap.count, describe: cap.describe };
        if (!cap.known) return out;
        const isPower = kind === 'power';
        const units = new Map();
        (layers || []).forEach(l => {
            if (!l) return;
            const unit = isPower ? (parseFloat(l.panelWatts) || 0) : this.getFullPanelPixels(l);
            const key = isPower
                ? `${unit}`
                : `${Number(l.cabinet_width) || 0}x${Number(l.cabinet_height) || 0}`;
            if (!units.has(key)) units.set(key, unit);
        });
        const found = [...units.values()].filter(u => u > 0);
        if (found.length === 0) return out;
        if (found.length > 1) {
            out.mixed = true;
            out.unit = Math.min(...found);
            out.count = Math.floor(cap.limit / out.unit);
            out.describe = `${Math.round(cap.limit).toLocaleString('en-US')} ${isPower ? 'W a circuit' : 'px a port'}`;
            return out;
        }
        out.unit = found[0];
        out.count = Math.floor(cap.limit / out.unit);
        out.describe = `${out.count} panels at ${cap.at}`;
        return out;
    }

    // Does this cabinet still fit on the run? Judged as the run would be
    // WITH it, load and limit both - on Low Latency or 5G a cabinet can move
    // the port's limit, and on Armor it can grow the rectangle the port pays
    // for by a whole row or column (customRunLoad), exactly as the automatic
    // walk and the pattern fill's cut weigh it.
    customRunAccepts(owner, kind, num, hitLayer, panel) {
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const path = (owner && owner[pathsKey] && owner[pathsKey][num]) || [];
        const hits = this.getResolvedPathPanels(owner, path)
            .concat(panel ? [{ layer: hitLayer, panel }] : []);
        const cap = this.customRunCapacity(owner, kind, hits.map(h => h.panel));
        if (!cap.known) return true;
        return this.customRunLoad(owner, kind, hits) <= cap.limit + CUSTOM_RUN_EPS;
    }

    // Would ANY free cabinet still be accepted onto this run? `hits` are the
    // run's resolved cabinets. A candidate is every visible cabinet on the
    // run's screens (the owner and the group peers its path may reach) that
    // no run of this kind holds yet - the cabinets a click could add - judged
    // exactly as customRunAccepts judges a click: load and limit both, with
    // the cabinet. The first one that fits answers, holes inside the run's
    // rectangle (free on Armor) first. On a rectangle processor a cabinet
    // whose rectangle with the run is bigger than the port's plain figure is
    // skipped unweighed - no derate ever raises a limit above that figure -
    // so a full run on a big wall costs one bounding-box sum per cabinet.
    _customRunCanGrow(owner, kind, hits) {
        if (!owner) return false;
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const scope = typeof this.getPathScopeLayers === 'function'
            ? this.getPathScopeLayers(owner) : [owner];
        const taken = new Set();
        for (const l of scope) {
            for (const path of Object.values((l && l[pathsKey]) || {})) {
                for (const e of path || []) {
                    if (e) taken.add(this.getScopedPanelKey(this.getPathEntryLayerId(l, e), e));
                }
            }
        }
        const rect = kind !== 'power' && typeof this.usesRectangleConstraint === 'function'
            && this.usesRectangleConstraint(owner.processorType || 'novastar-armor');
        const base = rect ? this.customRunCapacity(owner, kind).limit : 0;
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        for (const h of hits) {
            const p = h.panel;
            x1 = Math.min(x1, Number(p.x) || 0);
            y1 = Math.min(y1, Number(p.y) || 0);
            x2 = Math.max(x2, (Number(p.x) || 0) + (Number(p.width) || 0));
            y2 = Math.max(y2, (Number(p.y) || 0) + (Number(p.height) || 0));
        }
        const inside = [], outside = [];
        for (const l of scope) {
            if (!l || l.visible === false || !Array.isArray(l.panels)) continue;
            for (const p of l.panels) {
                if (!p || p.hidden || taken.has(this.getScopedPanelKey(l.id, p))) continue;
                const px = Number(p.x) || 0, py = Number(p.y) || 0;
                const qx = px + (Number(p.width) || 0), qy = py + (Number(p.height) || 0);
                if (rect && hits.length) {
                    const area = (Math.max(x2, qx) - Math.min(x1, px))
                        * (Math.max(y2, qy) - Math.min(y1, py));
                    if (area > base + CUSTOM_RUN_EPS) continue;
                }
                const within = hits.length && px >= x1 && py >= y1 && qx <= x2 && qy <= y2;
                (within ? inside : outside).push({ layer: l, panel: p });
            }
        }
        for (const c of inside.concat(outside)) {
            const all = hits.concat([c]);
            const cap = this.customRunCapacity(owner, kind, all.map(h => h.panel));
            if (!cap.known) return true;
            if (this.customRunLoad(owner, kind, all) <= cap.limit + CUSTOM_RUN_EPS) return true;
        }
        return false;
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
        const cap = this.customRunFill(owner, kind, num);
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
        el.textContent = fill.mixed
            ? `${head}: ${fill.text}${fill.full ? ' · full' : ''}`
            : `${head}: ${fill.text} panels${fill.full ? ' · full' : ''} (${fill.at})`;
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
        // A locked screen stays unchanged (the owner's ruling, 2026-10-16):
        // neither its own runs nor its cabinets take a new step.
        if (owner.locked || source.locked) {
            this._showLockedError([owner, source].filter(l => l.locked));
            return;
        }
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
        // Locked screens stay unchanged - see addPanelToCustomPath.
        if (owner.locked || source.locked) {
            this._showLockedError([owner, source].filter(l => l.locked));
            return;
        }
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
            // Read, never ensure*: the step itself (addPanelToCustomPowerPath)
            // makes the state after its lock check, so a locked screen is
            // not written by the key.
            const circuitNum = this.currentLayer.powerCustomIndex || 1;
            const path = (this.currentLayer.powerCustomPaths || {})[circuitNum] || [];
            const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
            if (next === false) return false;
            if (next) this.addPanelToCustomPowerPath(next.panel, next.layer);
            return true;
        }
        if (!this.isCustomFlowEditing(this.currentLayer)) return false;
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = (this.currentLayer.customPortPaths || {})[portNum] || [];
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

    // A pattern tile pressed while the shown screen is drawn by hand. Returns
    // true when the tile is spent here and must NOT fall through to the
    // automatic pattern write - which is always the case in custom mode: a
    // tile never takes a screen out of custom mode (the owner's ruling,
    // 2026-10-16). Before this, a tile with no cabinets selected fell
    // through, wrote the pattern to the selection and its group, and the
    // screen left custom mode while the box stayed ticked.
    //
    //   cabinets selected        the selection is filled, as it always was
    //   no cabinets, a screen    every cabinet of the selected screens the
    //   or group selected        owner's runs can reach is REFILLED from run
    //                            1 ("if a group is selected, then it should
    //                            [fill]"): the runs already on those
    //                            cabinets are cleared and the pattern laid
    //                            out from run 1, one undo step. So a second
    //                            tile re-lays the same cabinets in the new
    //                            pattern instead of being refused because the
    //                            first tile's runs hold them (1.5 audit: tl-h
    //                            then tl-v on the 20 x 4 over 20 x 1 wall
    //                            read "97 panels already wired to other
    //                            ports").
    //   nothing selected         nothing happens ("if the group is not
    //                            selected, then it should do nothing")
    //
    // The whole-screen branch borrows the cabinet selection to drive the
    // fill and ALWAYS hands it back as it found it - on success and on a
    // refusal alike. The audit found the borrowed keys left behind after a
    // refusal, where they swallowed every later cabinet click
    // (addPanelToCustomPath returns while a selection is pending).
    //
    // An overridden run open for redrawing on an AUTOMATIC screen keeps its
    // old split: with cabinets selected the tile fills them, with none it
    // falls through and sets the screen's automatic pattern, because that
    // screen is not in custom mode.
    applyPatternTileInCustom(kind, pattern) {
        const isPower = kind === 'power';
        const owner = this.currentLayer;
        if (!owner || (owner.type || 'screen') !== 'screen') return false;
        const editing = isPower ? this.isCustomPowerEditing(owner) : this.isCustomFlowEditing(owner);
        if (!editing) return false;
        const selection = isPower ? this.powerCustomSelection : this.customSelection;
        if (selection && selection.size > 0) {
            this._applyPatternFill(kind, pattern);
            return true;
        }
        const custom = isPower ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        if (!custom) return false;
        // The LAYER selection as stored - getSelectedLayers falls back to
        // currentLayer when it is empty, and an empty one means "nothing
        // selected" here.
        const ids = this.selectedLayerIds;
        if (!selection || !ids || ids.size === 0) return true;
        const keys = [];
        this.getSelectionScopeLayers(owner).forEach(member => {
            if (!member || !ids.has(member.id) || !Array.isArray(member.panels)) return;
            member.panels.forEach(panel => {
                if (!panel.hidden) keys.push(this.getScopedPanelKey(member.id, panel));
            });
        });
        if (keys.length === 0) return true;
        const before = new Set(selection);
        try {
            keys.forEach(k => selection.add(k));
            this._applyPatternFill(kind, pattern, { refill: true });
        } finally {
            selection.clear();
            before.forEach(k => selection.add(k));
        }
        if (isPower) {
            this.updateCustomPowerUI();
        } else {
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // The screens an AUTOMATIC pattern tile writes: the selected screens and
    // their groups (a group is one screen; the pattern is a group-wide
    // field), less every screen in custom mode for this side - a tile never
    // takes a screen out of custom mode, whichever screen is shown (the
    // owner's ruling, 2026-10-16; the audit found an automatic shown screen
    // carrying a custom one along with it) - and less every locked screen,
    // which stays unchanged and is named (`locked`, only those the pattern
    // would actually have changed).
    _patternTileTargets(kind, pattern) {
        const isPower = kind === 'power';
        const field = isPower ? 'powerFlowPattern' : 'flowPattern';
        const isCustom = isPower ? (l => this.isCustomPower(l)) : (l => this.isCustomFlow(l));
        const scope = [];
        const seen = new Set();
        const add = (l) => {
            if (!l || (l.type || 'screen') !== 'screen' || seen.has(l.id)) return;
            seen.add(l.id);
            scope.push(l);
        };
        (this.getSelectedLayers() || []).forEach(l => {
            add(l);
            if (typeof this.groupMembersOf === 'function') this.groupMembersOf(l).forEach(add);
        });
        const writable = scope.filter(l => !isCustom(l));
        return {
            change: writable.filter(l => !l.locked),
            locked: writable.filter(l => l.locked && (pattern === undefined || l[field] !== pattern)),
        };
    }

    applyPowerPatternToSelection(pattern) {
        this._applyPatternFill('power', pattern);
    }

    // The pattern buttons on a selection, both sides through ONE walk.
    //
    // Used to write the WHOLE selection into the one active port or circuit.
    // Now it walks the selection in pattern order and fills the active run
    // to its capacity (customRunCapacity - the sidebar's Panels/Circuit and
    // Panels/Port), then steps to the next number and keeps going until the
    // selection is consumed. HOW a run is filled follows the screen's mode
    // (the user's ruling, 2026-09-23: "if set to organized then whole rows;
    // if set to max capacity then pack full"): Organized takes whole rows
    // (or columns) only - a 14 x 6 block on serpentine at 14 a circuit is
    // circuits 1..6 at 14 apiece, every one read from the side the first
    // one started on; 18-wide rows at 24 a circuit are one row per circuit,
    // not 24-and-a-bit. Max Capacity / Maximize Power Use packs each run
    // full as one continuous snake, cut exactly at the cap even mid-row.
    // _chunkPicksByCapacity holds both walks.
    //
    // The numbers it fills are OVERWRITTEN - the active one always was, and
    // the ones it advances into are told on in the toast. A cabinet already
    // on a run OUTSIDE that set is a conflict and nothing is written, the
    // rule this has always had. One undo entry for the whole fill, and the
    // active index ends on the LAST number filled so the badge names what
    // was just drawn.
    //
    // `opts.refill` (a tile with a screen or group selected and no cabinets,
    // applyPatternTileInCustom): the runs whose cabinets lie inside the
    // selection - on the owner or on any member of its wall - are cleared
    // first and the fill starts at run 1, so nothing in the selection is a
    // conflict and a second tile re-lays the same cabinets. The clear and
    // the fill are ONE undo step, and a refused fill clears nothing.
    //
    // LOCKED SCREENS stay unchanged (the owner's ruling, 2026-10-16): a
    // locked owner refuses the fill outright (its runs are the ones being
    // written); a selected cabinet on a locked screen is left out and the
    // rest is filled; a run that touches a locked screen is never cleared or
    // overwritten - its number is stepped over and, on a refill, the
    // selected cabinets it carries keep it. Every locked screen met is named
    // in one error (_showLockedError).
    //
    // With one overridden run open for redrawing, the numbers the fill may
    // step into are the layer's overrides after the open one - the same list
    // Tab walks - and a selection that needs more than those is refused
    // rather than spilled onto runs the user never took over.
    //
    // Returns true when the fill was written.
    _applyPatternFill(kind, pattern, opts = {}) {
        const isPower = kind === 'power';
        if (!this.currentLayer || !window.canvasRenderer) return false;
        // The PORT / CIRCUIT stays on currentLayer even when the selection
        // spans peers - a port is one physical output on one processor. Only
        // the individual step records which screen the cable ran onto.
        const owner = this.currentLayer;
        if (isPower ? !this.isCustomPowerEditing(owner) : !this.isCustomFlowEditing(owner)) return false;
        const selection = isPower ? this.powerCustomSelection : this.customSelection;
        if (!selection || selection.size === 0) return false;
        if (owner.locked) {
            this._showLockedError([owner]);
            return false;
        }
        if (isPower) this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        const refill = !!(opts && opts.refill);
        const pathsKey = isPower ? 'powerCustomPaths' : 'customPortPaths';
        const idxKey = isPower ? 'powerCustomIndex' : 'customPortIndex';
        const noun = isPower ? 'circuit' : 'port';
        const keyOf = (layer, panel) => this.getScopedPanelKey(layer.id, panel);
        const toast = (msg, isError, ms) => {
            if (typeof this._toast === 'function') this._toast(msg, isError, ms);
        };
        // Every locked screen this fill met, named once at the end.
        const lockedMet = new Map();
        const meet = (layers) => (layers || []).forEach(l => lockedMet.set(l.id, l));
        const sayLocked = () => this._showLockedError([...lockedMet.values()]);

        const allPicks = this._selectedPathPanels(owner, selection);
        // The screens the user selected cabinets on - a run redone here that
        // also crossed onto ANOTHER screen is named when it lets go of that
        // screen's cabinets (_customFillUnwiredScreens).
        const selectedOn = new Set(allPicks.map(p => p.layer.id));
        let picks = allPicks.filter(pick => {
            if (!pick.layer.locked) return true;
            meet([pick.layer]);
            return false;
        });

        // The refill's clears, worked out before anything is written.
        const clears = [];          // [{ layer, num }]
        const clearSet = new Set(); // `${layerId}:${num}`
        if (refill && picks.length > 0) {
            const inScope = new Set(picks.map(p => keyOf(p.layer, p.panel)));
            const kept = new Set();
            this.getPathScopeLayers(owner).forEach(member => {
                const paths = member && member[pathsKey];
                if (!paths) return;
                Object.keys(paths).forEach(n => {
                    const steps = (paths[n] || []).filter(e => e && inScope.has(
                        this.getScopedPanelKey(this.getPathEntryLayerId(member, e), e)));
                    if (steps.length === 0) return;
                    const num = Number.isFinite(Number(n)) ? Number(n) : n;
                    const locked = this._runLockedLayers(member, kind, num);
                    if (locked.length) {
                        meet(locked);
                        steps.forEach(e => kept.add(
                            this.getScopedPanelKey(this.getPathEntryLayerId(member, e), e)));
                        return;
                    }
                    clears.push({ layer: member, num });
                    clearSet.add(`${member.id}:${num}`);
                });
            });
            if (kept.size > 0) picks = picks.filter(p => !kept.has(keyOf(p.layer, p.panel)));
        }
        if (picks.length === 0) {
            sayLocked();
            return false;
        }

        // The owner's run numbers the fill may not write: a run that touches
        // a locked screen and is not being cleared.
        const frozen = new Set();
        Object.keys(owner[pathsKey] || {}).forEach(n => {
            const num = Number.isFinite(Number(n)) ? Number(n) : n;
            if (clearSet.has(`${owner.id}:${num}`)) return;
            if (!(owner[pathsKey][n] || []).length) return;
            if (this._runLockedLayers(owner, kind, num).length) frozen.add(num);
        });

        const lattice = this._latticeGridForPicks(owner, picks);
        const lines = this._patternLines(pattern, lattice.grid, lattice.bucket);
        if (lines.length === 0) {
            sayLocked();
            return false;
        }

        // A frozen number is stepped over - at the start as between runs -
        // and its locked screens are named.
        const steppedOver = (nums) => nums.forEach(n => meet(this._runLockedLayers(owner, kind, n)));
        let startNum = refill ? 1 : (owner[idxKey] || 1);
        const startSkipped = [];
        while (startNum !== null && frozen.has(startNum)) {
            startSkipped.push(startNum);
            startNum = this._nextCustomRunNumber(owner, kind, startNum);
        }
        steppedOver(startSkipped);
        if (startNum === null) {
            sayLocked();
            return false;
        }

        const cut = this._chunkPicksByCapacity(owner, kind, startNum, lines, frozen);
        if (cut.skipped && cut.skipped.length) steppedOver(cut.skipped);
        if (cut.error) {
            toast(`Cannot apply: ${cut.error}`, true);
            sayLocked();
            return false;
        }
        const chunks = cut.chunks;
        // The picks in the order they were dealt, run after run.
        const ordered = chunks.flatMap(c => c.picks);
        if (ordered.length === 0) {
            sayLocked();
            return false;
        }
        const filled = new Set(chunks.map(c => c.num));

        // Reject the entire apply if any selected panel already belongs to a
        // run this fill will not overwrite (or, on a refill, clear). Prevents
        // silent double-mapping. The claim may live on a peer, which is why
        // the sample names both the cabinet's screen and the conflicting
        // run's.
        const conflicts = [];
        for (const pick of ordered) {
            const claim = isPower
                ? this._findPanelOwnerCircuit(owner, pick.panel, startNum, pick.layer)
                : this._findPanelOwnerPort(owner, pick.panel, startNum, pick.layer);
            if (!claim) continue;
            if (!claim.foreign && filled.has(claim.number)) continue;
            if (clearSet.has(`${claim.layerId}:${claim.number}`)) continue;
            conflicts.push({ pick, owner: claim });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `${this._describePathPanel(owner, c.pick.layer, c.pick.panel)}→${this._describePathConflict(c.owner, noun)}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ${noun}s, ${sample}${more}.`, true);
            sayLocked();
            return false;
        }

        // Worked out before anything is cleared or overwritten.
        const unwiredOn = this._customFillUnwiredScreens(owner, kind, clears, chunks, selectedOn);

        // The refill's clears land now, inside the same undo step as the
        // fill. A peer's run lets go of its override with it, the way Clear
        // does (_dropRunOverride).
        const touched = new Map();
        clears.forEach(c => {
            const paths = c.layer[pathsKey];
            if (paths) delete paths[c.num];
            if (c.layer.id !== owner.id) {
                this._dropRunOverride(c.layer, kind, c.num);
                touched.set(c.layer.id, c.layer);
            }
        });
        // Runs beyond the active one that held a drawing before this fill
        // replaced it - the toast says so. A run the refill cleared because
        // it lay inside the selection is not "replaced".
        const replaced = chunks.map(c => c.num).filter(n => (refill || n !== startNum)
            && !clearSet.has(`${owner.id}:${n}`)
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
        // currentLayer out of the layer selection entirely - and so is every
        // peer whose run the refill cleared.
        const persist = this._pathPersistLayers(owner);
        const have = new Set(persist.map(l => l && l.id));
        this.updateLayers(persist.concat([...touched.values()].filter(l => !have.has(l.id))));
        if (chunks.length > 1) {
            const cap = this.customRunCapacity(owner, kind);
            // Counted in the cabinets the selection is made of; a selection
            // of two cabinet sizes (data) or wattages (power) has no honest
            // count and names the cap the cut used instead, in pixels or
            // watts (see customRunFill). A data cut whose ports carry
            // different limits (Low Latency, the 5G narrow-port rule) names
            // the range it cut at.
            const sizing = this._customRunSizing(owner, kind, ordered.map(p => p.layer));
            const limits = isPower ? [] : chunks.map(c => this.customRunCapacity(
                owner, kind, c.picks.map(p => p.panel)).limit);
            const varies = limits.some(l => Math.round(l) !== Math.round(cap.limit));
            const each = varies
                ? `each cut at its own port capacity, ${Math.round(Math.min(...limits)).toLocaleString('en-US')}`
                    + ` to ${Math.round(Math.max(...limits)).toLocaleString('en-US')} px`
                : (sizing.mixed
                    ? `up to ${Math.round(cap.limit).toLocaleString('en-US')} ${isPower ? 'W' : 'px'} each`
                    : `up to ${sizing.count} panels each at ${cap.at}`);
            const lineNoun = String(pattern).endsWith('-v') ? 'column' : 'row';
            // The toast names the rule it used - the screen's mode decides
            // it (see _chunkPicksByCapacity).
            const rule = this._customRunPacksFull(owner, kind)
                ? 'packed full' : `whole ${lineNoun}s`;
            let msg = `Filled ${noun}s ${this._customRunLabel(owner, kind, chunks[0].num)} to `
                + `${this._customRunLabel(owner, kind, lastNum)} from the selection`
                + ` (${rule}, ${each})`;
            if (replaced.length > 0) {
                msg += `; replaced ${noun}${replaced.length === 1 ? '' : 's'} `
                    + replaced.map(n => this._customRunLabel(owner, kind, n)).join(', ');
            }
            toast(`${msg}.`, false);
        }
        if (unwiredOn.length > 0) {
            toast(this._customFillUnwiredMessage(kind, unwiredOn), true, 6000);
        }
        sayLocked();
        if (isPower ? this.powerCustomDebug : this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log(isPower ? '[CustomPower] Apply pattern' : '[CustomFlow] Apply pattern', {
                pattern,
                refill,
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
        return true;
    }

    // A PARTIAL GROUP FILL (the owner's ruling, 2026-10-16: "Warn and do
    // it"). A run is one cable, so a fill that redoes a run touching the
    // selection - a refill's clear, or an owner's run the fill overwrites -
    // redoes all of it, and a run that crossed onto a screen with nothing
    // selected lets go of that screen's cabinets. That stays; the screens it
    // happened to are named. Returns those screens, in wall order: every
    // screen holding a cabinet that is on a run being cleared or
    // overwritten, is not one the user selected cabinets on, and is not
    // wired again by the fill itself. Read BEFORE the clears land.
    _customFillUnwiredScreens(owner, kind, clears, chunks, selectedOn) {
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const rewired = new Set();
        (chunks || []).forEach(c => c.picks.forEach(p =>
            rewired.add(this.getScopedPanelKey(p.layer.id, p.panel))));
        const runs = (clears || []).map(c => ({ layer: c.layer, num: c.num }))
            .concat((chunks || []).map(c => ({ layer: owner, num: c.num })));
        const hit = new Set();
        runs.forEach(({ layer, num }) => {
            const path = (layer && layer[pathsKey] && layer[pathsKey][num]) || [];
            path.forEach(e => {
                if (!e) return;
                const id = this.getPathEntryLayerId(layer, e);
                if (selectedOn.has(id)) return;
                if (rewired.has(this.getScopedPanelKey(id, e))) return;
                hit.add(id);
            });
        });
        if (hit.size === 0) return [];
        return this.getPathScopeLayers(owner).filter(l => l && hit.has(l.id));
    }

    // "Runs that crossed into LOWER were redone — LOWER's cabinets on them
    // are now unwired." Power says circuits.
    _customFillUnwiredMessage(kind, layers) {
        const names = layers.map(l => l.name || `Screen ${l.id}`);
        const one = names.length === 1;
        const list = one ? names[0]
            : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
        const runs = kind === 'power' ? 'Circuits' : 'Runs';
        const whose = one ? `${list}'s cabinets` : `those screens' cabinets`;
        return `${runs} that crossed into ${list} were redone — ${whose} on them are now unwired.`;
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

    // Whether the pattern fill packs each run FULL on this screen (the
    // screen's pack-full mode) or by whole lines (its organized mode). Data
    // reads the Port Mapping buttons - `portMappingMode` 'max-capacity',
    // 'organized' when absent - and power reads the Maximize Power Use box
    // (`powerMaximize`); Organized is the default on both sides. Read from
    // the OWNER, the layer the fill writes to, the same one customRunCapacity
    // is read for.
    _customRunPacksFull(owner, kind) {
        if (!owner) return false;
        if (kind === 'power') return !!owner.powerMaximize;
        return ((owner.portMappingMode) || 'organized') === 'max-capacity';
    }

    // Cut the pattern's lines into runs at capacity: [{num, picks, load}]
    // starting at `startNum`. No cap known means one run with everything.
    //
    // TWO WALKS, chosen by the screen's mode (_customRunPacksFull). The
    // user's ruling, 2026-09-23: "if set to organized then whole rows; if
    // set to max capacity then pack full."
    //
    // ORGANIZED (the default): THE WALK is by whole LINES - rows for a
    // horizontal pattern, columns for a vertical one - the same unit the
    // automatic Organized walk packs (calculatePowerAssignments). A run
    // takes a line only when the WHOLE line still fits; a line that does
    // not fit opens the next run. The user, 2026-09-22, with 18-wide rows
    // at 24 a circuit: "it is supposed to start at the beginning and then
    // fill a max, not jump down a row unless it fits a whole other
    // row/column." Before this the fill poured cabinets in and cut wherever
    // the cap fell, so circuit 1 was row 0 plus the far end of row 1 read
    // backwards, and circuit 2 the rest of row 1 plus most of row 2 - runs
    // that started nowhere a cable comes from.
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
    // PACK FULL (Max Capacity on data, Maximize Power Use on power): the
    // selection is ONE continuous snake - the shape getPatternOrderForGrid
    // walks, the first line in the pattern's direction, every second line
    // back - and each run takes exactly as much of it as its cap carries,
    // cut wherever the cap falls, mid-line included. The next run carries
    // the snake on from that cut; nothing restarts from the start side.
    // That is the walk the automatic Max Capacity / Maximize engines make,
    // and what "pack full" means: 12-wide rows at 8 a port are ports of 8,
    // 8, 8 - row 0 cols 0-7; cols 8-11 then row 1 cols 11-8; row 1 cols
    // 7-0 - not 8, 4, 8, 4.
    //
    // THE LIMIT is the run's own (customRunCapacity with the run's cabinets):
    // for power the circuit's watts, the same for every run; for data the
    // port figure less the Low Latency derate and the 5G narrow-port penalty
    // for the cabinets the run would hold - so a cabinet is weighed against
    // the limit the run has WITH it, exactly as the automatic walk does.
    //
    // `skip`: run numbers the fill may not write (a run touching a locked
    // screen); a new run steps over them, and `skipped` lists the ones it
    // did.
    //
    // `error` instead when a single cabinet is over the cap on its own or
    // the override list runs out - nothing is written in either case.
    _chunkPicksByCapacity(owner, kind, startNum, lines, skip = null) {
        const cap = this.customRunCapacity(owner, kind);
        const eps = CUSTOM_RUN_EPS;
        const noun = kind === 'power' ? 'circuit' : 'port';
        const fmt = (v) => (kind === 'power'
            ? `${Math.round(v).toLocaleString('en-US')} W` : `${Math.round(v).toLocaleString('en-US')} px`);
        const perRun = cap.known && kind !== 'power';
        const limitFor = (picks) => {
            if (!cap.known) return Infinity;
            if (!perRun) return cap.limit;
            return this.customRunCapacity(owner, kind, picks.map(p => p.panel)).limit;
        };
        // A run's load is weighed whole (customRunLoad): on Armor a cabinet
        // can cost a row of the rectangle, so loads do not simply add up.
        const loadFor = (picks) => this.customRunLoad(owner, kind, picks);
        const loadOf = (pick) => loadFor([pick]);
        // The cap in words for the "taken-over runs" refusal: the cabinet
        // count for one kind of cabinet, pixels or watts for a selection of
        // two (the readout's own rule - customRunFill).
        const describe = () => {
            const layers = lines.flatMap(line => line.map(p => p.layer));
            return this._customRunSizing(owner, kind, layers, cap).describe;
        };
        const chunks = [];
        const skipped = [];
        let cur = { num: startNum, picks: [], load: 0 };
        let lineInRun = 0;
        // Close the run in hand and open the next number - or say why not.
        const closeRun = () => {
            chunks.push(cur);
            let next = this._nextCustomRunNumber(owner, kind, cur.num);
            while (next !== null && skip && skip.has(next)) {
                skipped.push(next);
                next = this._nextCustomRunNumber(owner, kind, next);
            }
            if (next === null) {
                const taken = this.getOverrideNums(owner, kind)
                    .map(n => this._customRunLabel(owner, kind, n)).join(', ');
                return `the selection does not fit on the taken-over `
                    + `${noun}s (${taken}) - ${describe()}. Take over another `
                    + `run or select a narrower block.`;
            }
            cur = { num: next, picks: [], load: 0 };
            lineInRun = 0;
            return null;
        };
        const lay = (seq) => {
            cur.picks.push(...seq);
            cur.load = loadFor(cur.picks);
        };
        const tooBig = (pick) => {
            const load = loadOf(pick);
            const solo = limitFor([pick]);
            if (cap.known && load > solo + eps) {
                return `panel ${this._describePathPanel(owner, pick.layer, pick.panel)} `
                    + `is ${fmt(load)} and a ${noun} carries ${fmt(solo)}.`;
            }
            return null;
        };
        if (this._customRunPacksFull(owner, kind)) {
            // One continuous snake, cut at the cap wherever it falls.
            const snake = [];
            lines.forEach((line, i) => {
                snake.push(...(i % 2 === 1 ? line.slice().reverse() : line));
            });
            for (const pick of snake) {
                const big = tooBig(pick);
                if (big) return { error: big, skipped };
                const next = cur.picks.concat([pick]);
                if (cur.picks.length > 0 && loadFor(next) > limitFor(next) + eps) {
                    const why = closeRun();
                    if (why) return { error: why, skipped };
                }
                lay([pick]);
            }
            chunks.push(cur);
            return { chunks, skipped };
        }
        for (const line of lines) {
            // An empty line (hidden cabinets, a group's gap) still counts
            // toward the snake's alternation - the rule this has always had.
            if (line.length === 0) {
                lineInRun += 1;
                continue;
            }
            for (const pick of line) {
                const big = tooBig(pick);
                if (big) return { error: big, skipped };
            }
            if (loadFor(line) <= limitFor(line) + eps) {
                // A whole line: onto the run in hand if it fits, else it
                // opens the next run from the start side.
                const next = cur.picks.concat(line);
                if (cur.picks.length > 0 && loadFor(next) > limitFor(next) + eps) {
                    const why = closeRun();
                    if (why) return { error: why, skipped };
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
                if (why) return { error: why, skipped };
            }
            let cells = line;
            while (cells.length > 0) {
                let took = 0;
                for (const pick of cells) {
                    const next = cur.picks.concat([pick]);
                    if (cur.picks.length > 0 && loadFor(next) > limitFor(next) + eps) break;
                    lay([pick]);
                    took += 1;
                }
                cells = cells.slice(took);
                if (cells.length > 0) {
                    const why = closeRun();
                    if (why) return { error: why, skipped };
                }
            }
            // The remainder is the first line on its run, read in the
            // pattern's direction; a line that follows it snakes back.
            lineInRun = 1;
        }
        chunks.push(cur);
        return { chunks, skipped };
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
