// canvas.js mixin: The data pass: per-panel flow marks, the port runs and arrows, load badges, the capacity error overlay.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    renderDataFlow(panel, layer) {
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

        // Base cabinet fill: checkerboard / palette, same as Pixel Map, with
        // the gradient overlay on top (below borders and flow arrows). These
        // used to hard-code the plain checkerboard, so gradients, palette
        // modes, and Transparent (no fill) were all ignored on the Data view.
        if (!layer.transparentFill && this._stageOn('Panels')) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width, drawn INSIDE the panel.
        if (layer.show_panel_borders && this._stageOn('Borders')) {
            this._svgGroup('Borders', layer);
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'data-flow');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
        }
        
        // Data flow arrows are rendered as a separate pass in renderDataFlowArrows
    },
    
    // Render capacity error overlay ON TOP of everything (including labels)
    // This renders WITHOUT clipping so it's visible even outside raster bounds.
    // Called from the third render pass (outside the per-layer ctx.translate),
    // so use show-translated bounds, getLayerBounds returns processor coords
    // which would land the badge at the layer's pixel-map position even when
    // the layer renders at its show position in Data Flow / Power.
    renderCapacityErrorOverlay(layer) {
        if (!layer._capacityError) return;

        const err = layer._capacityError;
        const bounds = this.getLayerBoundsInActiveView(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        
        // Red semi-transparent overlay on the layer itself
        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);
        
        // Measure text to size box appropriately
        this.ctx.font = `bold 48px ${projectFontFamily()}`;
        const titleText = `CANNOT FIT COMPLETE ${err.unitType.toUpperCase()}`;
        const titleWidth = this.ctx.measureText(titleText).width;
        
        this.ctx.font = `28px ${projectFontFamily()}`;
        const detailText = `Need ${err.unitCount} panels, port only fits ${err.panelsPerPort}`;
        const detailWidth = this.ctx.measureText(detailText).width;
        
        this.ctx.font = `24px ${projectFontFamily()}`;
        const infoText = `Port: ${err.portCapacity.toLocaleString()} px | Panel: ${err.panelPixels.toLocaleString()} px`;
        const infoWidth = this.ctx.measureText(infoText).width;
        
        // Size box to fit text with padding
        const textBoxWidth = Math.max(titleWidth, detailWidth, infoWidth) + 40;
        const textBoxHeight = 130;
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Red border around text box
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Error text
        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = `bold 48px ${projectFontFamily()}`;
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        this._fillText(titleText, layerCenterX, layerCenterY - 35);
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = `28px ${projectFontFamily()}`;
        this._fillText(detailText, layerCenterX, layerCenterY + 10);
        this.ctx.font = `24px ${projectFontFamily()}`;
        this.ctx.fillStyle = '#AAAAAA';
        this._fillText(infoText, layerCenterX, layerCenterY + 45);
    },

    // v0.11.0: the load badge that sits under a port's primary marker. Healthy
    // reads in the ordinary label colour - the owner reported coloured healthy
    // readouts being taken for faults - and only the warning (#ff6600) and
    // over-capacity (#ff0000) states get a colour, the same two the Port
    // Capacity panel uses. Drawn on the house dark plate so it stays legible
    // over any cabinet colour, and sized from the layer's own data-flow label
    // size so it tracks the slider like the P/R markers do.
    drawPortLoadBadge(layer, portPanels, centerX, centerY, markerRadius, labelSize, bounds) {
        const stats = this.getPortLoadStats(layer, portPanels);
        if (!stats) return;

        const fontSize = Math.max(8, Math.round(labelSize * 0.55));
        const text = `${stats.shown}%`;
        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        const padX = Math.max(3, Math.round(fontSize * 0.35));
        const padY = Math.max(2, Math.round(fontSize * 0.2));
        const plateWidth = this.ctx.measureText(text).width + padX * 2;
        const plateHeight = fontSize + padY * 2;

        // Under the marker by default; above it when the marker sits so low in
        // the screen that the badge would hang off the bottom edge.
        const gap = Math.max(2, Math.round(fontSize * 0.25));
        let cy = centerY + markerRadius + gap + plateHeight / 2;
        if (bounds && cy + plateHeight / 2 > bounds.bottom) {
            cy = centerY - markerRadius - gap - plateHeight / 2;
        }
        let cx = centerX;
        if (bounds) {
            if (cx - plateWidth / 2 < bounds.left) cx = bounds.left + plateWidth / 2;
            if (cx + plateWidth / 2 > bounds.right) cx = bounds.right - plateWidth / 2;
        }
        cx = this.snap(cx);
        cy = this.snap(cy);

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        const plate = this.snapRect(cx - plateWidth / 2, cy - plateHeight / 2, plateWidth, plateHeight);
        this.ctx.fillRect(plate.x, plate.y, plate.width, plate.height);

        if (stats.state === 'over') {
            this.ctx.fillStyle = '#ff0000';
        } else {
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
        }
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this._fillText(text, cx, cy);
    },

    renderDataFlowArrows(layer) {
        // Get the flow pattern (default: top-right, vertical-first)
        const pattern = layer.flowPattern || 'tl-h';
        const baseLineWidth = layer.arrowLineWidth || 4;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.dataFlowLabelSize || 30;
        // The printer page: white discs, black text, black rims; black
        // runs and arrows, dashed per port in drawPort.
        const printer = this.printerMode;
        const primaryColor = printer ? '#ffffff' : (layer.primaryColor || '#00FF00');
        const primaryTextColor = printer ? PRINTER_INK : (layer.primaryTextColor || '#000000');
        const backupColor = printer ? '#ffffff' : (layer.backupColor || '#FF0000');
        const backupTextColor = printer ? PRINTER_INK : (layer.backupTextColor || '#FFFFFF');
        const lineColor = this._ink(layer.dataFlowColor || '#FFFFFF');
        const arrowColor = this._ink(layer.arrowColor || '#0042AA');
        const useRandomColors = (layer.randomDataColors || false) && !printer;
        // The disc's rim on the printer page - a white disc on a grey
        // cabinet has no edge without one.
        const rimDisc = (x, y, radius) => {
            if (!printer) return;
            this.ctx.save();
            this.ctx.setLineDash([]);
            this.ctx.lineWidth = Math.max(1, labelSize * 0.1);
            this.ctx.strokeStyle = PRINTER_INK;
            this.ctx.beginPath();
            this.ctx.arc(x, y, radius, 0, Math.PI * 2);
            this.ctx.stroke();
            this.ctx.restore();
        };
        // v0.11.0: per-port load percentage, off by default so no existing
        // export changes. Drawn beside the port marker by drawPortLoadBadge.
        const showPortLoad = !!layer.showDataFlowPortLoad;
        const isCustomFlow = pattern === 'custom';
        if (isCustomFlow) {
            // Clear any capacity error when in custom mode
            layer._capacityError = null;
        }
        // Random color palette for multi-port support
        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];
        
        // Get visible (non-hidden) panels
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;
        
        // Save context, clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        // v0.8.7.4: layer bounds in panel-local coords, used to shift
        // port labels inward when they'd overflow the screen edge.
        // v0.11.0: in the cross-member overlay pass the "screen" a label must
        // stay inside is the whole wall, not the member that owns the port, and
        // the frame is the overlay's rather than this layer's.
        const layerBoundsForPort = this._crossMemberPass
            ? this._crossMemberBounds(layer)
            : this.getLayerBounds(layer);
        const layerLeft = layerBoundsForPort.x;
        const layerTop = layerBoundsForPort.y;
        const layerRight = layerBoundsForPort.x + layerBoundsForPort.width;
        const layerBottom = layerBoundsForPort.y + layerBoundsForPort.height;

        // `loadPanels` splits the cabinets a port is DRAWN from off the ones it
        // is SCORED on. They are the same objects for every ordinary port and
        // the argument is simply omitted; a crossing port is drawn from
        // overlay-frame shims but scored on the real cabinets, in processor
        // coords, because load and capacity are processor facts. null means the
        // port cannot be scored honestly at all (see _crossMemberLoadPanels).
        // The cable tags are drawn AFTER every port's labels are placed, so
        // a tag can be kept off the other labels of the screen - "the
        // cables added to the power or data sometimes go under labels and
        // overlap" (2026-09-09). drawPort collects the discs and the tags
        // it wants; drawCableTags places and paints them (placeCableTag:
        // beside its label, the other side, below, above - the first that
        // covers no other disc and stays inside the screen).
        const labelDiscs = [];
        const pendingTags = [];
        // LONG JUMPS (2026-09-25): with the cable tags on, a link between
        // two cabinets that do not touch wears its jumper's length at the
        // middle of its segment ("10'"); a short link above / below or
        // beside wears nothing. The lengths are the pull list's own
        // (app-jumpers jumperLongLinkMap), keyed by the real cabinets - a
        // cross-member shim through its srcPanel.
        const jumpMap = (layer.showDataCableTags === true && window.app
                && typeof window.app.jumperLongLinkMap === 'function')
            ? window.app.jumperLongLinkMap(layer, 'data') : null;
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
        const drawCableTags = () => {
            const bounds = { left: layerLeft, top: layerTop, right: layerRight, bottom: layerBottom };
            // The pills already down: a tag is placed clear of them as
            // well as of the discs - see placeCableTag.
            const taken = [];
            // The jump tags first: they sit where their segment is, so the
            // label tags are the ones that move off them. Centred on the
            // midpoint (a 'right' hang whose gap is taken back off x).
            for (const j of pendingJumps) {
                const w = this.cableTagLayout(j.text, labelSize).width;
                const x = j.x - labelSize * 0.25 - w / 2;
                const opts = { side: 'right' };
                taken.push(this.cableTagRect(j.text, x, j.y, labelSize, opts));
                this.drawCableTag(j.text, x, j.y, labelSize, DATA_CABLE_TAG_COLORS, opts, 'jump');
            }
            pendingJumps.length = 0;
            for (const t of pendingTags) {
                const at = this.placeCableTag(t.text, t.disc.x, t.disc.y, t.disc.r, labelSize,
                                              bounds, labelDiscs, t.disc, taken);
                taken.push(at.rect);
                this.drawCableTag(t.text, at.x, at.y, labelSize, DATA_CABLE_TAG_COLORS, at.opts);
            }
            pendingTags.length = 0;
        };

        const drawPort = (portPanels, portNum, loadPanels) => {
            if (portPanels.length === 0) return;
            const scoredPanels = (loadPanels === undefined) ? portPanels : loadPanels;

            // dock drag: the run under the cursor lights up before its lines
            this._dockRunUnderlay(portPanels, layer, portNum);

            const currentLineColor = useRandomColors ? randomColors[(portNum - 1) % randomColors.length] : lineColor;
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;
            // Printer page: this port's own dash (see _runDash).
            const dash = this._runDash(portNum, lineWidth);
            this.ctx.save();
            this.ctx.setLineDash(dash);
            if (dash.length) this.ctx.lineCap = 'butt';
            
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
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
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
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
            collectJumps(portPanels);
            
            const firstPanel = portPanels[0];
            const lastPanel = portPanels[portPanels.length - 1];
            const primaryLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'primary') : `P${portNum}`;
            const returnLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'return') : `R${portNum}`;

            // v0.8.7.4: render at user's labelSize directly. Circle grows
            // to fit text width so the label is never clipped. If the
            // label would overflow the screen edge, shift the CENTER
            // inward so it stays fully inside the screen.
            // A spaced label ("SR A1") stacks at the spaces instead of
            // inflating the circle - see _layoutCircleLabel.
            const sizeLabel = (label) => {
                this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
                const padding = Math.max(4, labelSize * 0.2);
                const layout = this._layoutCircleLabel(
                    label, labelSize, labelSize * 1.2, padding);
                return { size: labelSize, radius: layout.radius, lines: layout.lines };
            };
            const primaryFit = sizeLabel(primaryLabel);
            const returnFit = sizeLabel(returnLabel);

            const shiftIntoBounds = (px, py, radius) => {
                if (px - radius < layerLeft) px = layerLeft + radius;
                if (px + radius > layerRight) px = layerRight - radius;
                if (py - radius < layerTop) py = layerTop + radius;
                if (py + radius > layerBottom) py = layerBottom - radius;
                return { px: this.snap(px), py: this.snap(py) };
            };

            const primaryPos = shiftIntoBounds(
                firstPanel.x + firstPanel.width / 2,
                firstPanel.y + firstPanel.height / 2,
                primaryFit.radius
            );
            const returnPos = shiftIntoBounds(
                lastPanel.x + lastPanel.width / 2,
                lastPanel.y + lastPanel.height / 2,
                returnFit.radius
            );
            const px = primaryPos.px, py = primaryPos.py;
            const rx = returnPos.px, ry = returnPos.py;

            // If the port has only one panel, draw backup first so primary is on top.
            if (portPanels.length === 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, returnFit.radius, 0, Math.PI * 2);
                this.ctx.fill();
                rimDisc(rx, ry, returnFit.radius);
                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${returnFit.size}px ${projectFontFamily()}`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this._fillWrappedLabel(returnFit.lines, rx, ry, returnFit.size);
            }

            this.ctx.fillStyle = primaryColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, primaryFit.radius, 0, Math.PI * 2);
            this.ctx.fill();
            rimDisc(px, py, primaryFit.radius);

            this.ctx.fillStyle = primaryTextColor;
            this.ctx.font = `bold ${primaryFit.size}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillWrappedLabel(primaryFit.lines, px, py, primaryFit.size);

            if (portPanels.length > 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, returnFit.radius, 0, Math.PI * 2);
                this.ctx.fill();
                rimDisc(rx, ry, returnFit.radius);

                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${returnFit.size}px ${projectFontFamily()}`;
                this._fillWrappedLabel(returnFit.lines, rx, ry, returnFit.size);
            }

            // The port's home run, as a small blue tag beside its label -
            // the snake it rides ("SNAKE A") or its own cable ("50' CAT"):
            // "the same option for data homeruns" (2026-09-06), per screen,
            // default OFF, and the same test in exportMode so the PDF is
            // what was asked for. The power tag's drawer, in the data
            // cable's colours.
            // Every label disc of this pass, for the tags' placement:
            // a tag beside one label must never cover another.
            const primaryDisc = { x: px, y: py, r: primaryFit.radius };
            const returnDisc = { x: rx, y: ry, r: returnFit.radius };
            labelDiscs.push(primaryDisc, returnDisc);

            if (layer.showDataCableTags === true && window.app
                    && typeof window.app.dataPortCableForScreen === 'function') {
                // One tag beside one marker, drawn in a second pass once
                // every label of the screen is placed (see drawCableTags
                // below): right of the circle when that fits, else left
                // of it, and off any OTHER label's disc. A wrapped tag is
                // taller than its label circle, so it carries the
                // screen's top and bottom too and shifts inside them the
                // way the circle's centre was shifted.
                const cable = window.app.dataPortCableForScreen(layer, portNum);
                if (cable && cable.text) {
                    pendingTags.push({ text: cable.text, disc: primaryDisc });
                }
                // The return marker wears the BACKUP socket's own tag the
                // same way - the backup box's snake, its extension, or its
                // loose cable ("also redundancy extensions and snakes arent
                // showing their cable tags", 2026-09-07). Nothing where the
                // port has no backup or the backup socket carries nothing.
                const backup = typeof window.app.dataPortBackupCableForScreen === 'function'
                    ? window.app.dataPortBackupCableForScreen(layer, portNum) : null;
                if (backup && backup.text) {
                    pendingTags.push({ text: backup.text, disc: returnDisc });
                }
            }

            // v0.11.0: how close this port is to its limit, under the primary
            // marker so it reads with the port it belongs to and never covers
            // the port number itself. Runs for the hand-drawn custom paths too,
            // which is the case the percentage was asked for.
            if (showPortLoad && scoredPanels) {
                this.drawPortLoadBadge(layer, scoredPanels, px, py, primaryFit.radius, labelSize, {
                    left: layerLeft, right: layerRight, top: layerTop, bottom: layerBottom
                });
            }
        };

        // Custom flow mode: use user-defined paths
        if (isCustomFlow && layer.customPortPaths) {
            const portNums = Object.keys(layer.customPortPaths)
                .map(n => parseInt(n, 10))
                .sort((a, b) => a - b);

            portNums.forEach(portNum => {
                const path = layer.customPortPaths[portNum] || [];
                // v0.11.0: a path that stays on this layer is resolved and drawn
                // exactly as it always was; a path that reaches into a peer is
                // skipped here and drawn by the post-loop overlay pass, which
                // re-enters this function with _crossMemberPass raised and
                // takes the other side of both branches below.
                if (this._deferCrossMemberPath(layer, path)) return;
                if (this._crossMemberPass) {
                    drawPort(this._crossMemberDrawPanels(layer, path), portNum,
                        this._crossMemberLoadPanels(layer, path));
                    return;
                }
                const portPanels = path.map(p => {
                    const panel = layer.panels.find(panel => panel.row === p.row && panel.col === p.col);
                    return panel && !panel.hidden ? panel : null;
                }).filter(Boolean);
                drawPort(portPanels, portNum);
            });

            drawCableTags();
            this.ctx.restore();
            return;
        }

        // v0.12: automatic assignment CAN leave its layer now - a screen group
        // whose members are the same panel routes as one bigger screen (see
        // getAutoRoutePlan). A port that stays home is drawn here exactly as it
        // always was; one that reaches a peer is deferred to the same overlay
        // pass the hand-drawn crossing paths use, because an arrow drawn inside
        // this layer's transform lands in the wrong place on a member carrying a
        // different rotation or Show Look offset, and a member drawn later would
        // paint over it. A layer the plan makes a PEER gets an empty assignment
        // list back and draws nothing at all.
        const assignments = window.app ? window.app.calculatePortAssignments(layer) : [];
        if (layer._capacityError) {
            this.ctx.restore();
            return;
        }

        const ports = new Map();
        assignments.forEach(item => {
            if (!item || !item.panel || item.panel.hidden) return;
            if (!ports.has(item.port)) ports.set(item.port, []);
            ports.get(item.port).push(item);
        });

        [...ports.keys()].sort((a, b) => a - b).forEach(portNum => {
            const items = ports.get(portNum) || [];
            const crosses = items.some(i =>
                i.layerId !== undefined && i.layerId !== null && i.layerId !== layer.id);
            if (this._deferCrossMember(layer, crosses)) return;
            if (crosses) {
                const hits = this._autoCrossMemberHits(layer, items);
                // Drawn through each cabinet's own member's frame; SCORED on the
                // raw panels, which are already canvas-relative and share one
                // processor raster across the group (_crossMemberLoadPanels
                // carries the same distinction for the hand-drawn side).
                drawPort(hits.map(h => this._crossMemberPanelShim(h.layer, h.panel)),
                    portNum, hits.map(h => h.panel));
                return;
            }
            drawPort(items.map(i => i.panel), portNum);
        });

        drawCableTags();
        this.ctx.restore();
    },
});
