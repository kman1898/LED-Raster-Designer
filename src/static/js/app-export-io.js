// app-export-io: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ExportIo {
    // The frame rates a processor actually PUBLISHES a per-port figure for.
    //
    // Intersection across bit depths, not union: a rate present at 8-bit but
    // missing at 12-bit would still have to be interpolated the moment the
    // user changed bit depth, which is the thing this exists to prevent.
    // Rounded, because lookupPortCapacity matches on Math.round - 23.976 reads
    // the published 24 Hz row, 29.97 the 30, 59.94 the 60. Those three are
    // safe to offer: each is slightly SLOWER than the row it borrows, and
    // capacity rises as frame rate falls, so the published figure understates
    // them. Understating means more ports, never fewer.
    publishedFrameRates(processorType) {
        const table = this.portCapacityTables
            && this.portCapacityTables[processorType || 'novastar-armor'];
        if (!table) return null;
        const perDepth = Object.keys(table)
            .map(bd => new Set(Object.keys(table[bd] || {}).map(Number)))
            .filter(s => s.size > 0);
        if (perDepth.length === 0) return null;
        return perDepth.reduce((acc, s) => new Set([...acc].filter(r => s.has(r))));
    }

    // v0.11.0: the list is built from the processor's own published rows.
    //
    // It used to be a fixed list of 19 rates, narrowed only by "<= 120 for
    // Armor" - so a NovaStar screen could be set to 48, 72, 100, 150, 180, 192
    // or 200 Hz, none of which NovaStar publish a figure for. lookupPortCapacity
    // then INTERPOLATED between the neighbouring rows, and because capacity
    // runs as 1/fps the straight line always sits ABOVE the curve: +11% at
    // 100 Hz, +8% at 72. Overstated capacity under-counts ports, which is the
    // direction that leaves a crew short on site. Brompton was never affected -
    // its table already covers every rate offered.
    //
    // A rate with no published figure is now simply not offerable.
    updateFrameRateOptions() {
        const frameRateSelect = document.getElementById('frame-rate');
        if (!frameRateSelect || !this.currentLayer) return;

        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const currentFrameRate = this.currentLayer.frameRate || 60;

        const baseRates = [
            23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 72, 100, 120, 144, 150, 180, 192, 200, 240, 250
        ];

        const published = this.publishedFrameRates(processorType);
        // No table at all (an unknown processor) keeps every rate rather than
        // emptying the control and stranding the user.
        const allowedRates = published
            ? baseRates.filter(rate => published.has(Math.round(rate)))
            : baseRates;
        if (allowedRates.length === 0) allowedRates.push(currentFrameRate);

        frameRateSelect.innerHTML = '';
        allowedRates.forEach(rate => {
            const opt = document.createElement('option');
            opt.value = rate;
            opt.textContent = `${rate} Hz`;
            frameRateSelect.appendChild(opt);
        });

        if (allowedRates.includes(currentFrameRate)) {
            frameRateSelect.value = currentFrameRate;
            return;
        }

        // An existing project on a rate this processor does not publish - a
        // file saved before this list was narrowed, or a processor change.
        // Fall back to the highest published rate BELOW it.
        //
        // Down, not up, because this is not an approximation of the capacity
        // at the old rate - the processor cannot run that rate at all, so the
        // screen is genuinely running a slower one, and the published figure
        // for THAT rate is the true figure rather than a conservative stand-in.
        // A processor topping out at 60 asked for 72 or 120 lands on 60.
        //
        // It used to fall back to a flat 60 Hz regardless, which could jump a
        // 240 Hz screen down four rows and quadruple its pixels-per-port.
        const below = allowedRates.filter(r => r < currentFrameRate);
        const chosen = below.length ? Math.max(...below) : Math.min(...allowedRates);
        frameRateSelect.value = chosen;
        this.currentLayer.frameRate = chosen;
        // Never silent: a slower rate means MORE pixels per port and so FEWER
        // ports than the wall was planned with. The user has to see that the
        // number moved and why.
        if (typeof this._toast === 'function') {
            // Name the processor the way the user sees it in the control -
            // "NovaStar (Legacy)", not "novastar-armor".
            const procSelect = document.getElementById('processor-type');
            const procOpt = procSelect && Array.from(procSelect.options)
                .find(o => o.value === processorType);
            const procName = procOpt ? procOpt.textContent.trim() : processorType;
            this._toast(
                `${procName} has no published figure at ${currentFrameRate} Hz. `
                + `This screen is now ${chosen} Hz - check its port count.`,
                false, 7000);
        }
        if (typeof sendClientLog === 'function') {
            sendClientLog('frame_rate_snapped_to_published', {
                layerId: this.currentLayer.id,
                processorType,
                from: currentFrameRate,
                to: chosen,
                direction: below.length ? 'down' : 'lowest-published',
            });
        }
    }
    
    // Calculate port assignments for panels
    calculatePortAssignments(layer) {
        if (!layer || !Array.isArray(layer.panels)) return [];

        // v0.12: a screen group of matching panels routes as ONE BIGGER SCREEN,
        // so the walk below runs once over every member's cabinets instead of
        // once per member. `plan` is null for every ungrouped screen and every
        // group that may not cross, and then every line after this is the line
        // it always was. See getAutoRoutePlan (app-screen-info.js) for the rule.
        const plan = (typeof this.getAutoRoutePlan === 'function')
            ? this.getAutoRoutePlan(layer, 'data') : null;
        if (plan && !plan.isOwner) {
            // The wall's ports belong to the group's first member and are
            // counted there. A peer reporting its own figure as well would put
            // the same cable on the order sheet twice - the same reason a member
            // fully served by a peer's hand-drawn path reports zero.
            layer._capacityError = null;
            layer._lowLatencyDerate = null;
            layer._autoPortsRequired = 0;
            return [];
        }

        const bitDepth = layer.bitDepth || 8;
        const frameRate = layer.frameRate || 60;
        const processorType = layer.processorType || 'novastar-armor';
        const mappingMode = layer.portMappingMode || 'organized';
        const portCapacity = this.calculatePortCapacity(
            bitDepth, frameRate, processorType, !!layer.lowLatency);
        const pattern = layer.flowPattern || 'tl-h';
        const usesRectangle = this.usesRectangleConstraint(processorType);
        // v0.11.0: honour the layer's Port Mapping mode on EVERY processor.
        // Rectangle-constraint processors (NovaStar Armor) used to be forced
        // into Organized; they now support Max Capacity as well, and the
        // reserved-rectangle rule is enforced in both branches below.
        const isOrganized = mappingMode === 'organized';
        const isHorizontalFirst = pattern.includes('-h');
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        const fullPanelPixels = this.getFullPanelPixels(layer);
        // v0.11.0: NovaStar Low Latency replaces the flow pattern's row/column
        // units with a per-cabinet fill under a per-port (1 - Y/H) derate, so
        // it gets its own branch below. It is the hardware's geometry, not the
        // user's, so BOTH Port Mapping modes end up in that branch. Null for
        // every other processor and whenever low latency is off, which is what
        // keeps normal mode byte-identical.
        const llGeometry = this.getLowLatencyGeometry(layer);
        // v0.11.0: NovaStar 5G's 128 px minimum Ethernet-port load width. 0 on
        // every other processor, which makes capacityForRect below a straight
        // pass-through and leaves their traversals byte-identical. See
        // novastarMinLoadWidth / minLoadWidthPortCapacity in app-screen-info.js
        // for the published wording and for why the scope is this one key.
        //
        // ALWAYS on 5G, low latency or not: NovaStar print the note under the
        // GENERAL capacity table, not in a low latency section, so the plain
        // reading is that it is a property of the port. To narrow it to low
        // latency only, this one line becomes
        //   const minLoadWidth = llGeometry ? this.novastarMinLoadWidth(processorType) : 0;
        const minLoadWidth = this.novastarMinLoadWidth(processorType);

        layer._capacityError = null;
        layer._lowLatencyDerate = null;
        layer._autoPortsRequired = 0;
        if (portCapacity <= 0 || fullPanelPixels <= 0) return [];

        // The wall's grid. With no plan these ARE the layer's own grid and its
        // own panel indices, so nothing below can tell the difference; with one
        // they are the position lattice's compacted rows and columns, which is
        // the only address that means the same thing on every member.
        const gridRows = plan ? plan.rows : layer.rows;
        const gridCols = plan ? plan.columns : layer.columns;
        const rowOfPanel = plan ? (p => plan.rowOf.get(p)) : (p => p.row);
        const colOfPanel = plan ? (p => plan.colOf.get(p)) : (p => p.col);
        const layerOfPanel = plan
            ? (() => {
                const owners = new Map();
                plan.ordered.forEach(c => owners.set(c.panel, c.layer));
                return p => owners.get(p) || layer;
            })()
            : (() => layer);
        const orderedByPattern = includeHidden => (plan
            ? plan.ordered
                .filter(c => includeHidden || !c.panel.hidden)
                .map(c => c.panel)
            : this.getOrderedPanelsByPattern(layer, pattern, includeHidden));

        const orderedForCapacity = orderedByPattern(usesRectangle);
        if (orderedForCapacity.length === 0) return [];

        const ports = [];

        // Rectangle-constraint processors (NovaStar Armor / 1G) reserve the
        // pixel rectangle that encloses every visible cabinet in the port, so
        // a port's load is that rect's area rather than a pixel sum. Shared by
        // the Max Capacity and Low Latency branches below.
        const panelRect = (panel) => {
            const x1 = Number(panel.x) || 0;
            const y1 = Number(panel.y) || 0;
            return {
                minX: x1,
                minY: y1,
                maxX: x1 + (Number(panel.width) || 0),
                maxY: y1 + (Number(panel.height) || 0),
                count: 1
            };
        };
        const unionRect = (rect, panel) => {
            if (rect.count === 0) return panelRect(panel);
            const r = panelRect(panel);
            return {
                minX: Math.min(rect.minX, r.minX),
                minY: Math.min(rect.minY, r.minY),
                maxX: Math.max(rect.maxX, r.maxX),
                maxY: Math.max(rect.maxY, r.maxY),
                count: rect.count + 1
            };
        };
        const rectArea = (rect) => (rect.count === 0 ? 0 : (rect.maxX - rect.minX) * (rect.maxY - rect.minY));
        const emptyRect = () => ({ minX: 0, minY: 0, maxX: 0, maxY: 0, count: 0 });

        // v0.11.0: `base` less the NovaStar 5G narrow-port penalty, measured
        // from the bounding box of the port's VISIBLE cabinets - the port's own
        // load width and load height. A no-op wherever minLoadWidth is 0, i.e.
        // everywhere but 5G, so the other processors never see this at all.
        // Note this is separate bookkeeping from the Armor `rect`: Armor uses
        // its rectangle to measure LOAD, 5G uses its box to measure the LIMIT.
        const capacityForRect = (base, rect) => ((minLoadWidth > 0 && rect && rect.count > 0)
            ? this.minLoadWidthPortCapacity(
                base, processorType, rect.maxX - rect.minX, rect.maxY - rect.minY)
            : base);

        if (llGeometry) {
            // v0.11.0: NovaStar Low Latency.
            //   - there is NO port-width cap. NovaStar answered us directly:
            //     the 512 px single-port loading width printed in the NovaPro
            //     UHD Jr, MCTRL4K and MCTRL660 Pro manuals has been REMOVED in
            //     current firmware and those manuals are wrong and are being
            //     revised. Do not re-add the cap from the manual text;
            //   - what low latency does require, on EVERY NovaStar product,
            //     legacy and COEX alike (llGeometry.yDerate is now true for
            //     all three), is top alignment and the vertical cabinet
            //     formula: ports load as vertical runs of cabinets starting at
            //     the top of the canvas, and a port whose topmost cabinet sits
            //     at Y keeps only (1 - Y / canvasHeight) of the table figure.
            //     A top-aligned port - Y = 0, which is what a correctly built
            //     layout gives - costs nothing; the derate IS the price of a
            //     port that starts lower down;
            //   - the traversal stays the USER'S flow pattern, run over the
            //     whole screen exactly as normal mode runs it. With the width
            //     cap gone a port is bounded by capacity and by that derate and
            //     by nothing else, so there is no band sub-grid left to walk:
            //     all eight patterns order the cabinets here the same way they
            //     do without low latency. A vertical-first pattern keeps every
            //     port on the top row and pays nothing; a horizontal-first one
            //     starts its later ports further down and is derated for it,
            //     which is the vertical-loading requirement pricing itself in
            //     rather than the app overriding the user's choice.
            // Load accounting is unchanged per processor: Armor still pays for
            // its reserved rectangle, the COEX entries still pay a pixel sum.
            const canvasHeight = llGeometry.yDerate ? this.getLayerCanvasHeight(layer) : 0;
            if (llGeometry.yDerate && !(canvasHeight > 0)) {
                // No canvas height means no honest derate. Run at factor 1 and
                // say why once per layer - a guessed H would silently move the
                // port count, and dividing by 0 would poison every capacity.
                this._llNoCanvasHeightLogged = this._llNoCanvasHeightLogged || new Set();
                if (!this._llNoCanvasHeightLogged.has(layer.id)) {
                    this._llNoCanvasHeightLogged.add(layer.id);
                    sendClientLog('low_latency_no_canvas_height', {
                        layerId: layer.id, canvasId: layer.canvas_id || null, processorType
                    });
                }
            }
            // Capacity of a port whose topmost visible cabinet sits at `minY`.
            const capacityAtY = (minY) => (llGeometry.yDerate
                ? this.lowLatencyPortCapacity(portCapacity, minY, canvasHeight)
                : portCapacity);
            // v0.11.0: the limit a port is actually judged against. ORDER OF
            // OPERATIONS: the table value, then the (1 - Y/H) derate, THEN the
            // 5G narrow-port penalty subtracted from what is left. Doing it the
            // other way round - penalty first, derate second - would scale the
            // penalty by (1 - Y/H) and land on a different, larger capacity, so
            // this ordering is a decision and not an accident.
            const portLimit = (minY, bounds) => capacityForRect(capacityAtY(minY), bounds);
            const raiseCapacityError = (unitType, unitCount) => {
                layer._capacityError = {
                    isHorizontalFirst,
                    cols: gridCols,
                    rows: gridRows,
                    panelsPerPort: Math.floor(portCapacity / fullPanelPixels),
                    portCapacity,
                    panelPixels: fullPanelPixels,
                    unitType,
                    unitCount
                };
            };

            // The cabinets in the layer's own flow order - the SAME walk normal
            // mode uses, over the whole screen. Zero-area and hidden cabinets
            // drop out so a port's load is only what actually lights up.
            const llPanels = orderedByPattern(false)
                .filter(p => this.getPanelPixelArea(p) > 0);
            if (llPanels.length === 0) return [];

            let current = null;
            llPanels.forEach(panel => {
                if (layer._capacityError) return;
                const area = this.getPanelPixelArea(panel);
                const y = Number(panel.y) || 0;
                const soloRect = usesRectangle ? panelRect(panel) : null;
                const soloLoad = usesRectangle ? rectArea(soloRect) : area;
                const soloBounds = minLoadWidth > 0 ? panelRect(panel) : null;
                if (current) {
                    // Adding a cabinet can only pull the port's top edge
                    // UP, so re-derate against the candidate Y.
                    const candMinY = Math.min(current.minY, y);
                    const candRect = usesRectangle ? unionRect(current.rect, panel) : null;
                    const candLoad = usesRectangle ? rectArea(candRect) : (current.load + area);
                    // v0.11.0: on 5G the LIMIT moves as well as the load - a
                    // cabinet that widens the port shrinks the narrow-port
                    // penalty (or removes it), one that only makes the port
                    // taller deepens it. So the limit is re-evaluated against
                    // the CANDIDATE box, not the running one. This cannot
                    // oscillate: the walk is a single forward pass that
                    // consumes one cabinet per iteration and never revisits a
                    // port it has closed, and a cabinet that fails the solo
                    // test below raises a hard error instead of being retried.
                    const candBounds = minLoadWidth > 0 ? unionRect(current.bounds, panel) : null;
                    if (candLoad <= portLimit(candMinY, candBounds)) {
                        current.panels.push(panel);
                        current.load = candLoad;
                        current.minY = candMinY;
                        current.rect = candRect;
                        current.bounds = candBounds;
                        return;
                    }
                    ports.push(current);
                    current = null;
                }
                // Only now, opening a fresh port, is a lone cabinet judged
                // at its OWN Y - which is the Y that port would start at.
                // Testing this BEFORE trying the running port would fail a
                // cabinet low on the canvas that fits perfectly well on a
                // port opened higher up. Reaching here means it cannot be
                // placed at all, so it is a hard error the same as in the
                // Organized and Max Capacity branches, not a bad map.
                if (soloLoad > portLimit(y, soloBounds)) {
                    raiseCapacityError('panel', 1);
                    return;
                }
                current = {
                    panels: [panel], load: soloLoad, minY: y,
                    rect: soloRect, bounds: soloBounds
                };
            });
            if (current && !layer._capacityError) ports.push(current);

            if (layer._capacityError) return [];

            // Record the derate so the UI can explain a port count that moved
            // because the screen sits lower on the canvas, not because of a bug.
            if (llGeometry.yDerate && canvasHeight > 0) {
                const derated = ports.filter(p => p.minY > 0);
                if (derated.length > 0) {
                    layer._lowLatencyDerate = {
                        deratedPorts: derated.length,
                        totalPorts: ports.length,
                        canvasHeight,
                        worstCapacity: Math.min(...derated.map(p => capacityAtY(p.minY))),
                        portCapacity
                    };
                }
            }
        } else if (isOrganized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(gridRows).keys()].map(i => (startsTop ? i : (gridRows - 1 - i)))
                : [...Array(gridCols).keys()].map(i => (startsLeft ? i : (gridCols - 1 - i)));

            // Rectangle-constraint processors (NovaStar Armor / 1G) reserve a
            // pixel rectangle that encloses every visible cabinet in the port.
            // We compute that rect from each panel's actual x/y/width/height
            // (so half-tiles contribute their reduced footprint instead of the
            // full cell). See calcBoundingRectLoad below.
            const calcBoundingRectLoad = (unitIdxList) => {
                if (!usesRectangle) {
                    // Non-rectangle processors: sum actual pixel areas
                    return unitIdxList.reduce((total, idx) => {
                        const panels = orderedForCapacity.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                        return total + panels.reduce((sum, p) => sum + this.getPanelPixelArea(p), 0);
                    }, 0);
                }
                // Rectangle constraint (NovaStar Armor / 1G): the processor reserves
                // a pixel rectangle that encloses every visible cabinet in the port.
                // Compute that bounding rect from each panel's actual x/y/width/height
                // so half-tiles correctly contribute their reduced footprint instead
                // of the full cabinet cell.
                let minX = Infinity, maxX = -Infinity;
                let minY = Infinity, maxY = -Infinity;
                let hasVisible = false;
                unitIdxList.forEach(idx => {
                    const visible = orderedForCapacity.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx) && !p.hidden);
                    visible.forEach(p => {
                        hasVisible = true;
                        const x1 = Number(p.x) || 0;
                        const y1 = Number(p.y) || 0;
                        const x2 = x1 + (Number(p.width) || 0);
                        const y2 = y1 + (Number(p.height) || 0);
                        if (x1 < minX) minX = x1;
                        if (y1 < minY) minY = y1;
                        if (x2 > maxX) maxX = x2;
                        if (y2 > maxY) maxY = y2;
                    });
                });
                if (!hasVisible) return 0;
                return (maxX - minX) * (maxY - minY);
            };

            // v0.11.0: bounding box of the VISIBLE cabinets in a unit list -
            // the port's load width and load height for the NovaStar 5G
            // narrow-port penalty. Built only when that penalty is live, so
            // every other processor keeps its old single-figure limit.
            const capacityForUnits = (unitIdxList) => {
                if (!(minLoadWidth > 0)) return portCapacity;
                let bounds = emptyRect();
                unitIdxList.forEach(idx => {
                    orderedForCapacity
                        .filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx) && !p.hidden)
                        .forEach(p => { bounds = unionRect(bounds, p); });
                });
                return capacityForRect(portCapacity, bounds);
            };

            let current = { unitIndices: [], load: 0 };

            unitIndices.forEach(unitIdx => {
                const unitPanelsAll = orderedForCapacity.filter(p => (isHorizontalFirst ? rowOfPanel(p) === unitIdx : colOfPanel(p) === unitIdx));
                if (unitPanelsAll.length === 0) return;
                // Skip rows/columns with no visible panels
                const visibleInUnit = unitPanelsAll.filter(p => !p.hidden);
                if (visibleInUnit.length === 0) return;

                // Check if this single unit exceeds port capacity. For
                // rectangle-constraint processors, use the pixel-extent of the
                // visible panels in the unit (so half-tiles count as half).
                const singleUnitLoad = usesRectangle
                    ? (() => {
                        const visible = unitPanelsAll.filter(p => !p.hidden);
                        if (visible.length === 0) return 0;
                        let mnX = Infinity, mxX = -Infinity, mnY = Infinity, mxY = -Infinity;
                        visible.forEach(p => {
                            const x1 = Number(p.x) || 0, y1 = Number(p.y) || 0;
                            const x2 = x1 + (Number(p.width) || 0);
                            const y2 = y1 + (Number(p.height) || 0);
                            if (x1 < mnX) mnX = x1; if (y1 < mnY) mnY = y1;
                            if (x2 > mxX) mxX = x2; if (y2 > mxY) mxY = y2;
                        });
                        return (mxX - mnX) * (mxY - mnY);
                    })()
                    : unitPanelsAll.reduce((sum, p) => sum + this.getPanelPixelArea(p), 0);
                // v0.11.0: judged against the capacity THIS unit has - on 5G a
                // single narrow column is penalised in its own right, so the
                // unpenalised table figure would let an over-filled unit past.
                if (singleUnitLoad > capacityForUnits([unitIdx])) {
                    layer._capacityError = {
                        isHorizontalFirst,
                        cols: gridCols,
                        rows: gridRows,
                        panelsPerPort: Math.floor(portCapacity / fullPanelPixels),
                        portCapacity,
                        panelPixels: fullPanelPixels,
                        unitType: isHorizontalFirst ? 'row' : 'column',
                        unitCount: isHorizontalFirst ? gridCols : gridRows
                    };
                    return;
                }

                // Calculate what the bounding rect load would be if we add this unit
                const candidateIndices = [...current.unitIndices, unitIdx];
                const candidateLoad = calcBoundingRectLoad(candidateIndices);

                // v0.11.0: adding a unit moves the 5G limit as well as the
                // load - a second column widens the port and can lift the
                // narrow-port penalty, another row deepens it - so the limit is
                // re-read for the CANDIDATE set. Every other processor gets
                // plain portCapacity back out of capacityForUnits.
                if (current.unitIndices.length > 0 && candidateLoad > capacityForUnits(candidateIndices)) {
                    // Adding this unit would exceed capacity, start new port
                    current.load = calcBoundingRectLoad(current.unitIndices);
                    ports.push(current);
                    current = { unitIndices: [unitIdx], load: singleUnitLoad };
                } else {
                    current.unitIndices.push(unitIdx);
                    current.load = candidateLoad;
                }
            });

            if (layer._capacityError) return [];
            if (current.load > 0 || current.unitIndices.length > 0) ports.push(current);
        } else if (usesRectangle) {
            // v0.11.0: Max Capacity for rectangle-constraint processors
            // (NovaStar Armor). The port's load is the pixel RECTANGLE the
            // processor reserves around every visible cabinet in the port, not
            // a plain pixel sum, so we carry a running bounding rect and grow
            // it one cabinet at a time. A plain sum would under-count the
            // reserved area and emit a map that over-fills the port.
            //
            // Hidden/blank cabinets: the traversal includes them here (line
            // above passes includeHidden = usesRectangle) because they sit
            // physically inside the reserved rectangle. They are skipped
            // outright -- never added to the port's panel list, and never
            // allowed to expand the rect on their own. A hidden cabinet that
            // falls geometrically INSIDE the rect of the visible cabinets is
            // already paid for by that rect, which is the real hardware
            // behavior; adding its area separately would double-count it.
            // panelRect / unionRect / rectArea are hoisted above the branch
            // chain - the Low Latency branch needs the same rectangle rule.
            let current = { panels: [], load: 0 };
            let currentRect = { minX: 0, minY: 0, maxX: 0, maxY: 0, count: 0 };

            orderedForCapacity.forEach(panel => {
                if (layer._capacityError) return;
                if (panel.hidden) return;
                const panelLoad = this.getPanelPixelArea(panel);
                if (panelLoad <= 0) return;

                // One cabinet that cannot fit in an empty port is a hard
                // error, not a port we can split further. Surface it the same
                // way the Organized branch does instead of looping forever or
                // silently emitting an over-filled map.
                const soloLoad = rectArea(panelRect(panel));
                if (soloLoad > portCapacity) {
                    layer._capacityError = {
                        isHorizontalFirst,
                        cols: gridCols,
                        rows: gridRows,
                        panelsPerPort: Math.floor(portCapacity / fullPanelPixels),
                        portCapacity,
                        panelPixels: fullPanelPixels,
                        unitType: 'panel',
                        unitCount: 1
                    };
                    return;
                }

                const candidateRect = unionRect(currentRect, panel);
                const candidateLoad = rectArea(candidateRect);

                if (current.panels.length > 0 && candidateLoad > portCapacity) {
                    // Adding this cabinet would push the reserved rectangle
                    // past the port limit, close the port and start a new one.
                    current.load = rectArea(currentRect);
                    ports.push(current);
                    currentRect = panelRect(panel);
                    current = { panels: [panel], load: soloLoad };
                } else {
                    current.panels.push(panel);
                    currentRect = candidateRect;
                    current.load = candidateLoad;
                }
            });

            if (layer._capacityError) return [];
            if (current.panels.length > 0) ports.push(current);
        } else {
            let current = { panels: [], load: 0 };
            // v0.11.0: the port's bounding box, carried alongside the running
            // pixel sum purely so the NovaStar 5G narrow-port penalty can read
            // the port's load width and height. Stays null on every other
            // processor and capacityForRect then hands back portCapacity, so
            // this branch is byte-identical for them.
            let currentBounds = minLoadWidth > 0 ? emptyRect() : null;
            orderedForCapacity.forEach(panel => {
                if (layer._capacityError) return;
                const panelLoad = this.getPanelPixelArea(panel);
                if (panelLoad <= 0) return;
                // Adding a cabinet can widen the port and shrink the penalty,
                // or only heighten it and deepen the penalty, so the limit is
                // re-read for the candidate box. One forward pass, one cabinet
                // per iteration: it cannot oscillate.
                const candidateBounds = currentBounds ? unionRect(currentBounds, panel) : null;
                if (current.load > 0
                        && current.load + panelLoad > capacityForRect(portCapacity, candidateBounds)) {
                    ports.push(current);
                    current = { panels: [], load: 0 };
                    currentBounds = minLoadWidth > 0 ? emptyRect() : null;
                }
                // A cabinet the penalty leaves no room for even on an empty
                // port cannot be split any further, so raise the same hard
                // error the other branches do rather than emit an over-filled
                // map. Scoped to the 5G penalty: without it a lone oversized
                // cabinet behaved this way before and still does.
                if (minLoadWidth > 0 && current.load === 0
                        && panelLoad > capacityForRect(portCapacity, panelRect(panel))) {
                    layer._capacityError = {
                        isHorizontalFirst,
                        cols: gridCols,
                        rows: gridRows,
                        panelsPerPort: Math.floor(portCapacity / fullPanelPixels),
                        portCapacity,
                        panelPixels: fullPanelPixels,
                        unitType: 'panel',
                        unitCount: 1
                    };
                    return;
                }
                if (!panel.hidden) current.panels.push(panel);
                if (currentBounds) currentBounds = unionRect(currentBounds, panel);
                current.load += panelLoad;
            });
            if (layer._capacityError) return [];
            if (current.load > 0 || current.panels.length > 0) ports.push(current);
        }

        const assignments = [];
        layer._autoPortsRequired = ports.length;
        ports.forEach((port, idx) => {
            // v0.11.0: only the Organized branch stores row/column indices;
            // the Low Latency branch carries its own ordered panel list.
            const portPanels = (isOrganized && !llGeometry)
                ? this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, port.unitIndices || [], false, plan)
                : (port.panels || []);
            let pixelIndex = 0;
            portPanels.forEach((panel, panelIdx) => {
                const item = {
                    panel,
                    port: idx + 1,
                    isPortStart: panelIdx === 0,
                    pixelIndex
                };
                // Which SCREEN this cabinet is on, and ONLY on a crossing group
                // - the item shape of every ungrouped screen is untouched. It is
                // the id rather than the layer because an assignment list is
                // read, logged and compared all over the app, and it is the only
                // way the renderer can put a crossing port's arrow on the peer's
                // cabinet instead of the owner's at the same row and column.
                if (plan) item.layerId = layerOfPanel(panel).id;
                assignments.push(item);
                pixelIndex += this.getPanelPixelArea(panel);
            });
        });
        return assignments;
    }
    
    // Update export filename preview
    updateExportPreview() {
        const projectName = document.getElementById('export-name').value.trim() || 'Project';
        const format = document.getElementById('export-format').value;
        
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();
        
        const views = [];
        if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
        if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
        if (document.getElementById('export-show-look') && document.getElementById('export-show-look').checked) views.push('show-look');
        if (document.getElementById('export-data-flow').checked) views.push('data-flow');
        if (document.getElementById('export-power').checked) views.push('power');

        const preview = document.getElementById('export-preview');

        // Hide view checkboxes for Resolume XML (geometry only, no rendered views)
        const viewSection = document.getElementById('export-views-section');
        if (viewSection) {
            const geometryOnly = (format === 'resolume-xml');
            viewSection.style.display = geometryOnly ? 'none' : '';
        }

        if (format === 'resolume-xml') {
            // v0.11.0: the preview keeps .value-accent. It is the only thing in
            // its box and the accent reads as HIGHLIGHT there, unlike
            // Pixels/Port and Panels/Port, which share a box with error
            // colours and so use .value-normal. Error colours stay inline.
            preview.classList.add('value-accent');
            preview.style.color = '';
            preview.textContent = `${projectName}.xml`;
            return;
        }

        if (views.length === 0) {
            preview.textContent = '(Select at least one view)';
            preview.classList.remove('value-accent');
            preview.style.color = '#ff6b6b';
            return;
        }

        preview.classList.add('value-accent');
        preview.style.color = '';

        // Slice 11: factor selected canvases into the preview. Each
        // (canvas, view) combo is one file (PNG/PSD) or one page (PDF).
        const canvasIds = (typeof this.getSelectedExportCanvasIds === 'function')
            ? this.getSelectedExportCanvasIds() : [null];
        if (canvasIds.length === 0) {
            preview.textContent = '(Select at least one canvas)';
            preview.classList.remove('value-accent');
            preview.style.color = '#ff6b6b';
            return;
        }
        const projectCanvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        // v0.8.7.5: per-canvas Name inputs in the export modal are
        // prefilled with the canvas's stored name and the user can edit
        // them in place (same pattern as the view-suffix inputs). The
        // value is filename-only, the canvas's stored name in the
        // sidebar / project is untouched. Empty falls back to canvas.name.
        const nameByCid = {};
        document.querySelectorAll('.export-canvas-name-override').forEach(inp => {
            const cid = inp.dataset.canvasId;
            const v = (inp.value || '').trim();
            if (cid && v) nameByCid[cid] = v;
        });
        const canvasNameOf = (cid) => {
            if (!cid) return '';
            const c = projectCanvases.find(x => x && x.id === cid);
            const raw = nameByCid[cid] || (c && c.name) || 'Canvas';
            return this.sanitizeFilename(raw);
        };
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;
        const buildName = (cid, suffix, ext) => {
            const cname = canvasNameOf(cid);
            return (multiCanvas && cname)
                ? `${projectName}_${suffix}_${cname}.${ext}`
                : `${projectName}_${suffix}.${ext}`;
        };

        // v0.8.7.1: read per-canvas perspective dropdowns so the filename
        // preview reflects the user's modal override, not the underlying
        // canvas state. Build a synthetic canvas object per cid with the
        // override applied for the suffix calculation.
        const overrideByCid = {};
        document.querySelectorAll('.export-canvas-perspective').forEach(sel => {
            const cid = sel.dataset.canvasId;
            const kind = sel.dataset.kind;
            if (!cid || !kind) return;
            if (!overrideByCid[cid]) overrideByCid[cid] = {};
            const key = kind === 'data' ? 'data_flow_perspective' : 'power_perspective';
            overrideByCid[cid][key] = (sel.value === 'back') ? 'back' : 'front';
        });
        const canvasForSuffix = (cid) => {
            if (!cid) return null;
            const c = (this.project && this.project.canvases || []).find(x => x && x.id === cid);
            if (!c) return null;
            return Object.assign({}, c, overrideByCid[cid] || {});
        };

        if (format === 'pdf') {
            const pageCount = canvasIds.length * views.length;
            preview.textContent = `${projectName}.pdf (${pageCount} page${pageCount > 1 ? 's' : ''})`;
        } else if (format === 'psd' || format === 'png') {
            const ext = format;
            const lines = [];
            for (const cid of canvasIds) {
                const cForSuffix = canvasForSuffix(cid);
                for (const v of views) {
                    const suffix = this.getExportSuffixForView(v, suffixes, viewNames, cForSuffix);
                    lines.push(buildName(cid, suffix, ext));
                }
            }
            if (lines.length === 1) preview.textContent = lines[0];
            else preview.innerHTML = lines.join('<br>');
        }
    }

    getExportViewNames() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    getExportSuffixDefaults() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    loadExportSuffixesToUI() {
        const defaults = this.getExportSuffixDefaults();
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('exportSuffixes') || '{}');
        } catch (e) {
            saved = {};
        }
        const apply = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return;
            const val = typeof saved[key] === 'string' ? saved[key] : defaults[key];
            el.value = val || '';
        };
        apply('export-suffix-pixel-map', 'pixel-map');
        apply('export-suffix-cabinet-id', 'cabinet-id');
        apply('export-suffix-show-look', 'show-look');
        apply('export-suffix-data-flow', 'data-flow');
        apply('export-suffix-power', 'power');
    }

    saveExportSuffixesFromUI() {
        const suffixes = this.getExportSuffixesFromUI();
        localStorage.setItem('exportSuffixes', JSON.stringify(suffixes));
    }

    getExportSuffixesFromUI() {
        const defaults = this.getExportSuffixDefaults();
        const read = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return defaults[key];
            return (el.value || '').trim();
        };
        return {
            'pixel-map': read('export-suffix-pixel-map', 'pixel-map'),
            'cabinet-id': read('export-suffix-cabinet-id', 'cabinet-id'),
            'show-look': read('export-suffix-show-look', 'show-look'),
            'data-flow': read('export-suffix-data-flow', 'data-flow'),
            'power': read('export-suffix-power', 'power')
        };
    }

    getExportSuffixForView(view, suffixes, viewNames, canvas) {
        const raw = (suffixes && typeof suffixes[view] === 'string') ? suffixes[view].trim() : '';
        let suffix = raw || viewNames[view];
        // v0.8.6: perspective is per-canvas. When exporting a specific
        // canvas, read THAT canvas's perspective (not the project-root
        // legacy field). For legacy single-canvas projects (canvas=null)
        // fall back to the project root field.
        const perspectiveKey = view === 'data-flow' ? 'data_flow_perspective'
            : view === 'power' ? 'power_perspective'
            : null;
        if (perspectiveKey) {
            const value = canvas
                ? canvas[perspectiveKey]
                : (this.project && this.project[perspectiveKey]);
            if (value === 'back' && !/_back$/i.test(suffix)) {
                suffix = `${suffix}_back`;
            }
        }
        return suffix;
    }
    
    // Export Resolume Arena Advanced Output XML
    async exportResolumeXml(projectName) {
        const rasterW = parseInt(document.getElementById('toolbar-raster-width').value) || 3840;
        const rasterH = parseInt(document.getElementById('toolbar-raster-height').value) || 2160;

        const response = await fetch('/api/export/resolume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                raster_width: rasterW,
                raster_height: rasterH
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Resolume export failed');
        }
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.xml`, 'application/xml');
        sendClientLog('export_resolume_complete', { projectName, rasterW, rasterH });
    }

    /**
     * Open and fully initialize the export modal.
     *
     * All export entry points route through this method so the toolbar and
     * File menu cannot drift apart as modal options evolve.
     */
    openExportModal(format = null) {
        const modal = document.getElementById('export-modal');
        if (!modal) return;

        const formatSelect = document.getElementById('export-format');
        if (formatSelect && format) {
            formatSelect.value = format;
        }

        modal.style.display = 'block';
        document.getElementById('export-name').value =
            this.project.name || 'Untitled Project';
        this.loadExportSuffixesToUI();
        this.populateExportCanvasesList();

        // Re-evaluate format-specific controls such as the PSD scale row.
        if (formatSelect) {
            formatSelect.dispatchEvent(new Event('change'));
        }
        this.updateExportPreview();
    }

    // Perform export using client-side canvas capture at 1:1 pixel scale
    /**
     * Slice 11: build the dynamic Canvases checklist in the export modal.
     * Visible canvases are checked, hidden ones unchecked but still
     * selectable. Each row gets a stable id so the export-confirm handler
     * can read them.
     */
    populateExportCanvasesList() {
        const list = document.getElementById('export-canvases-list');
        if (!list) return;
        list.innerHTML = '';
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) {
            // Legacy / pre-Slice-1 project: no canvas list. Show a static
            // placeholder so the user understands what's being exported.
            const note = document.createElement('div');
            note.style.cssText = 'font-size:11px;color:#888;padding:6px 0;';
            note.textContent = 'Single-canvas project, entire workspace will be exported.';
            list.appendChild(note);
            return;
        }
        canvases.forEach((c, idx) => {
            if (!c || !c.id) return;
            const row = document.createElement('div');
            row.className = 'export-view-row';
            const isHidden = c.visible === false;
            // v0.8.7.5: col-1 of the row holds checkbox + swatch + an
            // editable canvas-name input (replacing the previous static
            // name span). Editing the input changes the canvas segment
            // in the exported filename only, the canvas's stored name
            // in the sidebar / project file is untouched. Using a div
            // (not a label) so clicking the input doesn't toggle the
            // checkbox.
            const labelCol = document.createElement('div');
            labelCol.className = 'export-view-label';
            labelCol.style.gap = '6px';
            const swatch = document.createElement('span');
            swatch.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:2px;background:${c.color || '#4A90E2'};flex:none;`;
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = !isHidden;
            checkbox.dataset.canvasId = c.id;
            checkbox.className = 'export-canvas-checkbox';
            checkbox.addEventListener('change', () => this.updateExportPreview());
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'export-canvas-name-override';
            nameInput.dataset.canvasId = c.id;
            nameInput.value = c.name || `Canvas ${idx + 1}`;
            nameInput.title = 'Edit to rename this canvas in the exported filename. Does NOT rename the canvas in the project.';
            // Inline override so the input stays compact inside the
            // 140px label column and doesn't pick up the chunky 8px
            // padding from `.export-view-row input[type="text"]`.
            nameInput.style.cssText = `flex:1;min-width:60px;padding:2px 6px;font-size:12px;background:#222;color:${isHidden ? '#888' : '#ddd'};border:1px solid #444;border-radius:3px;`;
            nameInput.addEventListener('input', () => this.updateExportPreview());
            labelCol.appendChild(checkbox);
            labelCol.appendChild(swatch);
            labelCol.appendChild(nameInput);
            if (isHidden) {
                const hiddenTag = document.createElement('span');
                hiddenTag.textContent = '(hidden)';
                hiddenTag.style.cssText = 'color:#888;font-size:11px;flex:none;';
                labelCol.appendChild(hiddenTag);
            }
            row.appendChild(labelCol);
            // v0.8.6: per-canvas perspective overrides for Data + Power
            // exports. Default to whatever the canvas currently has.
            // These dropdowns set/restore the canvas's perspective during
            // export only, they don't persist back to the project.
            const persp = document.createElement('div');
            persp.style.cssText = 'display:flex;gap:8px;margin-left:22px;font-size:11px;color:#aaa;align-items:center;';
            const mkSel = (kind, current) => {
                const wrap = document.createElement('span');
                wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
                const lbl = document.createElement('span');
                lbl.textContent = kind === 'data' ? 'Data:' : 'Power:';
                const sel = document.createElement('select');
                sel.className = `export-canvas-perspective export-canvas-perspective-${kind}`;
                sel.dataset.canvasId = c.id;
                sel.dataset.kind = kind;
                sel.style.cssText = 'background:#222;color:#ddd;border:1px solid #444;border-radius:3px;padding:1px 4px;font-size:11px;';
                ['front', 'back'].forEach(v => {
                    const o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === 'front' ? 'Front' : 'Back';
                    if (v === current) o.selected = true;
                    sel.appendChild(o);
                });
                // v0.8.7.1: refresh filename preview when this dropdown
                // changes so the user sees _back / no-suffix instantly.
                sel.addEventListener('change', () => this.updateExportPreview());
                wrap.appendChild(lbl);
                wrap.appendChild(sel);
                return wrap;
            };
            const curData = (c.data_flow_perspective === 'back') ? 'back' : 'front';
            const curPower = (c.power_perspective === 'back') ? 'back' : 'front';
            persp.appendChild(mkSel('data', curData));
            persp.appendChild(mkSel('power', curPower));
            row.appendChild(persp);
            list.appendChild(row);
        });
    }

    /**
     * Slice 11: read the canvas checkboxes back. Returns array of canvas
     * ids in their project.canvases order. Returns [null] for legacy
     * projects so performExport falls into single-canvas mode.
     */
    getSelectedExportCanvasIds() {
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) return [null];
        const checked = new Set();
        document.querySelectorAll('.export-canvas-checkbox').forEach(cb => {
            if (cb.checked && cb.dataset.canvasId) checked.add(cb.dataset.canvasId);
        });
        // Preserve project.canvases order in the output.
        return canvases.filter(c => c && checked.has(c.id)).map(c => c.id);
    }

    /**
     * Slice 11: multi-canvas-aware export. Iterates canvases × views,
     * temporarily hiding the OTHER canvases per pass and translating the
     * render so each canvas becomes its own export image at its native
     * raster size. canvasIds=[null] is the legacy single-canvas path.
     */
    async performExport(projectName, format, views, canvasIds) {
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();

        // Store current renderer state.
        const originalViewMode = window.canvasRenderer.viewMode;
        const originalZoom = window.canvasRenderer.zoom;
        const originalPanX = window.canvasRenderer.panX;
        const originalPanY = window.canvasRenderer.panY;
        const originalActiveCanvasId = (this.project && this.project.active_canvas_id) || null;
        const mainCanvas = window.canvasRenderer.canvas;
        const originalCtx = window.canvasRenderer.ctx;

        const transparentBg = document.getElementById('export-transparent-bg');
        const useTransparentBg = transparentBg && transparentBg.checked;

        // Snapshot every canvas's visibility so we can flip them per pass
        // and restore at the end. Legacy projects skip this entirely.
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        const visibilitySnapshot = canvases.map(c => ({ id: c.id, visible: c.visible }));
        // v0.8.6: snapshot every canvas's perspective so we can apply the
        // export-dialog overrides per pass and restore at the end. Read
        // the per-canvas perspective dropdowns once up-front.
        const perspectiveSnapshot = canvases.map(c => ({
            id: c.id,
            data_flow_perspective: c.data_flow_perspective,
            power_perspective: c.power_perspective,
        }));
        const perspectiveOverrides = {};
        document.querySelectorAll('.export-canvas-perspective').forEach(sel => {
            const cid = sel.dataset.canvasId;
            const kind = sel.dataset.kind;
            if (!cid || !kind) return;
            if (!perspectiveOverrides[cid]) perspectiveOverrides[cid] = {};
            const key = kind === 'data' ? 'data_flow_perspective' : 'power_perspective';
            perspectiveOverrides[cid][key] = (sel.value === 'back') ? 'back' : 'front';
        });
        // Apply overrides to every canvas BEFORE the per-canvas/per-view
        // loop so each render call sees the user's chosen perspective.
        canvases.forEach(c => {
            const o = perspectiveOverrides[c.id];
            if (!o) return;
            if (o.data_flow_perspective) c.data_flow_perspective = o.data_flow_perspective;
            if (o.power_perspective) c.power_perspective = o.power_perspective;
        });
        // v0.8.7.5: per-canvas Name inputs from the export modal. Each is
        // prefilled with the canvas's stored name and the user can edit
        // in place. Filename-only, never written back to the canvas
        // object. Empty entries fall back to canvas.name below.
        const nameOverridesByCid = {};
        document.querySelectorAll('.export-canvas-name-override').forEach(inp => {
            const cid = inp.dataset.canvasId;
            const v = (inp.value || '').trim();
            if (cid && v) nameOverridesByCid[cid] = v;
        });

        const exportCanvas = document.createElement('canvas');
        const exportCtx = exportCanvas.getContext('2d', { alpha: useTransparentBg });
        window.canvasRenderer.canvas = exportCanvas;
        window.canvasRenderer.ctx = exportCtx;
        // v0.8.7: optional resolution-scale multiplier (PSD only). Native
        // scale = 1 (existing behavior for PNG/PDF). Higher values render
        // PSD at scale × native raster so vector content (panels, labels,
        // arrows, text) stays crisp at higher zoom. PNG/PDF
        // skip the scale (their use cases don't benefit and the larger
        // file sizes would surprise users).
        // The actual scale used is clamped per pass to keep PSD dimensions
        // under PSD format's 30000×30000 hard limit (PSB is bigger but
        // pytoshop only writes classic PSD). Computed inside the loop.
        const scaleSel = document.getElementById('export-scale');
        const requestedScale = scaleSel ? Math.max(1, Math.min(8, Number(scaleSel.value) || 1)) : 1;
        // v0.8.7: PSD format max dimension is 30000px, but browsers cap
        // 2D canvas at much lower (Chrome: 16384, Safari/FF higher). The
        // toDataURL on an oversized canvas silently returns "data:," and
        // the server can't parse the empty image. Use 16000 to stay
        // within Chrome's hard cap with a safety margin.
        const PSD_MAX_DIM = 16000;
        let scaleClampedAnywhere = false;
        window.canvasRenderer.exportMode = true;
        window.canvasRenderer.exportTransparentBg = useTransparentBg;

        const renderedItems = [];
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;

        try {
            for (const cid of canvasIds) {
                // Resolve target canvas. cid===null means legacy single-
                // canvas: use project-root raster fields, no workspace shift.
                const targetCanvas = cid
                    ? canvases.find(c => c && c.id === cid)
                    : null;
                if (cid && !targetCanvas) continue;

                if (cid) {
                    // Make ONLY this canvas visible during the per-view loop
                    // so other canvases' layers don't bleed into the export
                    // (handles overlap, cross-canvas labels, etc.). Active
                    // canvas swap drives the rasterWidth/Height accessors
                    // that decide export-canvas dimensions per view.
                    canvases.forEach(c => { c.visible = (c.id === cid); });
                    this.project.active_canvas_id = cid;
                }

                for (const view of views) {
                    window.canvasRenderer.viewMode = view;
                    // rasterWidth/Height read from the active canvas (Slice 6)
                    // and pick show_raster_* automatically when view is
                    // show-look (so Show Look exports at its own resolution).
                    const rasterWidth = window.canvasRenderer.rasterWidth || 1920;
                    const rasterHeight = window.canvasRenderer.rasterHeight || 1080;
                    // v0.8.7: per-pass PSD scale, clamped so the resulting
                    // image dimensions stay under PSD's 30000×30000 hard
                    // limit. PNG/PDF always run at 1x. If the user picked
                    // 8x but the canvas is too big, we silently use the
                    // largest scale that fits and surface a single status
                    // message after the export completes.
                    let exportScale = (format === 'psd') ? requestedScale : 1;
                    if (exportScale > 1) {
                        const maxScaleByWidth = Math.floor(PSD_MAX_DIM / rasterWidth);
                        const maxScaleByHeight = Math.floor(PSD_MAX_DIM / rasterHeight);
                        const maxSafe = Math.max(1, Math.min(maxScaleByWidth, maxScaleByHeight));
                        if (exportScale > maxSafe) {
                            exportScale = maxSafe;
                            scaleClampedAnywhere = true;
                        }
                    }
                    window.canvasRenderer.zoom = exportScale;
                    exportCanvas.width = rasterWidth * exportScale;
                    exportCanvas.height = rasterHeight * exportScale;
                    // Translate the workspace so this canvas's top-left
                    // (workspace_x, workspace_y) lands at (0, 0) in the
                    // export canvas. Legacy: pan to 0,0.
                    // v0.8.5.3 fix: Show Look / Data / Power views render
                    // each canvas at its show_workspace_x/y (when set) -
                    // the export pan must match or the captured PNG comes
                    // out shifted and missing layers that live at
                    // negative-relative show positions.
                    const isShowExport = (view === 'show-look' || view === 'data-flow' || view === 'power');
                    let wsx = 0, wsy = 0;
                    if (targetCanvas) {
                        if (isShowExport) {
                            wsx = (targetCanvas.show_workspace_x == null
                                ? (targetCanvas.workspace_x || 0)
                                : (targetCanvas.show_workspace_x || 0));
                            wsy = (targetCanvas.show_workspace_y == null
                                ? (targetCanvas.workspace_y || 0)
                                : (targetCanvas.show_workspace_y || 0));
                        } else {
                            wsx = targetCanvas.workspace_x || 0;
                            wsy = targetCanvas.workspace_y || 0;
                        }
                    }
                    // v0.8.7: panX/panY are in screen pixels. With zoom =
                    // exportScale the workspace origin needs to land at
                    // -wsx*scale screen pixels for the canvas's top-left
                    // to render at (0, 0) of the export image.
                    window.canvasRenderer.panX = -wsx * exportScale;
                    window.canvasRenderer.panY = -wsy * exportScale;

                    window.canvasRenderer.render();

                    const dataUrl = exportCanvas.toDataURL('image/png');
                    const suffix = this.getExportSuffixForView(view, suffixes, viewNames, targetCanvas);
                    // v0.8.7.5: per-canvas Name input from the export modal
                    // takes precedence over targetCanvas.name when present.
                    // Empty / whitespace = fall back to canvas name.
                    const overrideRaw = nameOverridesByCid[cid];
                    const canvasName = targetCanvas
                        ? this.sanitizeFilename(overrideRaw || targetCanvas.name || 'Canvas')
                        : null;
                    // Filename: include canvas token only when exporting
                    // more than one canvas (v0.8.7.4). Single-canvas
                    // exports keep `Project_View.ext`; the Name input on
                    // a single-canvas export only matters if you happen
                    // to also have a hidden sibling canvas selected.
                    const fileBase = (multiCanvas && canvasName)
                        ? `${projectName}_${suffix}_${canvasName}`
                        : `${projectName}_${suffix}`;
                    // PDF page label includes canvas + view when multi.
                    const pdfLabel = (multiCanvas && canvasName)
                        ? `${canvasName}, ${suffix}`
                        : suffix;
                    renderedItems.push({
                        canvasId: cid,
                        canvasName,
                        view,
                        suffix,
                        fileBase,
                        pdfLabel,
                        dataUrl,
                        width: rasterWidth * exportScale,
                        height: rasterHeight * exportScale,
                        scale: exportScale,
                    });
                }
            }
        } finally {
            // Restore canvas visibility, perspective, active canvas, renderer state.
            visibilitySnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (c) c.visible = s.visible;
            });
            perspectiveSnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (!c) return;
                c.data_flow_perspective = s.data_flow_perspective;
                c.power_perspective = s.power_perspective;
            });
            if (this.project) this.project.active_canvas_id = originalActiveCanvasId;
            window.canvasRenderer.canvas = mainCanvas;
            window.canvasRenderer.ctx = originalCtx;
            window.canvasRenderer.exportMode = false;
            window.canvasRenderer.exportTransparentBg = false;
            window.canvasRenderer.viewMode = originalViewMode;
            window.canvasRenderer.zoom = originalZoom;
            window.canvasRenderer.panX = originalPanX;
            window.canvasRenderer.panY = originalPanY;
            window.canvasRenderer.render();
        }

        // v0.8.7: notify the user if any pass had to clamp the requested
        // PSD scale to fit PSD's 30000×30000 dimension limit. We don't
        // block, we just report the actual scale used so the file lands
        // and the user knows.
        if (scaleClampedAnywhere) {
            const usedScales = [...new Set(renderedItems.map(i => i.scale))].sort((a, b) => a - b);
            const status = document.getElementById('status-message');
            if (status) {
                status.textContent = `PSD scale reduced (max ${usedScales[usedScales.length - 1]}x), PSD format max is 30000px`;
                setTimeout(() => { if (status.textContent.startsWith('PSD scale')) status.textContent = 'Ready'; }, 6000);
            }
            sendClientLog && sendClientLog('export_psd_scale_clamped', {
                requested: requestedScale,
                used: usedScales,
            });
        }

        // Dispatch to format-specific writer. Multi-canvas just means
        // more items, each writer already loops over them.
        if (format === 'png') {
            await this.downloadRenderedPNGs(renderedItems);
        } else if (format === 'pdf') {
            await this.downloadAsPdf(projectName, renderedItems);
        } else if (format === 'psd') {
            await this.downloadAsPsd(projectName, renderedItems);
        }
    }
    
    dataUrlToBlob(dataUrl) {
        const [meta, base64] = dataUrl.split(',');
        const contentType = meta.split(':')[1].split(';')[0];
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        return new Blob([new Uint8Array(byteNumbers)], { type: contentType });
    }

    downloadBlob(blob, filename) {
        const link = document.createElement('a');
        link.download = filename;
        link.href = URL.createObjectURL(blob);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = (e) => reject(e);
            reader.readAsDataURL(blob);
        });
    }

    // Returns { path, cancelled, unavailable } - the same contract as
    // nativeSelectDirectory, and for the same reason.
    //
    // This used to return a bare path-or-null, and the caller read null as
    // "the user cancelled" and stopped. That was survivable while the host at
    // a LAN address was misclassified as remote, because the native path was
    // skipped entirely and the file still arrived as a browser download.
    // Once that misclassification was fixed, the same null began meaning
    // "the dialog could not open" - and a failed dialog silently ABANDONED
    // the export. No file anywhere, no message. Worse than the bug it
    // replaced. Cancel must stop; unavailable must fall back.
    async nativeSelectSavePath(suggestedName) {
        let data = null;
        try {
            const response = await fetch('/api/native-dialog/save-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ suggested_name: suggestedName })
            });
            if (!response.ok) return { path: null, cancelled: false, unavailable: true };
            data = await response.json();
        } catch (err) {
            return { path: null, cancelled: false, unavailable: true };
        }
        if (data && data.ok && data.path) {
            return { path: data.path, cancelled: false, unavailable: false };
        }
        return {
            path: null,
            cancelled: !!(data && data.cancelled),
            unavailable: !(data && data.cancelled),
        };
    }


    // Only the HOST is warned about a missing folder chooser.
    //
    // On the host, a chooser is what should happen, so failing to get one is a
    // real fault and the reason is worth surfacing. On a machine connected
    // over the network, a plain download IS the expected behaviour - the files
    // land on that machine, which is the point - so a warning there would be
    // crying wolf about something working as intended.
    //
    // (Browsers only expose folder access over a SECURE connection, so a
    // remote client on plain http:// could not be given a chooser anyway.)
    _noFolderChooserMessage() {
        if (!this.isLocalConnection()) return null;
        return 'Could not open the folder chooser, so the files were saved to '
            + 'your browser\'s downloads folder instead. The reason is in '
            + 'Help > Show Logs.';
    }

    // Returns { path, cancelled, unavailable }.
    //
    // The two failure modes MUST stay apart. `cancelled` means the user
    // dismissed the folder chooser and nothing should be written;
    // `unavailable` means the dialog could not be opened at all and the
    // browser download is the only way to get the files out. They used to
    // collapse into a bare null, so pressing Cancel on an export still dumped
    // every file into Downloads.
    async nativeSelectDirectory() {
        let data = null;
        try {
            const response = await fetch('/api/native-dialog/select-directory', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            if (!response.ok) return { path: null, cancelled: false, unavailable: true };
            data = await response.json();
        } catch (err) {
            return { path: null, cancelled: false, unavailable: true };
        }
        if (data && data.ok && data.path) {
            return { path: data.path, cancelled: false, unavailable: false };
        }
        return {
            path: null,
            cancelled: !!(data && data.cancelled),
            // Anything that is not an explicit cancel is treated as the dialog
            // being unavailable, so an unexpected shape still yields files.
            unavailable: !(data && data.cancelled),
        };
    }

    async nativeWriteFile(path, blob) {
        // v0.8.7: send the blob as raw multipart bytes instead of a base64
        // data URI. The old JSON path JSON.stringify-ed a ~36MB base64
        // string for a 26MB PSD, which blows up to "out of memory" or
        // sends an empty body on some browsers (we saw `has_data: false`
        // in server logs for 8x PSD exports). FormData streams the blob
        // directly without a giant string allocation.
        const fd = new FormData();
        fd.append('path', path);
        fd.append('file', blob);
        const response = await fetch('/api/native-dialog/write-file', {
            method: 'POST',
            body: fd,
        });
        if (!response.ok) return false;
        const data = await response.json();
        return !!(data && data.ok);
    }

    // Is this browser running ON the machine hosting the app?
    //
    // The hostname alone cannot answer that. When the launcher binds the
    // server to a network interface so the drawing can be opened from another
    // machine, the HOST's own browser also reaches it at that LAN address -
    // and http://192.168.2.5:8050 looks exactly the same whether it is this
    // machine or a laptop across the room. Judging by hostname concluded
    // "remote", so Export skipped the folder chooser and dropped the files
    // into the browser's downloads folder with no way to choose where.
    //
    // Only the server can tell, by comparing the caller's address to its own,
    // so ask it once and remember the answer.
    isLocalConnection() {
        if (this._isHostClient !== undefined && this._isHostClient !== null) {
            return this._isHostClient;
        }
        // Not probed yet: fall back to the address test, which is right
        // whenever the app is opened at localhost (the usual case).
        const host = window.location.hostname;
        return host === 'localhost' || host === '127.0.0.1' || host === '::1';
    }

    // Memoised probe. Safe to call on every export; only the first one
    // reaches the server.
    async ensureHostCapability() {
        if (this._hostCapabilityProbe) return this._hostCapabilityProbe;
        this._hostCapabilityProbe = (async () => {
            try {
                const r = await fetch('/api/native-dialog/available');
                // 403 is the server saying "you are not this machine" - a real
                // answer, not a failure.
                this._isHostClient = r.ok;
            } catch (err) {
                // Server unreachable: leave it unknown so isLocalConnection
                // falls back to the address test rather than locking the host
                // out of its own dialogs - and DROP the memo, so the next
                // export asks again. Caching a transient network blip would
                // reinstate the original bug for the rest of the session with
                // no way to recover short of a reload.
                this._isHostClient = null;
                this._hostCapabilityProbe = null;
            }
            sendClientLog('host_capability_probe', {
                isHost: this._isHostClient,
                hostname: window.location.hostname,
            });
            return this._isHostClient;
        })();
        return this._hostCapabilityProbe;
    }

    browserDownload(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        sendClientLog('save_blob_browser_download', { filename });
    }

    async saveBlobWithPicker(blobOrFn, filename, mimeType) {
        await this.ensureHostCapability();
        // Sanitize so a project name with "/" or other illegal chars doesn't
        // get rejected by showSaveFilePicker / OS file APIs.
        filename = this.sanitizeFilename(filename);
        // blobOrFn can be a Blob OR an async function returning one. Lazy-blob
        // form lets the caller defer expensive serialization (e.g. stringifying
        // a 1MB project) until AFTER showSaveFilePicker resolves, keeping the
        // user-activation gesture fresh for createWritable. See bug fix for
        // 0-byte JSON saves on large multi-canvas projects.
        const resolveBlob = async () => (typeof blobOrFn === 'function' ? await blobOrFn() : blobOrFn);
        // 1. Try the File System Access API (Chrome/Edge on secure contexts).
        //    Skip on localhost, we have a better server-side native dialog
        //    available that doesn't break on cloud-synced folders (Nextcloud,
        //    iCloud, Dropbox, OneDrive). Chrome's createWritable rejects with
        //    NotAllowedError when the target lives under a sync agent's xattrs,
        //    which produced 0-byte saves before this guard.
        if (window.showSaveFilePicker && !this.isLocalConnection()) {
            try {
                sendClientLog('save_blob_picker_start', { filename, mimeType });
                const ext = filename.split('.').pop() || '';
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'File', accept: { [mimeType]: [`.${ext}`] } }]
                });
                const blob = await resolveBlob();
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                sendClientLog('save_blob_picker_success', { filename });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                // NotAllowedError on createWritable: Chrome already created the
                // empty file via the picker but lost the user-activation needed
                // to write to it. Fall through to native/browser fallback so we
                // don't leave the user with a 0-byte file and nothing else.
                sendClientLog('save_blob_picker_failed', {
                    filename,
                    name: err && err.name,
                    message: err && err.message
                });
                // Try native dialog (Mac/Win/Linux), opens a fresh dialog so
                // we get our own gesture-bound path. If unavailable, use
                // browserDownload as last resort.
            }
        }
        // 2. Use native server-side dialog (opens on the host machine).
        // ONLY when this client IS the host: a remote client's save must land
        // on the remote machine (browser download below), not on the server.
        try {
            if (!this.isLocalConnection()) throw new Error('remote client: skip host dialog');
            const picked = await this.nativeSelectSavePath(filename);
            if (picked.cancelled) {
                // The user said no. Stop - saving anyway ignores them.
                sendClientLog('save_blob_native_dialog_cancelled', { filename });
                if (typeof this._toast === 'function') {
                    this._toast('Export cancelled - nothing was saved.', false, 4000);
                }
                return;
            }
            const savePath = picked.path;
            if (!savePath) {
                // Dialog could not open. Fall through to the browser download
                // rather than lose the export.
                sendClientLog('save_blob_native_dialog_unavailable', { filename });
                throw new Error('native dialog unavailable');
            }
            sendClientLog('save_blob_native_dialog_selected', { filename, savePath });
            const blob = await resolveBlob();
            const ok = await this.nativeWriteFile(savePath, blob);
            if (ok) {
                sendClientLog('save_blob_native_dialog_success', { filename, savePath });
                return;
            }
            sendClientLog('save_blob_native_dialog_write_failed', { filename, savePath });
        } catch (err) {
            sendClientLog('save_blob_native_dialog_error', { filename, message: err.message });
        }
        // 3. Last resort: trigger a normal browser download so the user always
        // ends up with a file (even if both the picker and the native dialog
        // failed). Better than silently leaving a 0-byte stub on disk.
        try {
            const blob = await resolveBlob();
            this.browserDownload(blob, filename);
        } catch (err) {
            sendClientLog('save_blob_browser_download_error', { filename, message: err && err.message });
        }
    }

    sanitizeFilename(name) {
        // Strip path separators and characters Windows/macOS reject in filenames.
        // Also collapse leading/trailing dots & whitespace which Windows rejects.
        if (!name) return 'untitled';
        const cleaned = String(name)
            .replace(/[\\/:*?"<>|\x00-\x1F]/g, '_')
            .replace(/^[\s.]+|[\s.]+$/g, '')
            .trim();
        return cleaned || 'untitled';
    }

    async saveMultipleFiles(files) {
        // Ask the server whether we are the host BEFORE deciding how to save.
        await this.ensureHostCapability();
        // Sanitize each filename so path separators (e.g. "/" in a project name)
        // don't break getFileHandle() with "Name is not allowed."
        files = files.map(f => ({ ...f, filename: this.sanitizeFilename(f.filename) }));
        sendClientLog('save_multiple_files_start', {
            count: files.length,
            hasDirectoryPicker: !!window.showDirectoryPicker,
            hasSaveFilePicker: !!window.showSaveFilePicker
        });
        // v0.8: same Chrome activation issue we hit on JSON saves, when
        // the user is on localhost (this Flask app), the multi-canvas export
        // burns the user-gesture token rendering all the canvases between
        // showDirectoryPicker resolving and the per-file getFileHandle/
        // createWritable calls. Chrome rejects with NotAllowedError and we
        // get zero files on disk. Skip the FS Access API entirely on
        // localhost and use the native server-side directory dialog, which
        // doesn't have this restriction.
        if (window.showDirectoryPicker && !this.isLocalConnection()) {
            try {
                const dirHandle = await window.showDirectoryPicker();
                for (const file of files) {
                    const handle = await dirHandle.getFileHandle(file.filename, { create: true });
                    const writable = await handle.createWritable();
                    await writable.write(file.blob);
                    await writable.close();
                }
                sendClientLog('save_multiple_files_directory_success', { count: files.length });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                sendClientLog('save_multiple_files_directory_failed', {
                    name: err && err.name, message: err && err.message
                });
                // fall through to native fallback so the user still gets files
            }
        }
        // Use native server-side directory picker (opens on the host machine).
        // Tried BEFORE per-file showSaveFilePicker because picking once is
        // far less work than N separate save dialogs. ONLY when this client
        // IS the host: a remote client's files must land on the remote
        // machine (per-file download below), not on the server.
        try {
            if (!this.isLocalConnection()) throw new Error('remote client: skip host dialog');
            const picked = await this.nativeSelectDirectory();
            if (picked.cancelled) {
                // The user said no. Saving to Downloads anyway is not a
                // fallback, it is ignoring them.
                sendClientLog('save_multiple_files_cancelled_by_user', { count: files.length });
                if (typeof this._toast === 'function') {
                    this._toast('Export cancelled - nothing was saved.', false, 4000);
                }
                return;
            }
            const targetDir = picked.path;
            if (targetDir) {
                for (const file of files) {
                    const filePath = `${targetDir.replace(/[\\/]$/, '')}/${file.filename}`;
                    const ok = await this.nativeWriteFile(filePath, file.blob);
                    if (!ok) {
                        sendClientLog('save_multiple_files_native_dialog_write_failed', { file: file.filename, filePath });
                        throw new Error(`Native write failed for ${file.filename}`);
                    }
                }
                sendClientLog('save_multiple_files_native_dialog_success', { count: files.length, directory: targetDir });
                return;
            }
            sendClientLog('save_multiple_files_native_dialog_unavailable', { count: files.length });
        } catch (err) {
            sendClientLog('save_multiple_files_native_dialog_error', { message: err.message });
        }
        // Last resort: per-file saveBlobWithPicker (multiple dialogs) or
        // browser download.
        //
        // Say so. Falling back silently is what made this look broken: the
        // folder chooser never appeared, the files landed in Downloads, and
        // nothing on screen connected the two. The reason itself is in the
        // app log (Help > Show Logs) under native_dialog_command_failed.
        const noChooserMsg = this._noFolderChooserMessage();
        if (noChooserMsg && typeof this._toast === 'function') {
            this._toast(noChooserMsg, true, 9000);
        }
        if (window.showSaveFilePicker) {
            for (const file of files) {
                const mimeType = file.blob && file.blob.type ? file.blob.type : 'application/octet-stream';
                await this.saveBlobWithPicker(file.blob, file.filename, mimeType);
            }
            sendClientLog('save_multiple_files_picker_success', { count: files.length });
            return;
        }
        for (const file of files) {
            try { this.browserDownload(file.blob, file.filename); } catch (_) {}
        }
    }

    async downloadRenderedPNGs(renderedViews) {
        if (renderedViews.length === 1) {
            const blob = this.dataUrlToBlob(renderedViews[0].dataUrl);
            await this.saveBlobWithPicker(blob, `${renderedViews[0].fileBase}.png`, 'image/png');
            return;
        }
        const files = renderedViews.map(v => ({
            filename: `${v.fileBase}.png`,
            blob: this.dataUrlToBlob(v.dataUrl)
        }));
        await this.saveMultipleFiles(files);
    }
    
    async downloadAsPdf(projectName, renderedViews) {
        // Slice 11: multi-canvas PDF. Each rendered item contributes one
        // page; the per-page name uses canvas + view when multi-canvas
        // (set on renderedItem.pdfLabel by performExport), else just the
        // view suffix. Server already handles variable per-page sizes.
        const response = await fetch('/api/export/pdf-from-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                images: renderedViews.map(v => ({
                    name: v.pdfLabel || v.suffix,
                    data: v.dataUrl,
                    width: v.width || window.canvasRenderer.rasterWidth,
                    height: v.height || window.canvasRenderer.rasterHeight
                })),
                width: window.canvasRenderer.rasterWidth,
                height: window.canvasRenderer.rasterHeight
            })
        });

        if (!response.ok) throw new Error('Failed to create PDF');

        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.pdf`, 'application/pdf');
    }
    
    async downloadAsPsd(projectName, renderedViews) {
        const files = [];
        for (const view of renderedViews) {
            // Slice 11: when exporting per-canvas, only include layers from
            // that canvas in the PSD layer list, otherwise the PSD reports
            // sibling canvases' layers as if they were in this image.
            // Legacy / single-canvas: include every layer (canvasId is null).
            // v0.8.6.3: the rendered item stores the view string in
            // `view.view` (set by performExport), NOT `view.viewMode`. The
            // old isShowView check read the wrong field and was always
            // false, so PSD layer metadata always grouped by Pixel Map
            // canvas_id even for Show Look / Data / Power exports.
            const isShowView = view.view === 'show-look'
                || view.view === 'data-flow' || view.view === 'power';
            const psdLayers = this.project.layers.filter(l => {
                if (!view.canvasId) return true;
                // Show Look / Data / Power exports use the layer's
                // effective show canvas (show_canvas_id || canvas_id) so a
                // layer reassigned in Show Look exports under its show
                // canvas's PSD instead of its Pixel Map canvas's.
                const cid = (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
                return cid === view.canvasId;
            }).map(l => {
                const b = this.getLayerBounds(l);
                let x1 = b.x1, y1 = b.y1, x2 = b.x2, y2 = b.y2;
                // v0.8.6.3: in Show Look the rendered image places each
                // layer at panel + (showOffset - layer.offset). PSD layer
                // metadata must reflect that shift so layer rectangles in
                // the resulting PSD line up with the pixels.
                if (isShowView) {
                    const procX = Number(l.offset_x) || 0;
                    const procY = Number(l.offset_y) || 0;
                    const showX = (l.showOffsetX != null) ? Number(l.showOffsetX) : procX;
                    const showY = (l.showOffsetY != null) ? Number(l.showOffsetY) : procY;
                    const dx = showX - procX;
                    const dy = showY - procY;
                    x1 += dx; x2 += dx;
                    y1 += dy; y2 += dy;
                }
                // v0.8.7: when PSD export is rendered at scale > 1, the
                // image is scale × native; layer rectangles must scale to
                // match or they'll cover only the top-left corner.
                const s = Number(view.scale) || 1;
                if (s !== 1) {
                    x1 *= s; x2 *= s; y1 *= s; y2 *= s;
                }
                return {
                    name: l.name,
                    offset_x: x1,
                    offset_y: y1,
                    width: x2 - x1,
                    height: y2 - y1,
                    visible: l.visible
                };
            });
            const response = await fetch('/api/export/psd-from-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_name: projectName,
                    view_name: view.suffix,
                    image_data: view.dataUrl,
                    width: view.width || window.canvasRenderer.rasterWidth,
                    height: view.height || window.canvasRenderer.rasterHeight,
                    layers: psdLayers
                })
            });
            if (!response.ok) {
                // v0.8.7: surface the server error so the user sees what
                // actually went wrong (e.g. PSD dimension limits, OOM)
                // instead of a generic message.
                let detail = '';
                try {
                    const j = await response.clone().json();
                    if (j && j.error) detail = `: ${j.error}`;
                } catch (_) {}
                throw new Error(`Failed to create PSD${detail}`);
            }
            const blob = await response.blob();
            files.push({ filename: `${view.fileBase}.psd`, blob });
        }
        if (files.length === 1) {
            await this.saveBlobWithPicker(files[0].blob, files[0].filename, 'application/octet-stream');
            return;
        }
        await this.saveMultipleFiles(files);
    }

    getPreferencesDefaults() {
        return {
            rasterWidth: 1920,
            rasterHeight: 1080,
            columns: 8,
            rows: 5,
            panelWidth: 128,
            panelHeight: 128,
            panelWidthMM: 500,
            panelHeightMM: 500,
            panelWeight: 20,
            weightUnit: 'kg',
            cabinetFontSize: 30,
            labelFontSize: 30,
            dataLabelSize: 30,
            powerLabelSize: 14,
            color1: '#404680',
            color2: '#959CB8',
            borderColor: '#FFFFFF',
            flowPattern: 'tl-h',
            powerFlowPattern: 'tl-h',
            dataLineWidth: 6,
            powerLineWidth: 8,
            processorType: 'novastar-armor',
            lowLatency: false,
            bitDepth: 8,
            frameRate: 60,
            powerVoltage: 110,
            powerAmperage: 15,
            powerWatts: 200,
            canvasGap: 0,
            // Project-wide canvas font. Applies to every label drawn on the
            // canvas (screen names, cabinet IDs, info bars, port/circuit
            // labels, etc.). The picker is populated from the fonts installed
            // on the machine running the app.
            font: 'Arial'
        };
    }

    getLocalPreferences() {
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('appPreferences') || '{}');
        } catch (e) {
            saved = {};
        }
        return saved;
    }

    getPreferences() {
        const defaults = this.getPreferencesDefaults();
        // Server preferences take priority (shared across all clients),
        // fall back to localStorage for backwards compatibility
        const saved = (this._serverPreferences && Object.keys(this._serverPreferences).length > 0)
            ? this._serverPreferences
            : this.getLocalPreferences();
        return { ...defaults, ...saved };
    }

    supportsFilePickerAPIs() {
        return !!window.showSaveFilePicker;
    }

    supportsDirectoryPickerAPIs() {
        return !!window.showDirectoryPicker;
    }

    getFlowPatternSvg(pattern) {
        const svgs = {
            'tl-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="4" r="3" fill="#00cc00"/><path d="M 4 4 L 28 4 L 28 16 L 4 16 L 4 28 L 22 28" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,28 22,24 22,32" fill="#cc0000"/></svg>',
            'tl-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="4" r="3" fill="#00cc00"/><path d="M 4 4 L 4 28 L 16 28 L 16 4 L 28 4 L 28 22" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,28 24,22 32,22" fill="#cc0000"/></svg>',
            'tr-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="4" r="3" fill="#00cc00"/><path d="M 28 4 L 4 4 L 4 16 L 28 16 L 28 28 L 10 28" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,28 10,24 10,32" fill="#cc0000"/></svg>',
            'tr-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="4" r="3" fill="#00cc00"/><path d="M 28 4 L 28 28 L 16 28 L 16 4 L 4 4 L 4 22" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,28 0,22 8,22" fill="#cc0000"/></svg>',
            'bl-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="28" r="3" fill="#00cc00"/><path d="M 4 28 L 28 28 L 28 16 L 4 16 L 4 4 L 22 4" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,4 22,0 22,8" fill="#cc0000"/></svg>',
            'bl-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="28" r="3" fill="#00cc00"/><path d="M 4 28 L 4 4 L 16 4 L 16 28 L 28 28 L 28 10" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,4 24,10 32,10" fill="#cc0000"/></svg>',
            'br-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="28" r="3" fill="#00cc00"/><path d="M 28 28 L 4 28 L 4 16 L 28 16 L 28 4 L 10 4" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,4 10,0 10,8" fill="#cc0000"/></svg>',
            'br-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="28" r="3" fill="#00cc00"/><path d="M 28 28 L 28 4 L 16 4 L 16 28 L 4 28 L 4 10" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,4 0,10 8,10" fill="#cc0000"/></svg>'
        };
        return svgs[pattern] || svgs['tl-h'];
    }

    renderPreferencePatternButtons(containerId, buttonClass) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (container.children.length > 0) return;
        const patterns = ['tl-h', 'tl-v', 'tr-h', 'tr-v', 'bl-h', 'bl-v', 'br-h', 'br-v'];
        patterns.forEach(pattern => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `pref-flow-pattern-btn ${buttonClass}`;
            btn.setAttribute('data-pattern', pattern);
            btn.innerHTML = this.getFlowPatternSvg(pattern);
            container.appendChild(btn);
        });
    }

    setupPreferences() {
        this.renderPreferencePatternButtons('pref-data-flow-pattern-grid', 'pref-data-flow-pattern-btn');
        this.renderPreferencePatternButtons('pref-power-flow-pattern-grid', 'pref-power-flow-pattern-btn');
        const saveBtn = document.getElementById('preferences-save');
        const cancelBtn = document.getElementById('preferences-cancel');
        const resetBtn = document.getElementById('preferences-reset');
        const modal = document.getElementById('preferences-modal');
        const modalContent = modal ? modal.querySelector('.modal-content') : null;
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const voltageCustom = document.getElementById('pref-power-voltage-custom');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const amperageCustom = document.getElementById('pref-power-amperage-custom');
        const prefDataPatternButtons = document.querySelectorAll('.pref-data-flow-pattern-btn');
        const prefPowerPatternButtons = document.querySelectorAll('.pref-power-flow-pattern-btn');
        let prefsBackdropDown = false;

        const syncVoltageCustom = () => {
            if (!voltageSelect || !voltageCustom) return;
            if (voltageSelect.value === 'custom') {
                voltageCustom.style.display = 'inline-block';
            } else {
                voltageCustom.style.display = 'none';
                voltageCustom.value = voltageSelect.value;
            }
        };
        const syncAmperageCustom = () => {
            if (!amperageSelect || !amperageCustom) return;
            if (amperageSelect.value === 'custom') {
                amperageCustom.style.display = 'inline-block';
            } else {
                amperageCustom.style.display = 'none';
                amperageCustom.value = amperageSelect.value;
            }
        };

        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const prefs = this.readPreferencesFromUI();
                localStorage.setItem('appPreferences', JSON.stringify(prefs));
                // Save to server so all clients share the same preferences
                this._serverPreferences = prefs;
                fetch('/api/preferences', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(prefs)
                });
                sendClientLog('preferences_saved', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0,
                    appliesToCurrentProject: !!(this.project && this.project.name === 'Untitled Project' && this.project.layers && this.project.layers.length === 1)
                });
                // Preferences are defaults for future/new projects.
                // Only apply to the current project when it is the startup default untitled project.
                this.applyPreferencesToDefaultLayerIfMatch(false);
                this.saveClientSideProperties();
                // v0.8.8.x: font change is project-wide and affects every
                // on-canvas label, repaint so the new font shows immediately.
                if (window.canvasRenderer) window.canvasRenderer.render();
                modal.style.display = 'none';
            });
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                const defaults = this.getPreferencesDefaults();
                localStorage.setItem('appPreferences', JSON.stringify(defaults));
                // Sync reset to server
                this._serverPreferences = defaults;
                fetch('/api/preferences', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(defaults)
                });
                sendClientLog('preferences_reset', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0,
                    appliesToCurrentProject: !!(this.project && this.project.name === 'Untitled Project' && this.project.layers && this.project.layers.length === 1)
                });
                this.openPreferencesModal();
                this.applyPreferencesToDefaultLayerIfMatch(false);
            });
        }
        if (modal) {
            modal.addEventListener('mousedown', (e) => {
                prefsBackdropDown = (e.target === modal);
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal && prefsBackdropDown) {
                    modal.style.display = 'none';
                }
                prefsBackdropDown = false;
            });
        }
        if (modalContent) {
            modalContent.addEventListener('mousedown', () => {
                prefsBackdropDown = false;
            });
            modalContent.addEventListener('click', (e) => e.stopPropagation());
        }
        if (voltageSelect) {
            voltageSelect.addEventListener('change', syncVoltageCustom);
        }
        if (amperageSelect) {
            amperageSelect.addEventListener('change', syncAmperageCustom);
        }
        prefDataPatternButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                prefDataPatternButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
        prefPowerPatternButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                prefPowerPatternButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
        syncVoltageCustom();
        syncAmperageCustom();
    }

    openPreferencesModal() {
        const prefs = this.getPreferences();
        const setVal = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value;
        };
        setVal('pref-raster-width', prefs.rasterWidth);
        setVal('pref-raster-height', prefs.rasterHeight);
        setVal('pref-columns', prefs.columns);
        setVal('pref-rows', prefs.rows);
        setVal('pref-panel-width', prefs.panelWidth);
        setVal('pref-panel-height', prefs.panelHeight);
        setVal('pref-panel-width-mm', prefs.panelWidthMM);
        setVal('pref-panel-height-mm', prefs.panelHeightMM);
        setVal('pref-panel-weight', prefs.panelWeight);
        setVal('pref-weight-unit', prefs.weightUnit || 'kg');
        setVal('pref-cabinet-font-size', prefs.cabinetFontSize);
        setVal('pref-label-font-size', prefs.labelFontSize);
        setVal('pref-data-label-size', prefs.dataLabelSize);
        setVal('pref-power-label-size', prefs.powerLabelSize);
        setVal('pref-color1', prefs.color1);
        setVal('pref-color2', prefs.color2);
        setVal('pref-border-color', prefs.borderColor);
        // Hydrate the Fonts picker, then pull in the machine's installed fonts
        // (refreshes the picker again when they arrive).
        this._refreshFontPrefsUI(prefs.font || 'Arial');
        this._loadSystemFonts();
        const prefDataPatternButtons = document.querySelectorAll('.pref-data-flow-pattern-btn');
        prefDataPatternButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-pattern') === (prefs.flowPattern || 'tl-h'));
        });
        const prefPowerPatternButtons = document.querySelectorAll('.pref-power-flow-pattern-btn');
        prefPowerPatternButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-pattern') === (prefs.powerFlowPattern || 'tl-h'));
        });
        setVal('pref-data-line-width', prefs.dataLineWidth);
        setVal('pref-power-line-width', prefs.powerLineWidth);
        setVal('pref-processor-type', prefs.processorType);
        const prefLowLatency = document.getElementById('pref-low-latency');
        if (prefLowLatency) prefLowLatency.checked = !!prefs.lowLatency;
        setVal('pref-bit-depth', prefs.bitDepth);
        setVal('pref-frame-rate', prefs.frameRate);
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const voltageCustom = document.getElementById('pref-power-voltage-custom');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const amperageCustom = document.getElementById('pref-power-amperage-custom');
        if (voltageSelect) {
            const val = String(prefs.powerVoltage);
            const option = [...voltageSelect.options].find(o => o.value === val);
            voltageSelect.value = option ? val : 'custom';
        }
        if (voltageCustom) {
            voltageCustom.value = prefs.powerVoltage;
            voltageCustom.style.display = (!voltageSelect || voltageSelect.value === 'custom') ? 'inline-block' : 'none';
        }
        if (amperageSelect) {
            const val = String(prefs.powerAmperage);
            const option = [...amperageSelect.options].find(o => o.value === val);
            amperageSelect.value = option ? val : 'custom';
        }
        if (amperageCustom) {
            amperageCustom.value = prefs.powerAmperage;
            amperageCustom.style.display = (!amperageSelect || amperageSelect.value === 'custom') ? 'inline-block' : 'none';
        }
        setVal('pref-power-watts', prefs.powerWatts);
        setVal('pref-canvas-gap', prefs.canvasGap);
        const modal = document.getElementById('preferences-modal');
        if (modal) modal.style.display = 'block';
    }

    readPreferencesFromUI() {
        const defaults = this.getPreferencesDefaults();
        const readNum = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el) return fallback;
            const val = parseFloat(el.value);
            return Number.isFinite(val) && val > 0 ? val : fallback;
        };
        const readStr = (id, fallback) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : fallback;
        };
        const readBool = (id, fallback) => {
            const el = document.getElementById(id);
            return el ? !!el.checked : fallback;
        };
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const prefDataPatternActive = document.querySelector('.pref-data-flow-pattern-btn.active');
        const prefPowerPatternActive = document.querySelector('.pref-power-flow-pattern-btn.active');
        const voltageVal = voltageSelect && voltageSelect.value !== 'custom'
            ? parseInt(voltageSelect.value, 10)
            : readNum('pref-power-voltage-custom', defaults.powerVoltage);
        const amperageVal = amperageSelect && amperageSelect.value !== 'custom'
            ? parseInt(amperageSelect.value, 10)
            : readNum('pref-power-amperage-custom', defaults.powerAmperage);
        return {
            rasterWidth: readNum('pref-raster-width', defaults.rasterWidth),
            rasterHeight: readNum('pref-raster-height', defaults.rasterHeight),
            columns: readNum('pref-columns', defaults.columns),
            rows: readNum('pref-rows', defaults.rows),
            panelWidth: readNum('pref-panel-width', defaults.panelWidth),
            panelHeight: readNum('pref-panel-height', defaults.panelHeight),
            panelWidthMM: readNum('pref-panel-width-mm', defaults.panelWidthMM),
            panelHeightMM: readNum('pref-panel-height-mm', defaults.panelHeightMM),
            panelWeight: readNum('pref-panel-weight', defaults.panelWeight),
            weightUnit: readStr('pref-weight-unit', defaults.weightUnit),
            cabinetFontSize: readNum('pref-cabinet-font-size', defaults.cabinetFontSize),
            labelFontSize: readNum('pref-label-font-size', defaults.labelFontSize),
            dataLabelSize: readNum('pref-data-label-size', defaults.dataLabelSize),
            powerLabelSize: readNum('pref-power-label-size', defaults.powerLabelSize),
            color1: readStr('pref-color1', defaults.color1),
            color2: readStr('pref-color2', defaults.color2),
            borderColor: readStr('pref-border-color', defaults.borderColor),
            flowPattern: prefDataPatternActive ? (prefDataPatternActive.getAttribute('data-pattern') || defaults.flowPattern) : defaults.flowPattern,
            powerFlowPattern: prefPowerPatternActive ? (prefPowerPatternActive.getAttribute('data-pattern') || defaults.powerFlowPattern) : defaults.powerFlowPattern,
            dataLineWidth: readNum('pref-data-line-width', defaults.dataLineWidth),
            powerLineWidth: readNum('pref-power-line-width', defaults.powerLineWidth),
            processorType: readStr('pref-processor-type', defaults.processorType),
            lowLatency: readBool('pref-low-latency', defaults.lowLatency),
            bitDepth: readNum('pref-bit-depth', defaults.bitDepth),
            frameRate: readNum('pref-frame-rate', defaults.frameRate),
            powerVoltage: Number.isFinite(voltageVal) && voltageVal > 0 ? voltageVal : defaults.powerVoltage,
            powerAmperage: Number.isFinite(amperageVal) && amperageVal > 0 ? amperageVal : defaults.powerAmperage,
            powerWatts: readNum('pref-power-watts', defaults.powerWatts),
            canvasGap: readNum('pref-canvas-gap', defaults.canvasGap),
            font: readStr('pref-font', defaults.font),
        };
    }

    // v0.8.8.x: web-safe font stack offered in the picker, plus user-added
    // custom fonts from preferences. Any font name works as a CSS font-family.
    _webSafeFonts() {
        return ['Arial', 'Helvetica', 'Verdana', 'Tahoma', 'Trebuchet MS',
            'Georgia', 'Times New Roman', 'Courier New', 'Impact', 'Monaco',
            'system-ui'];
    }
    _allFontOptions() {
        const system = Array.isArray(this._systemFonts) ? this._systemFonts : [];
        // De-dupe while preserving order: web-safe quick-picks, then installed.
        const seen = new Set();
        const out = [];
        [...this._webSafeFonts(), ...system].forEach(f => {
            const name = (f || '').trim();
            if (!name || seen.has(name.toLowerCase())) return;
            seen.add(name.toLowerCase()); out.push(name);
        });
        return out;
    }

    // Fetch the list of fonts installed on the machine running the app (once).
    // The server enumerates them; the browser can render any of them in canvas.
    _loadSystemFonts() {
        if (this._systemFontsLoaded) return Promise.resolve(this._systemFonts || []);
        if (this._systemFontsPromise) return this._systemFontsPromise;
        this._systemFontsPromise = fetch('/api/system-fonts')
            .then(r => r.json())
            .then(d => {
                this._systemFonts = Array.isArray(d.fonts) ? d.fonts : [];
                this._systemFontsLoaded = true;
                // If the Preferences modal is open, refresh the picker so the
                // installed fonts appear without the user reopening it.
                const modal = document.getElementById('preferences-modal');
                if (modal && modal.style.display !== 'none') {
                    const sel = document.getElementById('pref-font');
                    this._refreshFontPrefsUI(sel ? sel.value : undefined);
                }
                return this._systemFonts;
            })
            .catch(() => { this._systemFonts = []; this._systemFontsLoaded = true; return []; });
        return this._systemFontsPromise;
    }
    // Active canvas-text font. Reads from prefs.font (one project-wide value).
    getProjectFont() {
        const prefs = this.getPreferences() || {};
        return prefs.font || 'Arial';
    }

    // Grouped options for the Preferences font picker: a few recommended
    // quick-picks, then every font installed on this machine.
    _fontOptionGroups() {
        const seen = new Set();
        const dedupe = (arr) => {
            const out = [];
            (arr || []).forEach(f => {
                const name = (f || '').trim();
                if (!name || seen.has(name.toLowerCase())) return;
                seen.add(name.toLowerCase()); out.push(name);
            });
            return out;
        };
        const web = dedupe(this._webSafeFonts());
        const system = dedupe(Array.isArray(this._systemFonts) ? this._systemFonts : []);
        return [
            { label: 'Recommended', fonts: web },
            { label: 'Installed on this computer', fonts: system },
        ].filter(g => g.fonts.length);
    }

    // Flat list of every selectable font name (used for de-dupe/validation).
    _fontOptionsForPicker() {
        return this._fontOptionGroups().reduce((acc, g) => acc.concat(g.fonts), []);
    }

    _refreshFontPrefsUI(selectedFont) {
        const sel = document.getElementById('pref-font');
        if (sel) {
            sel.innerHTML = '';
            const groups = this._fontOptionGroups();
            const opts = [];
            const want = selectedFont || sel.value || 'Arial';
            // If the saved font isn't in any group yet (e.g. installed fonts
            // still loading), surface it at the top so the value sticks.
            if (want && !groups.some(g => g.fonts.some(f => f.toLowerCase() === want.toLowerCase()))) {
                const o = document.createElement('option');
                o.value = want; o.textContent = want;
                o.style.fontFamily = `"${want}", sans-serif`;
                sel.appendChild(o); opts.push(want);
            }
            groups.forEach(g => {
                const og = document.createElement('optgroup');
                og.label = g.fonts.length > 30 ? `${g.label} (${g.fonts.length})` : g.label;
                g.fonts.forEach(name => {
                    const o = document.createElement('option');
                    o.value = name; o.textContent = name;
                    o.style.fontFamily = `"${name}", sans-serif`;
                    og.appendChild(o); opts.push(name);
                });
                sel.appendChild(og);
            });
            if (opts.some(o => o.toLowerCase() === want.toLowerCase())) sel.value = want;
        }
    }

    applyPreferencesToRaster(prefs) {
        if (!window.canvasRenderer) return;
        window.canvasRenderer.rasterWidth = prefs.rasterWidth;
        window.canvasRenderer.rasterHeight = prefs.rasterHeight;
        const widthInput = document.getElementById('toolbar-raster-width');
        const heightInput = document.getElementById('toolbar-raster-height');
        if (widthInput) widthInput.value = prefs.rasterWidth;
        if (heightInput) heightInput.value = prefs.rasterHeight;
        if (this.project) {
            this.project.raster_width = prefs.rasterWidth;
            this.project.raster_height = prefs.rasterHeight;
            this.saveProject();
        }
        this.saveRasterSize();
        window.canvasRenderer.render();
    }

    setupMenuBar() {
        const menuItems = document.querySelectorAll('#menu-bar .menu-item');
        const menus = document.querySelectorAll('.menu-dropdown');
        const hideMenus = () => {
            menus.forEach(menu => menu.style.display = 'none');
            menuItems.forEach(item => item.classList.remove('active'));
        };

        this.updateShortcutLabels();

        menuItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const menuId = `menu-${item.dataset.menu}`;
                const menu = document.getElementById(menuId);
                if (!menu) return;
                const rect = item.getBoundingClientRect();
                const isVisible = menu.style.display === 'block';
                hideMenus();
                if (!isVisible) {
                    menu.style.display = 'block';
                    menu.style.left = `${rect.left}px`;
                    menu.style.top = `${rect.bottom + 4}px`;
                    item.classList.add('active');
                }
            });
        });

        document.addEventListener('click', () => {
            hideMenus();
            this.hideContextMenu();
        });
        window.addEventListener('resize', () => {
            hideMenus();
            this.hideContextMenu();
        });

        const handleMenuClick = (e) => {
            const target = e.target.closest('.menu-option');
            if (!target) return;
            // Don't close menu when hovering over submenu parent
            if (target.classList.contains('menu-has-submenu')) return;
            // A disabled item is a sentence, not a control: it stays put so
            // its title (the reason) can be read, and clicking it neither
            // acts nor closes the menu - native menu behaviour.
            if (target.classList.contains('menu-disabled')) return;
            const action = target.dataset.action;
            if (!action) return;
            hideMenus();
            this.handleMenuAction(action);
        };
        document.querySelectorAll('.menu-dropdown').forEach(menu => {
            menu.addEventListener('click', handleMenuClick);
        });

        const contextMenu = document.getElementById('context-menu');
        if (contextMenu) {
            contextMenu.addEventListener('click', handleMenuClick);
        }

        if (!this.globalContextMenuBound) {
            const appRoot = document.getElementById('app') || document.body;
            appRoot.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e.clientX, e.clientY);
            });
            this.globalContextMenuBound = true;
        }

        // Populate recent files submenu
        this.updateRecentFilesMenu();
    }

    updateShortcutLabels() {
        const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac/.test(navigator.userAgent);
        document.querySelectorAll('.menu-option[data-label]').forEach(option => {
            // Skip options with submenus, they manage their own content
            if (option.classList.contains('menu-has-submenu')) return;
            const label = option.getAttribute('data-label') || '';
            const shortcut = isMac ? option.getAttribute('data-shortcut-mac') : option.getAttribute('data-shortcut-win');
            if (shortcut) {
                option.textContent = `${label} (${shortcut})`;
            } else {
                option.textContent = label;
            }
        });
    }

    // Move the selected layers to another canvas from the right-click menu.
    //
    // The canvas list is built when the menu opens rather than declared in the
    // template: canvases are added, renamed and deleted at runtime, so a static
    // list would go stale. Follows the same popup shape as the per-canvas
    // "+ Add" chooser so the two feel like the same control.
    //
    // Layers keep their position when they move (routes_layers.move_layer_to_
    // canvas) - canvases share a coordinate space, so a screen lands where it
    // already was rather than jumping to the corner.
    openMoveToCanvasMenu() {
        const layers = this.getSelectedLayers().filter(l => !l.locked);
        if (layers.length === 0) return;
        const canvases = (this.project && this.project.canvases) || [];
        // Where the selection already lives. With a mixed selection every
        // canvas is a real destination for something, so nothing is excluded.
        const originIds = new Set(layers.map(l => l.canvas_id));
        const targets = canvases.filter(c => !(originIds.size === 1 && originIds.has(c.id)));
        if (targets.length === 0) return;

        document.querySelectorAll('.canvas-add-popup, .canvas-menu-popup, .canvas-color-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup canvas-add-popup';
        menu.innerHTML = targets
            .map(c => `<button data-canvas-id="${c.id}">${c.name}</button>`)
            .join('');
        document.body.appendChild(menu);

        const cm = document.getElementById('context-menu');
        const r = cm ? cm.getBoundingClientRect() : { left: 100, top: 100, width: 0 };
        menu.style.position = 'fixed';
        menu.style.left = `${Math.min(r.left + Math.max(r.width, 40), window.innerWidth - 180)}px`;
        menu.style.top = `${Math.max(8, Math.min(r.top, window.innerHeight - 40 - targets.length * 28))}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const canvasId = btn.dataset.canvasId;
                close();
                // Sequential, not Promise.all: each move PUTs and the server
                // answers with the whole project, so overlapping calls would
                // race and the last response would undo the others.
                for (const layer of layers) {
                    if (layer.canvas_id === canvasId) continue;
                    await this.moveLayerToCanvas(layer.id, canvasId, 'move');
                }
                sendClientLog('move_to_canvas', { count: layers.length, canvasId });
            });
        });
    }

    handleMenuAction(action) {
        switch (action) {
            case 'new':
                this.createNewProject();
                break;
            case 'open':
                this.loadProjectFromFile();
                break;
            case 'save':
                this.saveProjectToFile();
                break;
            case 'export-png':
                this.openExportModal('png');
                break;
            case 'export-psd':
                this.openExportModal('psd');
                break;
            case 'preferences':
                this.openPreferencesModal();
                break;
            case 'undo':
                this.undo();
                break;
            case 'redo':
                this.redo();
                break;
            case 'copy':
                this.copyLayer();
                break;
            case 'paste':
                this.pasteLayer();
                break;
            case 'duplicate':
                if (this.currentLayer) this.duplicateLayer(this.currentLayer);
                break;
            case 'delete':
                if (this.currentLayer) this.deleteLayer(this.currentLayer.id);
                break;
            // v0.11.0: screen groups. showContextMenu() hides these when the
            // selection cannot take them, and each action re-checks, so a
            // keyboard-driven call can't make a group of one either.
            case 'group-screens':
                this.groupSelectedLayers();
                break;
            case 'ungroup-screens':
                this.ungroupSelectedLayers();
                break;
            case 'remove-from-group':
                this.removeSelectedFromGroup();
                break;
            case 'center-x':
                this.centerLayersOnCanvas('x');
                break;
            case 'center-y':
                this.centerLayersOnCanvas('y');
                break;
            case 'center-both':
                this.centerLayersOnCanvas('both');
                break;
            case 'move-to-canvas':
                this.openMoveToCanvasMenu();
                break;
            case 'next-port':
                this.stepCustomPort(1);
                break;
            case 'prev-port':
                this.stepCustomPort(-1);
                break;
            // The assignment clear armed for this opening of the menu
            // (showContextMenu stored it). Re-checked here rather than
            // trusted: the disabled guard in handleMenuClick already blocks
            // the click, but a keyboard-driven call must not clear either.
            case 'hw-clear':
                if (this._clearMenuAction && !this._clearMenuAction.disabled
                        && typeof this._clearMenuAction.run === 'function') {
                    this._clearMenuAction.run();
                }
                break;
            // The merge-back armed for this opening of the menu, same
            // doctrine as the clear above: stored at open time, re-checked
            // here so a keyboard-driven call cannot merge what the cursor
            // never named.
            case 'hw-merge':
                if (this._mergeMenuAction
                        && typeof this._mergeMenuAction.run === 'function') {
                    this._mergeMenuAction.run();
                }
                break;
            case 'bulk-set-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), true);
                break;
            case 'bulk-unset-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), false);
                break;
            case 'bulk-set-half-auto':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'auto');
                break;
            case 'bulk-set-half-width':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'width');
                break;
            case 'bulk-set-half-height':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'height');
                break;
            case 'bulk-clear-half':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'none');
                break;
            case 'fit':
                if (window.canvasRenderer) window.canvasRenderer.fitToView();
                break;
            case 'actual-size':
                if (window.canvasRenderer) {
                    window.canvasRenderer.zoom = 1;
                    window.canvasRenderer.panX = 0;
                    window.canvasRenderer.panY = 0;
                    window.canvasRenderer.render();
                }
                break;
            case 'toggle-snap':
                if (window.canvasRenderer) {
                    window.canvasRenderer.magneticSnap = !window.canvasRenderer.magneticSnap;
                    const snapCb = document.getElementById('magnetic-snap');
                    if (snapCb) snapCb.checked = window.canvasRenderer.magneticSnap;
                }
                break;
            case 'quick-start':
                if (window.QuickStart) window.QuickStart.start();
                break;
            case 'advanced-guide':
                if (window.QuickStart) window.QuickStart.startAdvanced();
                break;
            case 'keyboard-shortcuts':
                this.openShortcutsModal();
                break;
            case 'show-logs':
                this.openLogsModal();
                break;
            case 'about':
                this.openAboutModal();
                break;
            default:
                if (action && action.startsWith('recent-file-')) {
                    const idx = parseInt(action.replace('recent-file-', ''), 10);
                    this.loadRecentFile(idx);
                }
                break;
        }
    }

    openShortcutsModal() {
        var modal = document.getElementById('shortcuts-modal');
        if (!modal) return;
        modal.style.display = 'block';
        var closeBtn = document.getElementById('shortcuts-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }

    openAboutModal() {
        var modal = document.getElementById('about-modal');
        if (!modal) return;
        var versionEl = document.getElementById('about-version');
        if (versionEl) {
            fetch('/api/version')
                .then(function(r) { return r.json(); })
                .then(function(d) { versionEl.textContent = 'v' + (d.version || ''); })
                .catch(function() { versionEl.textContent = ''; });
        }
        modal.style.display = 'block';
        var closeBtn = document.getElementById('about-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }
}

for (const k of Object.getOwnPropertyNames(_ExportIo.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ExportIo.prototype, k));
    }
}
