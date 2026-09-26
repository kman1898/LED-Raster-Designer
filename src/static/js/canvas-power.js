// canvas.js mixin: The power pass: circuit colours and keys, the run arrows, soca and gang (Nfer) brackets, cable tags, the power error overlay.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    getPowerCircuitPalette() {
        return ['#FF0000', '#FF8C00', '#FFE600', '#00CC00', '#1E4CFF', '#8A2BE2'];
    },

    getPowerCircuitColor(layer, circuitNum) {
        if (window.app && typeof window.app.getPowerCircuitColor === 'function') {
            return window.app.getPowerCircuitColor(layer, circuitNum);
        }
        const palette = this.getPowerCircuitPalette();
        return palette[(Math.max(1, circuitNum) - 1) % palette.length];
    },

    getPowerCircuitLetter(circuitNum) {
        let n = Math.max(1, parseInt(circuitNum, 10) || 1);
        let out = '';
        while (n > 0) {
            n -= 1;
            out = String.fromCharCode(65 + (n % 26)) + out;
            n = Math.floor(n / 26);
        }
        return out;
    },

    getPowerPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    },

    // _powerCircuitOwners rows as LAYER IDS - one row per circuit, null for a
    // circuit that never leaves `layer`, and null overall when nothing crosses.
    //
    // IDS, NOT LAYER OBJECTS. These rows are cached on the layer, and the
    // layer lives inside app.project - a row holding the layer itself (which
    // every stay-home cabinet of a grouped plan does) makes the project
    // CIRCULAR, and the first JSON.stringify of it throws instead of saving.
    // That is not a corner case: saveState deep-copies the project on every
    // edit, updateLayers PUTs each layer, and the group commit PUTs the whole
    // project - so one power render of a grouped wall silently broke undo and
    // persistence everywhere. The automatic DATA crossing already ships plain
    // layerIds on its items (_autoCrossMemberHits) for exactly this reason.
    //
    // Accepts rows of layers or of ids, so both the custom builder (which can
    // hand ids straight through) and calculatePowerAssignments' object rows
    // funnel through one conversion.
    _powerOwnerIdRows(layer, ownerRows) {
        if (!Array.isArray(ownerRows)) return null;
        let crossesAnywhere = false;
        const rows = ownerRows.map(row => {
            if (!Array.isArray(row)) return null;
            const ids = row.map(o => (o == null) ? null
                : (o.id !== undefined ? o.id : o));
            // An all-home row reads as "does not cross", the same shape the
            // hand-drawn side has always used, so the crossing tests downstream
            // stay a plain truthiness check.
            if (ids.every(id => id == null || id === layer.id)) return null;
            crossesAnywhere = true;
            return ids;
        });
        return crossesAnywhere ? rows : null;
    },

    preparePowerLayerRenderData(layer) {
        if (!window.app) return;
        const isCustom = (layer.powerFlowPattern || 'tl-h') === 'custom';
        let error = null;
        let circuits = [];
        let circuitNumKeys = null;

        // v0.11.0: which LAYER each cabinet of each circuit came from, parallel
        // to `circuits`. Every entry is this layer for an automatic map and for
        // any custom circuit that stays home; only a circuit reaching into a
        // group peer differs, and only that case needs the scoped keys below.
        let circuitOwners = null;

        // Per-circuit branch panel counts (splitter circuits only) - null
        // when nothing on this screen shares a circuit.
        let circuitRuns = null;

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            const entries = circuitNums.map(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                if (!this._pathCrossesMembers(layer, path)) {
                    return { num: circuitNum, owners: null,   // all this layer's own cabinets
                        panels: path
                            .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                            .filter(p => p && !p.hidden) };
                }
                // Ids, not the layers themselves - see _powerOwnerIdRows.
                const hits = this._resolvePathPanels(layer, path);
                return { num: circuitNum, owners: hits.map(h => h.layer.id),
                    panels: hits.map(h => h.panel) };
            });
            // Manual splitter merges collapse drawn circuits into ONE shared
            // circuit keyed (and labelled) by the first member's number, so
            // every tile of the group tints and reads as the one circuit.
            const groups = (window.app && typeof window.app.appliedSplitterGroups === 'function')
                ? window.app.appliedSplitterGroups(layer, circuitNums).merge : [];
            let merged = entries;
            if (groups.length) {
                const inG = new Map();
                groups.forEach(g => g.forEach(n => inG.set(n, g)));
                const byNum = new Map(entries.map(e => [e.num, e]));
                const done = new Set();
                merged = [];
                circuitRuns = [];
                for (const e of entries) {
                    if (done.has(e.num)) continue;
                    const g = inG.get(e.num);
                    if (!g) {
                        merged.push(e);
                        circuitRuns.push([e.panels.length]);
                        continue;
                    }
                    const ms = g.filter(n => byNum.has(n)).map(n => byNum.get(n));
                    ms.forEach(m => done.add(m.num));
                    merged.push({
                        num: ms[0].num,
                        owners: ms.some(m => m.owners)
                            ? ms.flatMap(m => m.owners || m.panels.map(() => layer.id))
                            : null,
                        panels: ms.flatMap(m => m.panels),
                    });
                    circuitRuns.push(ms.map(m => m.panels.length));
                }
            }
            circuitNumKeys = merged.map(e => e.num);
            circuitOwners = merged.map(e => e.owners);
            circuits = merged.map(e => e.panels);
        } else {
            const assignments = window.app.calculatePowerAssignments(layer);
            error = assignments.error;
            circuits = assignments.circuits || [];
            circuitRuns = assignments.runs || null;
            // Per-run overrides: the engine numbers the rows itself (auto rows
            // skip the overridden numbers, override rows keep theirs). Null on
            // every screen without overrides, so idx + 1 stays the number.
            circuitNumKeys = assignments.nums || null;
            // v0.12: an automatic circuit that crosses into a group peer names
            // the screen each cabinet is on. Null for every non-crossing plan,
            // which keeps the unscoped `${row},${col}` map below - and therefore
            // the colour-coded tinting of every ungrouped screen - exactly as it
            // was. Without it a crossing circuit tints the OWNER's R3C4 instead
            // of the peer's, because that key cannot tell the two apart.
            circuitOwners = this._powerOwnerIdRows(layer, assignments.layers);
        }

        layer._powerError = error;
        layer._powerCircuits = circuits;
        layer._powerCircuitRuns = circuitRuns;
        layer._powerCircuitNumKeys = circuitNumKeys;
        layer._powerCircuitOwners = circuitOwners;

        const panelCircuitMap = new Map();
        const panelIndexMap = new Map();
        // v0.11.0: the same two maps keyed by `${layerId}:${row},${col}` so a
        // circuit that reaches into a group peer can still tint the cabinets it
        // claimed over there. It has to be a SECOND map rather than a change of
        // key: the unscoped one is read by renderPower for this layer's own
        // cabinets and cannot tell member A's R0C0 from member B's, so filing a
        // peer's cabinet in it would paint the owner's own R0C0 instead.
        const panelCircuitScopedMap = new Map();
        const panelIndexScopedMap = new Map();
        if (!error) {
            circuits.forEach((circuitPanels, idx) => {
                const circuitNum = circuitNumKeys ? circuitNumKeys[idx] : idx + 1;
                const owners = circuitOwners ? circuitOwners[idx] : null;
                (circuitPanels || []).forEach((panel, panelIdx) => {
                    const ownerId = (owners && owners[panelIdx] != null)
                        ? owners[panelIdx] : layer.id;
                    if (ownerId === layer.id) {
                        const key = this.getPowerPanelKey(panel);
                        panelCircuitMap.set(key, circuitNum);
                        panelIndexMap.set(key, panelIdx + 1);
                    }
                    if (window.app && typeof window.app.getScopedPanelKey === 'function') {
                        const scopedKey = window.app.getScopedPanelKey(ownerId, panel);
                        panelCircuitScopedMap.set(scopedKey, circuitNum);
                        panelIndexScopedMap.set(scopedKey, panelIdx + 1);
                    }
                });
            });
        }
        layer._powerPanelCircuitMap = panelCircuitMap;
        layer._powerPanelIndexMap = panelIndexMap;
        layer._powerPanelCircuitScopedMap = panelCircuitScopedMap;
        layer._powerPanelIndexScopedMap = panelIndexScopedMap;
        // Which frame these maps belong to. Kept off the layer object (a
        // WeakMap on the renderer) so it is not one more transient key the
        // preset, file-load and history code has to remember to strip.
        if (!this._powerPrepFrame) this._powerPrepFrame = new WeakMap();
        this._powerPrepFrame.set(layer, this._renderSeq || 0);
    },

    renderPowerArrows(layer) {
        const pattern = layer.powerFlowPattern || 'tl-h';
        const baseLineWidth = layer.powerLineWidth || 8;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.powerLabelSize || 14;
        // The printer page: white discs with black text and a black rim,
        // black runs and arrows (dashed per circuit in drawDaisyLines).
        const printer = this.printerMode;
        const powerLabelBgColor = printer ? '#ffffff' : (layer.powerLabelBgColor || '#D95000');
        const powerLabelTextColor = printer ? PRINTER_INK : (layer.powerLabelTextColor || '#000000');
        const lineColor = this._ink(layer.powerLineColor || '#FF0000');
        const arrowColor = this._ink(layer.powerArrowColor || '#0042AA');
        const useRandomColors = (layer.powerRandomColors || false) && !printer;
        const useColorCodedView = !!layer.powerColorCodedView;
        const isCustom = pattern === 'custom';
        if (isCustom) {
            layer._powerError = null;
        }
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;

        this.ctx.save();
        this._clipToActiveRaster();
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];

        // v0.8.7.4: layer bounds in panel-local coords, used to shift
        // labels inward when they'd overflow the screen edge.
        // v0.11.0: the cross-member overlay pass keeps its labels inside the
        // whole wall instead, in the overlay's frame - see renderDataFlowArrows.
        const layerBounds = this._crossMemberPass
            ? this._crossMemberBounds(layer)
            : this.getLayerBounds(layer);
        const layerLeft = layerBounds.x;
        const layerTop = layerBounds.y;
        const layerRight = layerBounds.x + layerBounds.width;
        const layerBottom = layerBounds.y + layerBounds.height;

        // v0.8.7.4: render at the user's labelSize directly (no
        // fit-to-panel cap, that was overriding the size slider).
        // Circle grows to fit text width so labels never get clipped.
        // If the label would overflow the screen edge, shift the
        // CENTER inward so the label stays fully inside the screen
        // bounds. Long labels overflow into neighboring panels but
        // never beyond the screen.
        // v0.12.0: placement split from drawing so the splitter fan-out can
        // place ONE bubble centered over its run heads (see
        // drawCircuitBranches); the single-run path is unchanged.
        // A spaced label ("SR A1") stacks at the spaces instead of
        // inflating the circle - see _layoutCircleLabel. The layout (lines
        // + radius) travels together so the bubble and its text agree.
        const labelLayout = (label) => {
            this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
            const padding = Math.max(6, labelSize * 0.25);
            return this._layoutCircleLabel(
                label, labelSize, Math.max(labelSize * 0.7, lineWidth * 1.4), padding);
        };
        const clampLabelCenter = (px, py, circleRadius) => {
            // Shift to keep circle fully within screen bounds.
            if (px - circleRadius < layerLeft) px = layerLeft + circleRadius;
            if (px + circleRadius > layerRight) px = layerRight - circleRadius;
            if (py - circleRadius < layerTop) py = layerTop + circleRadius;
            if (py + circleRadius > layerBottom) py = layerBottom - circleRadius;
            return { px: this.snap(px), py: this.snap(py) };
        };
        // The cable tags are drawn AFTER every circuit's label is placed,
        // so a tag can be kept off the other labels of the screen - "the
        // cables added to the power or data sometimes go under labels and
        // overlap" (2026-09-09: a "10' True1" beside S1-1-1 lay across
        // S1-1-2, the circuits a panel apart). drawLabelBubble collects
        // the discs and the tags it wants; drawCableTags places and paints
        // them (placeCableTag: the run's side first, then beside its label,
        // the other side, below, above - the first that covers no other
        // disc and stays inside the screen). THE RUN'S SIDE (owner's
        // ruling, 2026-09-25): a run that leaves its disc going DOWN,
        // RIGHT or LEFT - or a one-cabinet circuit - hangs its tags ABOVE
        // the disc; one going UP hangs them UNDER it (_tagRunSide). The
        // data map's port tags go by the same rule.
        // THE 2FER / 3FER PILL RIDES WITH THE CABLE TAG (2026-09-15). It
        // used to float on the gang bracket under the runs' feet, and on a
        // wall of row runs that line is a row seam nowhere near the runs'
        // heads: "when two fers or similar are enabled on the screen to be
        // seen, the drawing isn't obvious what it is connected to". Now it
        // hangs off the shared circuit's own label disc, a second row of
        // the cable tag's stack - "it should just connect to 10' True1 for
        // example. just put it right above that or under it" - so a head
        // reads "S1-1 · 10' True1 · 2fer". With the cable tags off the pill
        // takes the tag's place beside the disc; with the Nfer tags off
        // there is no pill (OVER alone excepted, _nferTagText). Every disc
        // a shared circuit gets carries it - the one label at the fan-out,
        // or a disc per member where a member run draws its own.
        const labelDiscs = [];
        const pendingTags = [];
        // LONG JUMPS (2026-09-25): the data map's rule on the power side -
        // with the cable tags on, a link between two cabinets that do not
        // touch wears its jumper's length at the middle of its segment; a
        // short link wears nothing (app-jumpers jumperLongLinkMap, keyed by
        // the real cabinets, a cross-member shim through its srcPanel).
        const jumpMap = (layer.showPowerCableTags === true && window.app
                && typeof window.app.jumperLongLinkMap === 'function')
            ? window.app.jumperLongLinkMap(layer, 'power') : null;
        const pendingJumps = [];
        const collectJumps = (panels) => {
            if (!jumpMap || !jumpMap.size) return;
            for (let i = 0; i < panels.length - 1; i++) {
                const a = panels[i], b = panels[i + 1];
                const inner = jumpMap.get(a.srcPanel || a);
                const ft = inner ? inner.get(b.srcPanel || b) : null;
                if (ft == null) continue;
                pendingJumps.push({
                    text: `${ft}'`,
                    x: (a.x + a.width / 2 + b.x + b.width / 2) / 2,
                    y: (a.y + a.height / 2 + b.y + b.height / 2) / 2,
                });
            }
        };
        // The gang a disc's circuit number names. A shared circuit's own
        // number is its key on every path; its run ids are keys only on a
        // custom-routed screen, where they ARE drawn circuit numbers (a
        // merged member keeps its number and, crossing into a peer, draws
        // its own disc). On an auto screen a run id is a RUN ordinal in a
        // different space - the 2fer of runs [1, 2] is circuit 1, and run
        // 2 is nobody's circuit number - so keying those would hang a
        // "2fer" off the plain circuit 2 next door.
        const gangByRun = new Map();
        const customIds = typeof window.app.isCustomPower === 'function'
            && window.app.isCustomPower(layer);
        for (const g of this._nferGangs(layer)) {
            gangByRun.set(g.num, g);
            if (customIds) g.runIds.forEach(id => gangByRun.set(id, g));
        }
        const drawCableTags = () => {
            // The pills are placed in the UPRIGHT frame (_tagFrame): on a
            // rotated screen "right of the disc" means right on the page,
            // not right along the rotated wall, and the stack under a tag
            // is a stack on the page. Unrotated, the frame is the layer's
            // own and every number below is what it always was.
            const F = this._tagFrame();
            const corners = [[layerLeft, layerTop], [layerRight, layerTop],
                             [layerLeft, layerBottom], [layerRight, layerBottom]]
                .map(([x, y]) => F.toU(x, y));
            const bounds = { left: Math.min(...corners.map(c => c.x)),
                             top: Math.min(...corners.map(c => c.y)),
                             right: Math.max(...corners.map(c => c.x)),
                             bottom: Math.max(...corners.map(c => c.y)) };
            const discsU = labelDiscs.map(d => Object.assign(F.toU(d.x, d.y), { r: d.r }));
            const ownU = (d) => discsU[labelDiscs.indexOf(d)];
            const paint = (text, at, colors, kind) => {
                const pivot = F.fromU(at.x, at.y);
                this.drawCableTag(text, at.x, at.y, labelSize, colors,
                                  Object.assign({ pivot }, at.opts), kind);
            };
            // The pills already down: a tag is placed clear of them as
            // well as of the discs - see placeCableTag.
            const taken = [];
            // The jump tags first, centred on their segment's midpoint in
            // the upright frame (a 'right' hang whose gap is taken back off
            // x); the label tags then move off them.
            for (const j of pendingJumps) {
                const u = F.toU(j.x, j.y);
                const w = this.cableTagLayout(j.text, labelSize).width;
                const at = { x: u.x - labelSize * 0.25 - w / 2, y: u.y, opts: { side: 'right' } };
                taken.push(this.cableTagRect(j.text, at.x, at.y, labelSize, at.opts));
                paint(j.text, at, undefined, 'jump');
            }
            pendingJumps.length = 0;
            for (const t of pendingTags) {
                const own = ownU(t.disc);
                // the side the owner ruled for a head (_tagRunSide)
                const prefer = this._tagRunSide(t.step, F);
                const nfer = t.gang ? this._nferTagText(layer, t.gang) : null;
                let base = null;
                if (t.text) {
                    // A pill that will stack under this one is placed with
                    // it: the column is judged whole, and hung ABOVE the
                    // disc the tag stands a pill higher so the 3fer lands
                    // between it and the disc.
                    const stack = nfer ? this._stackReserve(nfer, labelSize) : null;
                    const at = this.placeCableTag(t.text, own.x, own.y, own.r, labelSize,
                                                  bounds, discsU, own, taken, { prefer, stack });
                    taken.push(at.rect);
                    paint(t.text, at, undefined, undefined);
                    base = at.rect;
                }
                if (!nfer) continue;
                const colors = this._nferTagColors(t.gang);
                const at = base
                    ? this.placeStackedTag(nfer, base, labelSize, bounds, discsU, own, taken)
                    : this.placeCableTag(nfer, own.x, own.y, own.r, labelSize,
                                         bounds, discsU, own, taken, { prefer });
                taken.push(at.rect);
                paint(nfer, at, colors, 'gang');
            }
            pendingTags.length = 0;
        };
        const drawLabelBubble = (layout, px, py, circuitNum, step) => {
            this.ctx.fillStyle = powerLabelBgColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, layout.radius, 0, Math.PI * 2);
            this.ctx.fill();
            if (printer) {
                this.ctx.save();
                this.ctx.setLineDash([]);
                this.ctx.lineWidth = Math.max(1, labelSize * 0.1);
                this.ctx.strokeStyle = PRINTER_INK;
                this.ctx.stroke();
                this.ctx.restore();
            }

            this.ctx.fillStyle = powerLabelTextColor;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillWrappedLabel(layout.lines, px, py, labelSize);
            const disc = { x: px, y: py, r: layout.radius };
            labelDiscs.push(disc);
            // The circuit's cable, as a small gold tag beside the label -
            // option D of cables-mock.html, "an option when doing the docs
            // per screen" (2026-09-06): per screen, default OFF, and the
            // same test in exportMode so the PDF is what was asked for.
            // Placed and drawn by drawCableTags once every label is down:
            // inside the screen, right of the label when that fits, else
            // left of it, and off any other label's disc. A wrapped tag is
            // taller than its label circle, so it carries the screen's top
            // and bottom too and shifts inside them the way the circle's
            // centre was shifted.
            let cableText = null;
            if (layer.showPowerCableTags === true && circuitNum != null
                    && window.app
                    && typeof window.app.powerCircuitCable === 'function') {
                const cable = window.app.powerCircuitCable(layer, circuitNum);
                if (cable) cableText = cable.text;
            }
            const gang = circuitNum != null ? gangByRun.get(circuitNum) || null : null;
            if (cableText || gang) pendingTags.push({ text: cableText, disc, gang, step });
        };
        // The run's first step - its first cabinet to its second, centre
        // to centre, in the frame the daisy is drawn in (a custom path's
        // own order; drawCableTags turns it upright). Null for a circuit
        // of one cabinet. The tags' side is read off it (2026-09-25).
        const firstStep = (a, b) => (a && b)
            ? { dx: (b.x + b.width / 2) - (a.x + a.width / 2),
                dy: (b.y + b.height / 2) - (a.y + a.height / 2) }
            : null;
        const drawCircuitLabel = (panelStart, panelNext, circuitNum) => {
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const layout = labelLayout(label);
            const { px, py } = clampLabelCenter(
                panelStart.x + panelStart.width / 2,
                panelStart.y + panelStart.height / 2, layout.radius);
            drawLabelBubble(layout, px, py, circuitNum, firstStep(panelStart, panelNext));
        };

        if (useColorCodedView) {
            if (!Array.isArray(layer._powerCircuits) && window.app) {
                const assignments = window.app.calculatePowerAssignments(layer);
                layer._powerError = assignments.error;
                layer._powerCircuits = assignments.circuits || [];
                layer._powerCircuitNumKeys = assignments.nums || null;
            }
            if (layer._powerError || !Array.isArray(layer._powerCircuits)) {
                this.ctx.restore();
                return;
            }
            const colorViewKeys = layer._powerCircuitNumKeys;
            // v0.11.0: `circuits` can now hold a peer's cabinets, and the label
            // is parked on the circuit's FIRST cabinet - which may be one of
            // them. Its raw x/y mean nothing inside this layer's transform, so
            // a crossing circuit's label is deferred to the overlay pass with
            // the lines, and there it is rebuilt from overlay-frame shims.
            const colorViewOwners = layer._powerCircuitOwners;
            layer._powerCircuits.forEach((circuitPanels, idx) => {
                if (!circuitPanels || circuitPanels.length === 0) return;
                const circuitNum = colorViewKeys ? colorViewKeys[idx] : idx + 1;
                const path = (isCustom && layer.powerCustomPaths)
                    ? (layer.powerCustomPaths[circuitNum] || []) : [];
                const crosses = !!(colorViewOwners && colorViewOwners[idx]);
                if (this._crossMemberPass) {
                    if (!crosses) return;
                    const shims = this._crossMemberDrawPanels(layer, path);
                    if (shims.length === 0) return;
                    drawCircuitLabel(shims[0], shims[1], circuitNum);
                    return;
                }
                if (crosses) {
                    this._deferCrossMemberPath(layer, path);
                    return;
                }
                // dock drag: colour-coded view draws no daisy, so the
                // underlay is the whole of the run highlight here
                this._dockRunUnderlay(circuitPanels, layer, circuitNum);
                drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
            });
            drawCableTags();
            this.ctx.restore();
            return;
        }

        // The daisy polyline + direction arrows for ONE run of panels -
        // shared by the whole-circuit path and the per-branch splitter path.
        const drawDaisyLines = (circuitPanels, currentLineColor, circuitNum) => {
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;
            // Printer page: this circuit's own dash, butt-capped so a fine
            // pattern stays a pattern instead of fusing into a solid line.
            const dash = this._runDash(circuitNum, lineWidth);
            this.ctx.save();
            this.ctx.setLineDash(dash);
            if (dash.length) this.ctx.lineCap = 'butt';

            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                this.ctx.beginPath();
                this.ctx.moveTo(cx, cy);
                this.ctx.lineTo(nx, ny);
                this.ctx.stroke();
            }
            this.ctx.restore();

            this.ctx.fillStyle = arrowColor;
            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                const midX = this.snap((cx + nx) / 2);
                const midY = this.snap((cy + ny) / 2);
                const angle = Math.atan2(ny - cy, nx - cx);
                const arrowLen = lineWidth * 3;
                this.ctx.beginPath();
                this.ctx.moveTo(
                    midX + arrowLen * Math.cos(angle),
                    midY + arrowLen * Math.sin(angle)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle - Math.PI / 5),
                    midY - arrowLen * Math.sin(angle - Math.PI / 5)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle + Math.PI / 5),
                    midY - arrowLen * Math.sin(angle + Math.PI / 5)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }
            collectJumps(circuitPanels);
        };

        const drawCircuit = (circuitPanels, circuitNum) => {
            if (circuitPanels.length === 0) return;
            // dock drag: the circuit under the cursor lights up first
            this._dockRunUnderlay(circuitPanels, layer, circuitNum);
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            drawDaisyLines(circuitPanels, currentLineColor, circuitNum);
            drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
        };

        // A splitter circuit: each branch is its own short daisy, and the
        // ONE circuit label sits at the FAN-OUT - centered across the span
        // of the run-head panels (between the two heads of a 2fer, over the
        // middle of a 3fer) - with the dashed stubs radiating from the
        // bubble to every run head. v0.12.0: it used to sit on run 1's first
        // panel with the stubs crossing to the other heads, which read as
        // clutter on a real wall; a single-branch circuit keeps the plain
        // first-panel label.
        const drawCircuitBranches = (branches, circuitNum) => {
            const live = (branches || []).filter(b => b && b.length > 0);
            if (!live.length) return;
            // dock drag: every branch of the circuit lights together
            live.forEach(b => this._dockRunUnderlay(b, layer, circuitNum));
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            live.forEach(b => drawDaisyLines(b, currentLineColor, circuitNum));
            if (live.length === 1) {
                drawCircuitLabel(live[0][0], live[0][1], circuitNum);
                return;
            }
            const heads = live.map(b => b[0]);
            const hx = heads.map(h => h.x + h.width / 2);
            const hy = heads.map(h => h.y + h.height / 2);
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const layout = labelLayout(label);
            const { px, py } = clampLabelCenter(
                (Math.min(...hx) + Math.max(...hx)) / 2,
                (Math.min(...hy) + Math.max(...hy)) / 2, layout.radius);
            this.ctx.save();
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = Math.max(1, lineWidth * 0.6);
            this.ctx.setLineDash([lineWidth * 1.5, lineWidth]);
            for (const h of heads) {
                this.ctx.beginPath();
                this.ctx.moveTo(px, py);
                this.ctx.lineTo(this.snap(h.x + h.width / 2), this.snap(h.y + h.height / 2));
                this.ctx.stroke();
            }
            this.ctx.restore();
            // The fan-out disc names every branch; its tags go by the
            // first branch that has a step (the runs of one splitter leave
            // their heads the same way on an organised wall).
            const lead = live.find(b => b.length > 1);
            drawLabelBubble(layout, px, py, circuitNum, lead ? firstStep(lead[0], lead[1]) : null);
        };

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            // Manual splitter merges: the group's member paths draw as the
            // BRANCHES of one shared circuit - one label (the first member's
            // number), dashed stubs to the other runs. A group touching a
            // cross-member path keeps the per-path drawing (the overlay pass
            // machinery owns those), so nothing is wired twice.
            const groups = (window.app && typeof window.app.appliedSplitterGroups === 'function')
                ? window.app.appliedSplitterGroups(layer, circuitNums).merge : [];
            const inG = new Map();
            groups.forEach(g => g.forEach(n => inG.set(n, g)));
            const homePanelsOf = (circuitNum) => (layer.powerCustomPaths[circuitNum] || [])
                .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                .filter(p => p && !p.hidden);
            const done = new Set();
            circuitNums.forEach(circuitNum => {
                if (done.has(circuitNum)) return;
                const g = inG.get(circuitNum);
                if (g && !this._crossMemberPass) {
                    const members = g.filter(n => circuitNums.includes(n));
                    const crosses = members.some(n =>
                        this._pathCrossesMembers(layer, layer.powerCustomPaths[n] || []));
                    if (!crosses) {
                        members.forEach(n => done.add(n));
                        drawCircuitBranches(members.map(homePanelsOf), members[0]);
                        return;
                    }
                }
                const path = layer.powerCustomPaths[circuitNum] || [];
                // v0.11.0: same split as the data-flow custom branch, and it has
                // to stay in step with preparePowerLayerRenderData above - the
                // two read the same paths and a divergence would show up as a
                // circuit that is tinted but not wired, or wired twice.
                if (this._deferCrossMemberPath(layer, path)) return;
                if (this._crossMemberPass) {
                    drawCircuit(this._crossMemberDrawPanels(layer, path), circuitNum);
                    return;
                }
                drawCircuit(homePanelsOf(circuitNum), circuitNum);
            });
            drawCableTags();
            this.ctx.restore();
            return;
        }

        // v0.12: an automatic circuit CAN leave its layer - same change as the
        // one in renderDataFlowArrows above, and the same reason for the overlay
        // pass. A circuit that stays home draws here exactly as it did.
        if (!Array.isArray(layer._powerCircuits) && window.app) {
            const assignments = window.app.calculatePowerAssignments(layer);
            layer._powerError = assignments.error;
            layer._powerCircuits = assignments.circuits || [];
            layer._powerCircuitRuns = assignments.runs || null;
            layer._powerCircuitNumKeys = assignments.nums || null;
            layer._powerCircuitOwners = this._powerOwnerIdRows(layer, assignments.layers);
        }
        if (layer._powerError) {
            this.ctx.restore();
            return;
        }

        // The cached owner rows hold ids (_powerOwnerIdRows); resolve them
        // through the same scope authority the ids were minted from.
        const ownerById = (window.app && typeof window.app.getPathScopeLayers === 'function')
            ? new Map(window.app.getPathScopeLayers(layer).map(l => [l.id, l]))
            : null;
        const autoNumKeys = layer._powerCircuitNumKeys;
        layer._powerCircuits.forEach((circuitPanels, idx) => {
            if (!circuitPanels || circuitPanels.length === 0) return;
            const circuitNum = autoNumKeys ? autoNumKeys[idx] : idx + 1;
            const owners = layer._powerCircuitOwners && layer._powerCircuitOwners[idx];
            const crosses = Array.isArray(owners)
                && owners.some(id => id != null && id !== layer.id);
            if (this._deferCrossMember(layer, crosses)) return;
            // A crossing circuit is drawn through each cabinet's own member's
            // frame; a cabinet on a member this view does not draw is left off
            // the line rather than run onto blank paper.
            const ownerOf = (i) => (owners && owners[i] != null && ownerById
                && ownerById.get(owners[i])) || layer;
            const drawPanels = crosses
                ? circuitPanels
                    .map((p, i) => ((ownerOf(i).visible !== false)
                        ? this._crossMemberPanelShim(ownerOf(i), p) : null))
                    .filter(Boolean)
                : circuitPanels;
            // Splitter circuit: break the daisy at run boundaries and fan
            // dashed stubs out from the feed - one label either way. The run
            // counts index the same list either way, so a crossing splitter
            // circuit keeps its branches instead of collapsing into one daisy.
            const counts = layer._powerCircuitRuns && layer._powerCircuitRuns[idx];
            if (counts && counts.length > 1) {
                let off = 0;
                drawCircuitBranches(
                    counts.map(n => drawPanels.slice(off, off += n)), circuitNum);
                return;
            }
            drawCircuit(drawPanels, circuitNum);
        });

        drawCableTags();
        this.ctx.restore();
    },

    // Soca/multi brackets above the wall on the power map: one bracket per
    // multi spanning the columns its 6 legs feed, labeled with the multi
    // name and home-run length (Binder convention). Brackets stack upward
    // when their spans overlap (row-major circuits usually span full width).
    //
    // Style B (2026-08-31): each pill carries a darker text badge with the
    // box's connector type - SOCA 208 / SOCA 120 / L21-30, read off the
    // screen's effective breakout - beside the name · length; a breakout
    // the type table does not name gets no badge. Stacking is unchanged
    // and exports draw the same path, so the badge prints when the
    // checkbox is on.
    //
    // Mid plug-drag, the multi the drop would feed draws DASHED under the
    // name the box would get ("SL3", the naming index's own derivation, so
    // it reads exactly as the committed bracket will): the pending
    // bracket. `pendingOnly`
    // is the brackets-off pass, which draws that one bracket and nothing
    // else.
    renderSocaBrackets(layer, pendingOnly) {
        if (!window.app || typeof window.app.getSocaPlan !== 'function') return;
        if ((layer.type || 'screen') !== 'screen') return;
        const pend = this._pendingPlugFor(layer);
        if (pendingOnly && !pend) return;
        let plan = window.app.getSocaPlan(layer);
        if (pendingOnly) plan = plan.filter(s => s.soca === pend.socaIndex);
        if (!plan.length) return;
        const badge = typeof window.app.outputTypeForBreakout === 'function'
            && typeof window.app.getPowerBreakout === 'function'
            ? window.app.outputTypeForBreakout(window.app.getPowerBreakout(layer), layer.powerVoltage)
            : null;
        const badgeText = badge ? badge.badge : null;
        const bounds = this.getLayerBounds(layer);
        const top = bounds.y;
        const labelSize = Math.max(11, (layer.powerLabelSize || 14) * 0.9);
        const legFont = Math.max(8, labelSize * 0.62);
        const pillH = labelSize + 6;
        // THE BAND'S OWN STRIP (2026-09-09). The pill used to straddle the
        // bracket line - and the bracket line is also where the leg ruler
        // hangs from, so every leg tick under the pill ran through it and
        // the ruler broke off wherever a band stood. On the user's own
        // export "S1-1 · 250 · 65.8A" read "S1-4". The pill now sits ON
        // the line, its bottom edge the line itself, and the ruler keeps
        // the strip beneath: two strips, never a shared pixel, and every
        // tick of the ruler reads at its full length.
        // The assembly gets exactly the height it has always had: the
        // binder's map gutter was cut for that, and a taller stack is not
        // clipped politely - it is simply lost off the top of the map's
        // bitmap, band and all. So the band's strip comes OUT of that
        // height and the ruler takes what is left, SHRINKING to fit it
        // where it must. The spacing gives way before the layout does,
        // the same instinct as the wiring sheet's adaptive pitch.
        // The row pitch is untouched for the same reason. A bracket only
        // draws a ruler when its legs sit on DISTINCT column groups (see
        // `distinct` below), and brackets that share a row's columns
        // outright draw none at all, so a stacked bracket's ruler and the
        // band under it do not meet in practice - and the map's label
        // registry (tests/test_map_label_collisions.py) is what says so
        // on real shows rather than this comment.
        const stack = 12 + legFont * 1.9 + pillH / 2;   // the room, as always
        const baseGap = Math.max(pillH * 0.4, stack - pillH);
        // The ruler shares out what is left under the line, and it does
        // not share it evenly: the L LABEL is the reading, so it keeps
        // its size as long as it can, and the TICK - which only points
        // at the columns - gives way first, down to a third of its
        // length. Both stop a pad short of the cabinets: a ruler label
        // with the wall's own edge line through it is the fault this
        // work is about, one strip further down.
        const legPad = Math.max(1, legFont * 0.15);
        const fullTick = labelSize * 0.45;
        const legTick = Math.max(fullTick * 0.35,
                                 Math.min(fullTick, (baseGap - legPad - legFont) / 1.5));
        const legSize = Math.min(legFont,
                                 Math.max(legFont * 0.7, baseGap - legPad - legTick * 1.5));
        const rowH = labelSize + 14;
        // assign stacking rows: first bracket whose x-span is free on a row
        const rows = [];   // per row: list of [x1, x2]
        const placed = plan.map(s => {
            if (!Number.isFinite(s.x1) || !Number.isFinite(s.x2)) return null;
            let r = 0;
            for (; ; r++) {
                const row = rows[r] || (rows[r] = []);
                if (row.every(([a, b]) => s.x2 + 12 < a || s.x1 - 12 > b)) { row.push([s.x1, s.x2]); break; }
            }
            return { s, r };
        }).filter(Boolean);

        this.ctx.save();
        // Printer page: the bracket and its pill in black on white.
        const orange = this._ink(layer.powerLabelBgColor || '#D95000');
        this.ctx.lineWidth = Math.max(1.5, labelSize * 0.12);
        this.ctx.strokeStyle = orange;
        this.ctx.fillStyle = orange;
        this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
        for (const { s, r } of placed) {
            const dashed = !!(pend && pend.socaIndex === s.soca);
            const y = top - baseGap - r * rowH;
            const tick = labelSize * 0.45;
            this.ctx.save();
            if (dashed) this.ctx.setLineDash([tick * 0.7, tick * 0.5]);
            this.ctx.beginPath();
            this.ctx.moveTo(s.x1, y + tick);
            this.ctx.lineTo(s.x1, y);
            this.ctx.lineTo(s.x2, y);
            this.ctx.lineTo(s.x2, y + tick);
            this.ctx.stroke();
            this.ctx.restore();
            // Leg ticks: drop a short mark from the bracket to the columns
            // each leg feeds, labeled L1..L6 (Binder power-diagram detail).
            // Only meaningful when the legs sit on DISTINCT column groups -
            // row-based circuits all span the same columns, so their ticks
            // would pile up on one x; skip them rather than draw a smear.
            const legs = (s.legs || [])
                .filter(l => Number.isFinite(l.x1) && Number.isFinite(l.x2))
                .map(l => ({ ...l, cx: (l.x1 + l.x2) / 2 }))
                .sort((a, b) => a.cx - b.cx);
            const minGap = legFont * 2.2;
            const distinct = legs.length > 1 &&
                legs.every((l, i) => i === 0 || (l.cx - legs[i - 1].cx) >= minGap);
            if (distinct) {
                this.ctx.save();
                this.ctx.lineWidth = Math.max(1, labelSize * 0.07);
                this.ctx.font = `600 ${legSize}px ${projectFontFamily()}`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'top';
                const lw = this.ctx.lineWidth;
                for (const l of legs) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(l.cx, y);
                    this.ctx.lineTo(l.cx, y + legTick * 1.5);
                    this.ctx.stroke();
                    this._noteLabelBox('rulerTick', 'L' + l.leg,
                                       l.cx - lw / 2, y, lw, legTick * 1.5);
                    if (this.labelProbe) {
                        const lwid = this.ctx.measureText('L' + l.leg).width;
                        this._noteLabelBox('rulerLabel', 'L' + l.leg,
                                           l.cx - lwid / 2, y + legTick * 1.6, lwid, legSize);
                    }
                    this._fillText('L' + l.leg, l.cx, y + legTick * 1.6);
                }
                this.ctx.restore();
            }
            // Home-run lengths are paperwork: they print on exported maps
            // (like the Binder's power diagram) but stay off the working view.
            const label = (dashed ? pend.boxName : s.name)
                + (this.exportMode && s.length ? ` · ${s.length}` : '')
                + ` · ${s.amps.toFixed(1)}A`;
            const cx = (s.x1 + s.x2) / 2;
            const tw = this.ctx.measureText(label).width;
            // the type badge: a darker sub-pill before the text, in the
            // mono register the chips and the LEGS line use
            const badgeFont = `bold ${Math.max(7, labelSize * 0.68)}px `
                + 'ui-monospace, Menlo, Consolas, monospace';
            let bw = 0;
            const badgePad = labelSize * 0.3;
            if (badgeText) {
                this.ctx.save();
                this.ctx.font = badgeFont;
                bw = this.ctx.measureText(badgeText).width + badgePad * 2;
                this.ctx.restore();
            }
            const gap = badgeText ? labelSize * 0.3 : 0;
            // The band's own strip: the pill RESTS on the bracket line
            // (its bottom edge IS the line) instead of straddling it, so
            // the leg ruler hanging under the line keeps a clear strip -
            // see baseGap above.
            this.ctx.save();
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.globalCompositeOperation = 'source-over';
            const padX = labelSize * 0.4;
            const pillW = tw + bw + gap + padX * 2;
            const px0 = cx - pillW / 2;
            const pillY = y - pillH;         // the pill's top; its foot is y
            const yText = y - pillH / 2;     // the middle of the pill
            this._noteLabelBox('band', label, px0, pillY, pillW, pillH);
            this.ctx.fillStyle = dashed ? 'rgba(0, 0, 0, 0.6)' : (this.printerMode ? '#ffffff' : orange);
            this.ctx.beginPath();
            if (this.ctx.roundRect) this.ctx.roundRect(px0, pillY, pillW, pillH, pillH / 2);
            else this.ctx.rect(px0, pillY, pillW, pillH);
            this.ctx.fill();
            if (this.printerMode && !dashed) {
                this.ctx.strokeStyle = PRINTER_INK;
                this.ctx.lineWidth = Math.max(1, labelSize * 0.08);
                this.ctx.stroke();
            }
            if (dashed) {
                // the pending pill: dark, dashed orange rim, orange text
                this.ctx.strokeStyle = orange;
                this.ctx.lineWidth = Math.max(1, labelSize * 0.08);
                this.ctx.setLineDash([tick * 0.6, tick * 0.4]);
                this.ctx.stroke();
                this.ctx.setLineDash([]);
            }
            const ink = dashed ? orange
                : (this.printerMode ? PRINTER_INK : (layer.powerLabelTextColor || '#000000'));
            let cursor = px0 + padX;
            if (badgeText) {
                const bh = pillH - 6;
                this.ctx.fillStyle = dashed
                    ? 'rgba(217, 80, 0, 0.22)'
                    : (this.printerMode ? '#e9e9e9' : 'rgba(0, 0, 0, 0.28)');
                this.ctx.beginPath();
                if (this.ctx.roundRect) this.ctx.roundRect(cursor, yText - bh / 2, bw, bh, bh / 2);
                else this.ctx.rect(cursor, yText - bh / 2, bw, bh);
                this.ctx.fill();
                this.ctx.save();
                this.ctx.font = badgeFont;
                this.ctx.fillStyle = ink;
                this._fillText(badgeText, cursor + bw / 2, yText + 0.5);
                this.ctx.restore();
                cursor += bw + gap;
            }
            this.ctx.fillStyle = ink;
            this._fillText(label, cursor + tw / 2, yText);
            this.ctx.restore();
        }
        this.ctx.restore();
    },

    // The plug drag's pending box on this screen, off the dock's live drop
    // target (app-dock.js _dockScreenTarget stamps `plug` on it, and so
    // does the hit test for a typed spare box over a circuit - a `run`
    // target): the multi index the drop would feed and the name the box
    // would get. Null when no plug drag targets this screen, or the drop
    // would be refused.
    _pendingPlugFor(layer) {
        const t = window.app && window.app._dockDropTarget;
        if (!t || (t.kind !== 'screen' && t.kind !== 'run')
                || t.layerId !== layer.id) {
            return null;
        }
        return (t.plug && t.plug.ok) ? t.plug : null;
    },

    // The shared circuits of a screen, resolved for drawing: one entry per
    // circuit that gangs more than one run - its number, the run ids it
    // joins, how many ways the splitter is, and whether the shared load is
    // past the screen's amps figure (the soca plan's per-leg amps against
    // powerAmperage - the same `over` the tray's gang tag reads). Read by
    // the bracket under the runs' feet AND by the label pass, which hangs
    // the Nfer pill off every disc the shared circuit gets - so the two
    // never disagree about which circuits are shared. Empty off a
    // non-screen layer, or when the app is not up (a unit render).
    _nferGangs(layer) {
        if (!window.app || typeof window.app.screenCircuits !== 'function') return [];
        if ((layer.type || 'screen') !== 'screen') return [];
        const shared = window.app.screenCircuits(layer)
            .filter(c => Array.isArray(c.runIds) && c.runIds.length > 1);
        if (!shared.length) return [];
        const cap = parseFloat(layer.powerAmperage) || 0;
        const byNum = new Map();
        if (typeof window.app.getSocaPlan === 'function') {
            (window.app.getSocaPlan(layer) || []).forEach(s =>
                (s.legs || []).forEach(l => byNum.set(l.circuit, l.amps)));
        }
        return shared.map(c => {
            const amps = byNum.get(c.num) || 0;
            return { num: c.num, runIds: c.runIds.slice(), ways: c.runIds.length,
                     over: cap > 0 && amps > cap + 1e-9, panels: c.panels, layers: c.layers };
        });
    },

    // The Nfer pill's text for one shared circuit, or null for no pill.
    // "2fer" / "3fer", "· OVER" appended when the shared load is past the
    // circuit's amps. The tag is text the user may not want on the wall -
    // "i need a way to disable the twofer/3fer text on the screen if i
    // dont want it there" (2026-09-06): per screen (showPowerNferTags,
    // default on), and the same test in exportMode so the PDF matches the
    // screen. An OVER gang is a warning, not decoration: with the tags off
    // it still prints OVER alone, because a red stroke by itself is easy
    // to miss on a busy wall.
    _nferTagText(layer, gang) {
        const tagsOff = layer.showPowerNferTags === false;
        if (tagsOff && !gang.over) return null;
        return tagsOff ? 'OVER' : `${gang.ways}fer${gang.over ? ' · OVER' : ''}`;
    },

    // The Nfer pill's colours: the tray's gang tag is the model - a dark
    // pill, white text, a grey rim - and red with a white rim when OVER.
    // Its own colour, never the label's: a gang tag in the power label's
    // orange sat on the wall as one more orange disc - "when two fer is
    // shown it should not be the same color as the power label due to it
    // being hard to read" (2026-09-06). The printer page swaps the family
    // for black on white in drawCableTag itself, OVER saying so in text.
    _nferTagColors(gang) {
        return gang.over
            ? { fill: '#d05a52', rim: '#ffffff', ink: NFER_TAG_COLORS.ink }
            : NFER_TAG_COLORS;
    },

    // A committed gang's face on the wall (2026-08-30, "B and then right
    // click"): a bracket spanning the ganged runs' FEET - red when the
    // shared circuit is past the screen's amps figure. The concept mock's
    // after-strips promised exactly this; before it a share barely read on
    // the map at all. Drawn from the layer's own power pass, so it inherits
    // every transform the runs get, and it draws in exports too - the soca
    // brackets live ABOVE the screen, this below, so the two never
    // collide. Cross-member circuits keep the bracket on the OWNER's own
    // cabinets: a peer's cabinets live in the peer's frame and a span
    // computed across frames would land nowhere.
    // The "2fer" / "3fer" pill used to float on this line, and on a wall
    // of row runs the line is a row seam a long way from the runs' heads:
    // "the drawing isn't obvious what it is connected to" (2026-09-15).
    // The pill now hangs off the shared circuit's own label disc with its
    // cable tag - "it should just connect to 10' True1 for example. just
    // put it right above that or under it" - see renderPowerArrows'
    // drawCableTags. The bracket itself is unchanged.
    renderNferBrackets(layer) {
        const gangs = this._nferGangs(layer);
        if (!gangs.length) return;
        const labelSize = Math.max(10, (layer.powerLabelSize || 14) * 0.8);
        this.ctx.save();
        for (const c of gangs) {
            const own = c.layers
                ? c.panels.filter((p, i) => !c.layers[i]
                    || c.layers[i] === layer || c.layers[i].id === layer.id)
                : c.panels;
            if (!own.length) continue;
            let x1 = Infinity, x2 = -Infinity, yBot = -Infinity;
            own.forEach(p => {
                x1 = Math.min(x1, Number(p.x) || 0);
                x2 = Math.max(x2, (Number(p.x) || 0) + (Number(p.width) || 0));
                yBot = Math.max(yBot,
                    (Number(p.y) || 0) + (Number(p.height) || 0));
            });
            if (!Number.isFinite(x1) || !Number.isFinite(x2)
                    || !Number.isFinite(yBot)) continue;
            // The tray's gang tag's grey; red only when OVER.
            const color = this._ink(c.over ? '#d05a52' : NFER_TAG_COLORS.rim);
            // Hugging the gang's own boundary: below the screen for
            // column runs (the clean mock look), ON the row seam for
            // horizontal runs - either way, the line under "these runs
            // share one feed".
            const y = yBot + labelSize * 0.25;
            const tick = labelSize * 0.45;
            this.ctx.lineWidth = Math.max(1.5, labelSize * 0.12);
            this.ctx.strokeStyle = color;
            this.ctx.beginPath();
            this.ctx.moveTo(x1 + 2, y - tick);
            this.ctx.lineTo(x1 + 2, y);
            this.ctx.lineTo(x2 - 2, y);
            this.ctx.lineTo(x2 - 2, y - tick);
            this.ctx.stroke();
        }
        this.ctx.restore();
    },

    // The cable tag: "10' True1" in the mock's gold on near-black with a
    // gold rim (.cl .tag of cables-mock.html), hung off the right edge of
    // the label circle in the label's own size register - a reading beside
    // the label, never a second label. `x` is the circle's right edge.
    // `colors` swaps the family - the data side's snake / home-run tag
    // wears the data cable's blue (DATA_CABLE_TAG_COLORS) through this
    // same drawer rather than a second one.
    //
    // `opts.flip` hangs the tag off the LEFT edge instead (x is then the
    // circle's left edge): a label on the wall's right edge would push
    // its tag off the screen and under the next one - "there are no tags
    // for SR 1-1 and so on. they are to the right behind the other screen.
    // they should be on the inside of the screen" (2026-09-06). The
    // callers measure with cableTagWidth and flip when the right side
    // would leave the screen.
    //
    // A long tag wraps at its spaces the way a port label does - "also we
    // should add wrapping like we did to port labels on cable extensions
    // such as Snake 1 SR A would be / Snake 1 / SR A" (2026-09-07). The
    // rule, in cableTagLayout: a tag wider than 4.5 x labelSize on one
    // line splits at whitespace into the fewest lines (at most 3) whose
    // widest line fits that cap. 4.5 x labelSize is about the label
    // marker's own diameter plus one: past that a pill stops reading as a
    // tag beside its label and starts covering cabinets. A tag that fits,
    // or has no space to break at, draws exactly as it always has.
    cableTagWidth(text, labelSize) {
        return labelSize * 0.25 + this.cableTagLayout(text, labelSize).width;   // gap + pill
    },

    // The words a cable tag may break between. A bare number or a single
    // character is a name's suffix, not a word of its own - "Snake 1",
    // "SR A", "SNAKE A" - so it stays with the word before it and a wrap
    // never strands it at the head of a line: the user's own split of
    // "Snake 1 SR A" is "Snake 1" / "SR A", where a purely width-balanced
    // break would have given "Snake" / "1 SR A". (The port label keeps its
    // raw tokens: its wrap is about circle size, and "SR" over "A1" is the
    // shape it was built for.)
    _cableTagUnits(text) {
        const tokens = String(text).trim().split(/\s+/).filter(t => t.length > 0);
        const units = [];
        for (const t of tokens) {
            const suffix = units.length > 0 && (t.length === 1 || /^\d+$/.test(t));
            if (suffix) units[units.length - 1] += ' ' + t;
            else units.push(t);
        }
        return units;
    },

    /**
     * Lay a cable tag out: { lines, width, height } plus the register it
     * was measured in (size, padX, lineHeight). `width` and `height` are
     * the pill's: the widest line plus the side padding, and
     * lines x lineHeight + 4. The leading is the tag's own text size, so
     * one line gives exactly the old size + 4 pill and a stack stays as
     * tight as one tag should. When even three lines cannot meet the cap
     * the three-line split stands - it is as narrow as the tag gets.
     */
    cableTagLayout(text, labelSize) {
        // The tag's text is 85% of the map's label size (owner, 2026-09-26,
        // picked from rendered sizes on his show: at 70% "the cable length
        // text is a bit small").
        const size = Math.max(8, labelSize * 0.85);
        const padX = size * 0.45;
        const lineHeight = size;
        const str = String(text);
        this.ctx.save();
        this.ctx.font = `bold ${size}px ${projectFontFamily()}`;
        const widthOf = (s) => this.ctx.measureText(s).width;
        // The wrap cap grows with the text (4.5 labels at the old 70%
        // register), so a bigger tag wraps exactly where it used to.
        const cap = size * (4.5 / 0.7);
        let lines = [str];
        let widest = widthOf(str);
        if (widest > cap) {
            const units = this._cableTagUnits(str);
            for (let n = 2; n <= Math.min(units.length, 3); n++) {
                lines = this._balancedSplit(units, n, widthOf);
                widest = Math.max(...lines.map(widthOf));
                if (widest <= cap) break;
            }
        }
        this.ctx.restore();
        return {
            lines, size, padX, lineHeight,
            width: widest + padX * 2,
            height: lines.length * lineHeight + 4,
        };
    },

    // The pill a cable tag draws, before anything is painted: its rect in
    // the caller's frame and the layout it was measured with - the drawer
    // and the placement read the same rect, so a placement tested clear
    // of a label is the pill that lands. `opts.side` says where the pill
    // hangs off the anchor (x, y):
    //   'right' (the default) - x is the circle's RIGHT edge, y its centre
    //   'left'  (opts.flip)   - x is the circle's LEFT edge, y its centre
    //   'below' / 'above'     - x is the circle's CENTRE, y its bottom /
    //                           top edge; the pill is centred under / over
    // `opts.top` / `opts.bottom` are the screen's edges: a pill taller than
    // the room shifts inside them the way the circle's centre was shifted
    // inside the screen. `opts.left` / `opts.right` do the same for a
    // below / above pill, which is centred on its label rather than hung
    // off its edge and so has no side of its own to keep: it slides along
    // the screen's edge instead of hanging over it. A pill hung LEFT or
    // RIGHT is never slid - it would leave the label it names.
    cableTagRect(text, x, y, labelSize, opts) {
        const tag = this.cableTagLayout(text, labelSize);
        const side = (opts && opts.side) || ((opts && opts.flip) ? 'left' : 'right');
        const stacked = side === 'below' || side === 'above';
        // A pill hung off a label's SIDE stands a quarter-label away, as
        // it always has. One hung UNDER or OVER stands further off
        // (2026-09-09): a disc is at its widest exactly where a stacked
        // pill is centred, so the quarter-label that reads as a gap
        // beside a label read as a pill welded to it on a dense wall -
        // "the label discs and their cable tags are jammed into each
        // other". More than the pill's own corner radius, so the two
        // rounded rims never look joined.
        const gap = labelSize * (stacked ? 0.6 : 0.25);
        let left, top;
        if (side === 'left') left = x - gap - tag.width;
        else if (side === 'right') left = x + gap;
        else left = x - tag.width / 2;
        if (side === 'below') top = y + gap;
        else if (side === 'above') top = y - gap - tag.height;
        else top = y - tag.height / 2;
        if (opts && Number.isFinite(opts.top) && Number.isFinite(opts.bottom)) {
            if (top + tag.height > opts.bottom) top = opts.bottom - tag.height;
            if (top < opts.top) top = opts.top;
        }
        if (stacked && opts && Number.isFinite(opts.left) && Number.isFinite(opts.right)) {
            if (left + tag.width > opts.right) left = opts.right - tag.width;
            if (left < opts.left) left = opts.left;
        }
        return { x: left, y: top, w: tag.width, h: tag.height, side, layout: tag, gap };
    },

    // Where a cable tag goes so it covers no OTHER label of its screen -
    // "the cables added to the power or data sometimes go under labels and
    // overlap" (2026-09-09): a tag beside one label landed on the next
    // label when two runs began a panel apart. The label circle is at
    // (cx, cy) with `radius`; `bounds` is the screen ({ left, top, right,
    // bottom }); `discs` every label circle of the same pass ({ x, y, r }),
    // the tag's own among them (it is skipped by identity, and a pill
    // never touches the circle it hangs off anyway - the gap is between
    // them). Tried in order: the side the tag always took (right, or left
    // when right would leave the screen and left would not), the other
    // side, below the label, above it - a below / above pill slides along
    // the screen's edge rather than hang over it (cableTagRect); the first
    // pill inside the screen that meets no other disc AND NO PILL ALREADY
    // PLACED wins. `taken` is those pills, in the order they were placed:
    // without it a tag hung right off one label and a tag hung left off
    // the next printed clean through each other, each of them clear of
    // every DISC and neither of them aware of the other (Kelly, SL ·
    // POWER, 2026-09-09: "5' True1" and "10' True1" overprinted by 185 x
    // 51 pixels of the map).
    // When no side is clear the spacing gives way before the layout does:
    // the candidate that covers the LEAST of anything else wins, rather
    // than a flat fall back to below that could have been the worst of
    // the four. Returns the anchor and opts for drawCableTag, with the
    // pill.
    //
    // BOTH MAPS LEAD WITH THE RUN'S SIDE (owner's ruling, 2026-09-25,
    // chosen from rendered options on his show; the power map first, the
    // data map's port tags the same day - "we need to make the cable tag
    // in the top correct not on the side like it is"). A head's tags go by
    // the way its run LEAVES the disc (_tagRunSide): a run that goes DOWN,
    // RIGHT or LEFT hangs them ABOVE the disc, a run that goes UP hangs
    // them UNDER it, and a one-cabinet run hangs them above.
    // `place.prefer` names that side; it is tried FIRST, then the OTHER
    // side of the disc (above <-> under: a top-row head with no room over
    // it hangs its tags under the disc, not beside it - the owner, same
    // day), then beside it (right-or-left, the other), with the same
    // clear-first / least-bad scoring. Called with no `place` the order is
    // the old one (beside first) - no map calls it that way any more.
    // `place.stack` ({ w, h, gap }, _stackReserve)
    // is a pill that will stack under this one (a head's 2fer / 3fer): the
    // column is judged whole, and hung ABOVE the disc the tag stands that
    // pill higher, so the stack reads tag, pill, disc top to bottom - under
    // the disc it reads disc, tag, pill. An above / under pill is centred
    // on the disc's x. With `place` given, a candidate that the screen's
    // edge has slid back onto its OWN disc counts as covering it - a head
    // on the wall's top row whose tag cannot stand over it moves on rather
    // than print across its own label.
    placeCableTag(text, cx, cy, radius, labelSize, bounds, discs, own, taken, place) {
        const w = this.cableTagWidth(text, labelSize);
        const rightFits = cx + radius + w <= bounds.right;
        const leftFits = cx - radius - w >= bounds.left;
        const first = (!rightFits && leftFits) ? 'left' : 'right';
        let order = [first, first === 'right' ? 'left' : 'right', 'below', 'above'];
        const prefer = place && place.prefer;
        if (prefer && order.includes(prefer)) {
            // the run-side fallback is the OTHER side of the disc, then
            // beside it (owner, 2026-09-25: a top-row head with no room
            // above hangs its tags under the disc, not beside it)
            const other = prefer === 'above' ? 'below' : prefer === 'below' ? 'above' : null;
            const head = other ? [prefer, other] : [prefer];
            order = [...head, ...order.filter(o => !head.includes(o))];
        }
        const stack = (place && place.stack) || null;
        const lift = stack ? stack.h + stack.gap : 0;
        const anchor = (side) => side === 'right' ? { x: cx + radius, y: cy }
            : side === 'left' ? { x: cx - radius, y: cy }
            : side === 'below' ? { x: cx, y: cy + radius }
            : { x: cx, y: cy - radius - lift };
        const candidate = (side) => {
            const a = anchor(side);
            const opts = { side, flip: side === 'left', top: bounds.top, bottom: bounds.bottom,
                           left: bounds.left, right: bounds.right };
            const rect = this.cableTagRect(text, a.x, a.y, labelSize, opts);
            // the column the cost is read over: the pill, and the one
            // stacked centred under it when there is one
            let cover = rect;
            if (stack) {
                const sx = rect.x + rect.w / 2 - stack.w / 2;
                const sy = rect.y + rect.h + stack.gap;
                const x0 = Math.min(rect.x, sx), x1 = Math.max(rect.x + rect.w, sx + stack.w);
                cover = { x: x0, y: rect.y, w: x1 - x0, h: sy + stack.h - rect.y, gap: rect.gap };
            }
            return { x: a.x, y: a.y, opts, rect, cover };
        };
        const eps = 1e-6;
        const cost = this._tagCover(bounds, discs, own, taken, !!place);
        const strip = (c) => ({ x: c.x, y: c.y, opts: c.opts, rect: c.rect });
        let best = null, bestCost = Infinity;
        for (const side of order) {
            const c = candidate(side);
            const k = cost(c.cover);
            if (k <= eps) return strip(c);
            if (k < bestCost) { bestCost = k; best = c; }
        }
        return strip(best || candidate('below'));
    },

    // The room a head's second pill (its 2fer / 3fer) takes under the
    // first: its width and height and the hair between the two - what
    // placeCableTag reserves and placeStackedTag then fills.
    _stackReserve(text, labelSize) {
        const tag = this.cableTagLayout(text, labelSize);
        return { w: tag.width, h: tag.height, gap: Math.max(1, labelSize * 0.08) };
    },

    // What a pill at a candidate rect would cover, as a function of the
    // rect: the discs it meets (`discs`, its own `own` skipped unless
    // `withOwn`), the pills already down (`taken`), and any part of it
    // outside the screen (`bounds`). Zero is a clear placement. Shared by
    // placeCableTag and placeStackedTag so the two rows of a head's stack
    // are judged alike. `withOwn` (the run-side placement, both maps)
    // counts the own disc too - a pill never meets the disc it hangs off
    // unless the screen's edge slid it there - and holds the pill half its
    // height off the other discs above and under it. Off its OWN disc it
    // is held the lesser of that and the stand-off cableTagRect gave it
    // (`rc.gap`): a pill where cableTagRect hung it is clear, one the
    // screen's edge slid in toward its disc is not - a head on the top
    // row of a short wall (Kelly's DJ Booth, data, 2026-09-25) had its tag
    // pushed down to a third of its height off the disc, the rims reading
    // as one; it goes to the other side instead.
    _tagCover(bounds, discs, own, taken, withOwn) {
        const eps = 1e-6;
        const inside = (rc) => rc.x >= bounds.left - eps && rc.x + rc.w <= bounds.right + eps
            && rc.y >= bounds.top - eps && rc.y + rc.h <= bounds.bottom + eps;
        const meets = (rc, d) => {
            const qx = Math.max(rc.x, Math.min(d.x, rc.x + rc.w));
            const qy = Math.max(rc.y, Math.min(d.y, rc.y + rc.h));
            return (qx - d.x) * (qx - d.x) + (qy - d.y) * (qy - d.y) < d.r * d.r - eps;
        };
        const others = (discs || []).filter(d => d && d !== own);
        const placed = (taken || []).filter(Boolean);
        const overlaps = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x))
            * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
        return (rc) => {
            let c = 0;
            // On the run-side path a pill also keeps half its own height
            // off any OTHER disc above or under it - the stand-off a pill
            // keeps from the disc it hangs off (cableTagRect), so a tag
            // hung over its disc never jams against the disc of the circuit
            // a cabinet up the column.
            const m = withOwn ? rc.h / 2 : 0;
            const probe = m ? { x: rc.x, y: rc.y - m, w: rc.w, h: rc.h + 2 * m } : rc;
            for (const d of others) {
                if (!meets(probe, d)) continue;
                c += overlaps(probe, { x: d.x - d.r, y: d.y - d.r, w: d.r * 2, h: d.r * 2 });
            }
            if (withOwn && own) {
                const mo = Math.min(rc.h / 2, rc.gap || 0);
                const near = mo ? { x: rc.x, y: rc.y - mo, w: rc.w, h: rc.h + 2 * mo } : rc;
                if (meets(near, own)) {
                    c += overlaps(near, { x: own.x - own.r, y: own.y - own.r, w: own.r * 2, h: own.r * 2 });
                }
            }
            for (const t of placed) c += overlaps(rc, t);
            if (!inside(rc)) c += rc.w * rc.h;
            return c;
        };
    },

    // Where a second pill goes in a head's tag stack: directly UNDER the
    // pill already there (`base`, a rect placeCableTag returned), CENTRED
    // on the base's x - "3fer etc needs to be centered under the True1
    // extension" (owner, 2026-09-25; until then it sat flush with the
    // base's edge nearest the disc) - and a hair of a gap between them, so
    // the two read as one column: "SR 5-5 · 10' True1 · 3fer". A base hung
    // ABOVE its disc was lifted by placeCableTag to leave exactly this
    // slot, so there the pill sits between the tag and the disc. Above the
    // base instead when under it would leave the screen or cover a disc
    // (its own included) or a pill already down; when neither is clear the
    // one that covers less wins, the same give as placeCableTag. Same
    // return shape: the anchor and opts drawCableTag takes (a 'right' hang
    // whose gap is the quarter label cableTagRect adds, so the pill lands
    // exactly on `rect`).
    placeStackedTag(text, base, labelSize, bounds, discs, own, taken) {
        const tag = this.cableTagLayout(text, labelSize);
        const gap = this._stackReserve(text, labelSize).gap;
        const left = base.x + base.w / 2 - tag.width / 2;
        const candidate = (top) => {
            const rect = { x: left, y: top, w: tag.width, h: tag.height };
            return { x: rect.x - labelSize * 0.25, y: rect.y + rect.h / 2,
                     opts: { side: 'right' }, rect };
        };
        const cost = this._tagCover(bounds, discs, own, taken, true);
        const below = candidate(base.y + base.h + gap);
        const above = candidate(base.y - gap - tag.height);
        const kb = cost(below.rect);
        if (kb <= 1e-6) return below;
        const ka = cost(above.rect);
        return ka < kb ? above : below;
    },

    // The side the owner ruled for a head's cable tags (2026-09-25; power
    // and data maps alike), read off the run's first step AS DRAWN
    // ({ dx, dy } in the layer's frame, or null): the step is carried into
    // `F`, the upright frame of _tagFrame, so "down" is down on the sheet
    // whatever the screen's rotation or Back-view mirror. A run that
    // leaves its disc going UP hangs its tags under the disc ('below');
    // down, right, left - and a one-cabinet run, which has no step - hang
    // them above it. A diagonal step goes by its larger axis (a tie by the
    // vertical one).
    _tagRunSide(step, F) {
        if (!step) return 'above';
        const o = F.toU(0, 0), e = F.toU(step.dx, step.dy);
        const dx = e.x - o.x, dy = e.y - o.y;
        return (Math.abs(dy) >= Math.abs(dx) && dy < 0) ? 'below' : 'above';
    },

    // The frame a tag is placed in: the layer's own, turned by the
    // screen's active rotation (and mirrored on a Back view) so that its
    // axes are the PAGE's. `toU` carries a layer-frame point into it,
    // `fromU` brings one back; `active` says whether the two differ at
    // all. A pill placed in this frame is placed the way it will be read
    // - beside its disc on the page - and drawCableTag paints it upright
    // about `opts.pivot`, the layer-frame point its anchor came from.
    _tagFrame() {
        const rad = (this._keepTextUpright && this._activeRotationRad) || 0;
        const mirror = !!this._mirror;
        const cos = Math.cos(rad), sin = Math.sin(rad);
        return {
            active: !!(rad || mirror),
            toU: (x, y) => {
                const ux = x * cos - y * sin, uy = x * sin + y * cos;
                return { x: mirror ? -ux : ux, y: uy };
            },
            fromU: (ux, uy) => {
                const x = mirror ? -ux : ux, y = uy;
                return { x: x * cos + y * sin, y: -x * sin + y * cos };
            },
        };
    },

    // Draws the pill cableTagRect describes at (x, y) - see it for the
    // anchor and `opts.side` / `opts.flip` / `opts.top` / `opts.bottom`.
    // `opts.pivot`: (x, y) are then in the upright frame of _tagFrame and
    // the pivot is the layer-frame point they came from; the pill (rim,
    // fill, text and the registry's box) is painted about the pivot under
    // the same counter-rotation _fillText keeps a label upright with, so
    // the pill stands up WITH its text. Without it, or on an unrotated
    // screen, the pill draws where it always has.
    // `kind` is the registry kind the pill is noted under: 'tag' (a cable
    // tag) unless the caller says otherwise - the Nfer pill notes itself
    // as 'gang', the name the collision guards and the binder's ink price
    // have always known the 2fer / 3fer pill by.
    drawCableTag(text, x, y, labelSize, colors, opts, kind) {
        const c = this.printerMode ? PRINTER_TAG_COLORS : (colors || POWER_CABLE_TAG_COLORS);
        const rc = this.cableTagRect(text, x, y, labelSize, opts);
        const tag = rc.layout;
        const { size, padX, lineHeight } = tag;
        this.ctx.save();
        this.ctx.font = `bold ${size}px ${projectFontFamily()}`;
        const pillW = rc.w;
        const pillH = rc.h;
        // The corner radius of a ONE-line pill: a taller box keeps a
        // modest rounding rather than turning into a capsule.
        const corner = (size + 4) / 2;
        const left = rc.x;
        // The anchor as given: the pivot is the layer-frame point it came
        // from, so the counter-rotation below is taken about IT - not about
        // the pill's centre, which an above / under hang (or a pill slid
        // inside the screen's edge) puts somewhere else (2026-09-25: a
        // 3fer stacked under a tag hung over its disc printed across the
        // tag on a 90-degree screen).
        const anchorY = y;
        y = rc.y + pillH / 2;
        // THE PILL STANDS UP WITH ITS TEXT (2026-09-15). On a rotated
        // screen the text is kept upright by _fillText, counter-rotated
        // about its anchor - and the pill was not, so a 90-degree screen
        // drew a vertical capsule with "10' Edison" lying across it. With
        // a pivot the whole pill is painted under that same counter-
        // rotation about the pivot, text included (raw fillText: the
        // frame is already upright, so _fillText's own turn would be one
        // too many), and the registry notes the box under it - which is
        // where the ink lands. Without a pivot, or unrotated: no
        // transform, the same rect, the same _fillWrappedLabel as ever.
        const pivot = opts && opts.pivot;
        const upright = this._keepTextUpright && this._activeRotationRad;
        const turned = !!(pivot && (this._mirror || upright));
        if (turned) {
            this.ctx.translate(pivot.x, pivot.y);
            if (upright) this.ctx.rotate(-this._activeRotationRad);
            if (this._mirror) this.ctx.scale(-1, 1);
            this.ctx.translate(-x, -anchorY);
        }
        this._noteLabelBox(kind || 'tag', text, left, y - pillH / 2, pillW, pillH);
        this.ctx.beginPath();
        if (this.ctx.roundRect) {
            this.ctx.roundRect(left, y - pillH / 2, pillW, pillH, corner);
        } else {
            this.ctx.rect(left, y - pillH / 2, pillW, pillH);
        }
        this.ctx.fillStyle = c.fill;
        this.ctx.fill();
        this.ctx.lineWidth = Math.max(1, size * 0.1);
        this.ctx.strokeStyle = c.rim;
        this.ctx.stroke();
        this.ctx.fillStyle = c.ink;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'middle';
        if (turned) {
            const n = tag.lines.length;
            for (let i = 0; i < n; i++) {
                this.ctx.fillText(tag.lines[i], left + padX, y + (i - (n - 1) / 2) * lineHeight);
            }
        } else {
            // One line is _fillText, the same call as before the wrap; a
            // stack is left-aligned at the pill's text edge, centred on y.
            this._fillWrappedLabel(tag.lines, left + padX, y, size, lineHeight);
        }
        this.ctx.restore();
    },

    renderPowerErrorOverlay(layer) {
        if (!layer._powerError) return;
        const err = layer._powerError;
        // Same as renderCapacityErrorOverlay: this is called from the third
        // render pass outside the per-layer translate, so we need the layer's
        // active-view bounds (show offset already baked in), using raw
        // processor bounds parks the badge at the wrong screen position when
        // the layer is moved in Show Look.
        const bounds = this.getLayerBoundsInActiveView(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;

        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);

        const titleText = err.message || 'POWER ERROR';
        this.ctx.font = `bold 42px ${projectFontFamily()}`;
        const titleWidth = this.ctx.measureText(titleText).width;
        const textBoxWidth = titleWidth + 40;
        const textBoxHeight = 90;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );

        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = `bold 42px ${projectFontFamily()}`;
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this._fillText(titleText, layerCenterX, layerCenterY);
    },
    
    renderPower(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            if (!this._stageOn('Borders')) return;
            this._svgGroup('Borders', layer);
            this.ctx.strokeStyle = this.printerMode ? 'rgba(0, 0, 0, 0.3)' : 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }

        const paintFill = this._stageOn('Panels');
        let fillHex = null;
        // The printer page has no colour to code with: the cabinets stay
        // grey and the circuits are told apart by their dashes.
        if (layer.powerColorCodedView && !layer._powerError && !this.printerMode) {
            // v0.11.0: the circuit tinting this cabinet is usually one of this
            // layer's own, but a group peer's circuit can have claimed it - and
            // then the COLOUR is the peer's, because the palette and the circuit
            // number both belong to the layer that owns the circuit. Without
            // this a cross-member circuit tinted only the half of itself that
            // happened to sit on the layer being drawn.
            const hit = this._powerCircuitForPanel(layer, panel);
            if (hit && hit.circuitNum) {
                fillHex = this.getPowerCircuitColor(hit.owner, hit.circuitNum);
            }
        }

        if (!paintFill) {
            // The Borders stage of the Elements export: no fill at all.
        } else if (fillHex) {
            // Circuit color-coded view: keep the flat circuit color readable
            // (no gradient on top).
            this.ctx.fillStyle = fillHex;
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        } else if (!layer.transparentFill) {
            // Base cabinet fill: checkerboard / palette, same as Pixel Map,
            // with the gradient overlay on top (below borders and circuit
            // lines). These used to hard-code the plain checkerboard, so
            // gradients, palette modes, and Transparent (no fill) were all
            // ignored on the Power view. Circuit color-coding above is data,
            // not decoration, so it still paints on a transparent screen.
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            this._applyGradientOverlay(panel, layer);
        }

        if (layer.show_panel_borders && this._stageOn('Borders')) {
            this._svgGroup('Borders', layer);
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'power');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
        }
    },
});
