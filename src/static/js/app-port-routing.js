// app-port-routing: the data-port routing engine for LEDRasterApp.
// calculatePortAssignments walks a screen's cabinets into per-port runs under
// the processor's published capacity, and the frame-rate helpers
// (publishedFrameRates, updateFrameRateOptions) keep the offered rates to the
// rows a figure is published for. Moved verbatim out of app-export-io.js and
// attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _PortRouting {
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
            // fully served by a peer's hand-drawn path reports zero. The one
            // exception is the member's own per-run OVERRIDES: a redrawn port
            // is a physical output on THIS member's processor, so it is
            // reported here, by the layer that owns it, and nowhere else.
            layer._capacityError = null;
            layer._lowLatencyDerate = null;
            layer._autoPortsRequired = 0;
            return this._appendOverridePortItems(layer, [], plan);
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
        // Per-run overrides: a cabinet on a hand-drawn override anywhere in
        // the path scope is already fed, so the automatic walk lays over
        // everything else and the overridden port numbers are skipped when the
        // walk's ports are numbered (see the assignment loop at the bottom).
        // The claim set is empty for every project without overrides, and
        // every list below is then byte-identical to what it always was.
        const claimed = (typeof this._overrideClaims === 'function')
            ? this._overrideClaims(layer, 'data') : new Set();
        const orderedByPattern = includeHidden => {
            const ordered = plan
                ? plan.ordered
                    .filter(c => includeHidden || !c.panel.hidden)
                    .map(c => c.panel)
                : this.getOrderedPanelsByPattern(layer, pattern, includeHidden);
            return claimed.size === 0 ? ordered : ordered.filter(p => !claimed.has(p));
        };

        const orderedForCapacity = orderedByPattern(usesRectangle);
        if (orderedForCapacity.length === 0) {
            return this._appendOverridePortItems(layer, [], plan);
        }

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
            if (llPanels.length === 0) {
                return this._appendOverridePortItems(layer, [], plan);
            }

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
        // Per-run overrides reserve their numbers: the walk's ports take
        // 1, 2, 3... skipping every overridden number, so a port whose
        // cabinets the walk never touched keeps the number it always had and
        // nothing reshuffles beyond the cabinets the user actually took.
        const reserved = (typeof this.getOverrideNums === 'function'
            && !this.isCustomFlow(layer))
            ? this.getOverrideNums(layer, 'data') : [];
        let nextPortNum = 1;
        const takePortNum = () => {
            while (reserved.includes(nextPortNum)) nextPortNum++;
            return nextPortNum++;
        };
        ports.forEach((port) => {
            // v0.11.0: only the Organized branch stores row/column indices;
            // the Low Latency branch carries its own ordered panel list.
            // The Organized list is re-derived from the grid here, so the
            // override claims are dropped from it the same way the capacity
            // walk dropped them above.
            const portPanels = ((isOrganized && !llGeometry)
                ? this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, port.unitIndices || [], false, plan)
                : (port.panels || []))
                .filter(p => claimed.size === 0 || !claimed.has(p));
            const portNum = takePortNum();
            let pixelIndex = 0;
            portPanels.forEach((panel, panelIdx) => {
                const item = {
                    panel,
                    port: portNum,
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
        return this._appendOverridePortItems(layer, assignments, plan);
    }

    // Fold this layer's overridden ports into an automatic assignment, in the
    // item shape every consumer already reads. `_autoPortsRequired` becomes
    // the highest port number in use - the number-skip can leave gaps, and a
    // processor has to have output 11 for a run labelled P11, so the highest
    // number is the honest requirement (the same highest-drawn convention
    // whole-screen custom has always reported). A no-op returning the
    // assignment untouched for every layer without overrides.
    _appendOverridePortItems(layer, assignments, plan) {
        // Gate on the RESERVED numbers, not just the drawn paths: an override
        // whose path is empty still reserves its number and shifts the walk's
        // numbering, so the highest-in-use figure has to be recomputed for it
        // too - ports.length would report one port short across the gap.
        const reserves = (typeof this.getOverrideNums === 'function'
            && !this.isCustomFlow(layer))
            ? this.getOverrideNums(layer, 'data') : [];
        if (reserves.length === 0) return assignments;
        const overrides = this._ownOverrideRuns(layer, 'data');
        overrides.forEach(o => {
            let pixelIndex = 0;
            o.hits.forEach((hit, i) => {
                const item = {
                    panel: hit.panel,
                    port: o.num,
                    isPortStart: i === 0,
                    pixelIndex
                };
                if (plan || hit.layer.id !== layer.id) item.layerId = hit.layer.id;
                assignments.push(item);
                pixelIndex += this.getPanelPixelArea(hit.panel);
            });
        });
        layer._autoPortsRequired = assignments.reduce(
            (max, x) => Math.max(max, (x && x.port) || 0), 0);
        // Ascending port order, the shape the pure walk has always produced -
        // a consumer walking the list to find "the first port" must not find
        // an override parked at the end. The sort is stable, so cabinets
        // within a port keep their feed order.
        assignments.sort((a, b) => a.port - b.port);
        return assignments;
    }
}

for (const k of Object.getOwnPropertyNames(_PortRouting.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PortRouting.prototype, k));
    }
}
