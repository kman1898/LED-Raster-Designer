// app-screen-info: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { evaluateMathExpression, sendClientLog, refreshAllColorSwatches } from './helpers.js';

class _ScreenInfo {
    getPanelLoadFactor(layer, panel) {
        const fullPixels = this.getFullPanelPixels(layer);
        const panelPixels = this.getPanelPixelArea(panel);
        if (fullPixels <= 0 || panelPixels <= 0) return 0;
        const areaRatio = panelPixels / fullPixels;
        if (areaRatio >= 0.999) return 1;
        return Math.min(1, areaRatio * 1.3);
    }

    // ── Screen groups (v0.11.0): combined totals across a group's members ──
    //
    // A group is one screen built from more than one layer, because the
    // per-layer grid is uniform: a wall of 1m JP5 cabinets AND 0.5m standard
    // cabinets has to be two layers. The geometry already lands correctly -
    // what does not is every TOTAL, which still reads per layer, so the user
    // building that wall gets two half-answers and adds them up by hand.
    //
    // There is no new maths below. Each figure is the per-layer figure the app
    // already computes, evaluated against EACH member's own cabinet size,
    // weight and wattage, and then summed:
    //
    //   equivalentPanels  getPanelLoadFactor          (area derate; already
    //                                                  correct for mixed sizes)
    //   pixels            getPanelPixelArea
    //   watts / weight    equivalentPanels x the MEMBER's panelWatts /
    //                     panel_weight - members differ, so one member's
    //                     per-cabinet figure can never stand in for the group
    //   amps              I = P / V and I = P / (V x 1.73), exactly as
    //                     updatePowerCapacityDisplay writes
    //                     _powerTotalAmps1 / _powerTotalAmps3
    //   circuits          calculatePowerAssignments(member).circuits.length
    //   ports             calculatePortAssignments(member), read the same way
    //                     updatePortCapacityDisplay reads it
    //
    // Ports and circuits stay PER MEMBER by design: automatic assignment walks
    // one uniform grid, so a group's requirement is the sum of its members'
    // own requirements, not a re-run across the combined shape.
    //
    // Which panels count: non-blank AND non-hidden, matching getPowerCounts
    // and the canvas weight label. A blanked panel is a hole in the wall - no
    // cabinet hangs there, so it has no weight and draws nothing.

    // Resolve a group (or a bare group id) to its member layers, in the order
    // the group lists them. layer_ids is the authoritative side of the
    // relationship server-side (see _enforce_group_integrity), so it is the
    // side walked here too.
    getGroupMembers(group) {
        const g = this.resolveGroup(group);
        if (!g || !Array.isArray(g.layer_ids)) return [];
        const layers = (this.project && this.project.layers) || [];
        const byId = new Map(layers.map(l => [l.id, l]));
        const seen = new Set();
        const members = [];
        g.layer_ids.forEach(lid => {
            if (seen.has(lid)) return;
            const layer = byId.get(lid);
            if (!layer) return;
            seen.add(lid);
            members.push(layer);
        });
        return members;
    }

    resolveGroup(group) {
        if (typeof group === 'string') {
            const groups = (this.project && this.project.groups) || [];
            return groups.find(g => g && g.id === group) || null;
        }
        return group || null;
    }

    // How much of this layer's grid is fed by paths a PEER member owns?
    // Returns { total, covered } counted in CABINETS: `total` is the cabinets
    // that need feeding at all (a blank is a hole in the wall and a hidden
    // cabinet does not light, so neither needs a port or a circuit), `covered`
    // is how many of those a peer's drawn path has already picked up.
    //
    // v0.11.0 step 6: this is what stops a group counting the same port twice.
    // A member in custom mode with nothing of its own drawn falls back below
    // to "at least the active port index", which is the right answer for a
    // standalone screen and the wrong one for a member whose cabinets are
    // already fed by the peer's port: that port is the PEER'S, it is counted
    // there, and counting it again here prints 2 Mains on a wall with one
    // cable in it.
    //
    // v0.11.0 audit fix: this used to be a bare `.some()` - ONE cabinet
    // claimed by a neighbour zeroed the WHOLE member. A 20 x 2 Brompton wall
    // needing 2 ports of its own reported 0 because a peer's cable had picked
    // up a single cabinet, so 39 cabinets were planned for with no port at
    // all. Counting is the whole point of the change: the caller can now tell
    // FULL coverage (the honest zero) from PARTIAL coverage (still needs its
    // own ports).
    //
    // Coverage is measured by (row, col) because that is the only durable
    // cabinet address (panel ids are regenerated on every geometry rebuild),
    // and a claim on a blank or hidden cabinet is ignored on purpose - it
    // cannot "cover" a cabinet that was never going to draw a port.
    //
    // Returns { total: 0, covered: 0 } for every ungrouped layer and for every
    // project with no cross-layer step anywhere, so nothing existing moves.
    _peerPathCoverage(layer, pathsKey) {
        const out = { total: 0, covered: 0 };
        if (!layer || typeof this.getPathScopeLayers !== 'function') return out;
        const feedable = (layer.panels || []).filter(p => p && !p.blank && !p.hidden);
        out.total = feedable.length;
        if (out.total === 0) return out;
        const claimed = new Set();
        this.getPathScopeLayers(layer).forEach(peer => {
            if (!peer || peer.id === layer.id) return;
            const paths = peer[pathsKey];
            if (!paths) return;
            Object.keys(paths).forEach(k => {
                (paths[k] || []).forEach(e => {
                    if (e && e.layerId === layer.id) claimed.add(`${e.row},${e.col}`);
                });
            });
        });
        if (claimed.size === 0) return out;
        out.covered = feedable.filter(p => claimed.has(`${p.row},${p.col}`)).length;
        return out;
    }

    // True only when EVERY cabinet of `layer` that needs feeding is already on
    // a peer's path. That is the only case where returning 0 is honest: the
    // cable exists, it is counted on the member that owns it, and this member
    // adds nothing.
    _layerFullyServedByPeerPath(layer, pathsKey) {
        const c = this._peerPathCoverage(layer, pathsKey);
        return c.total > 0 && c.covered >= c.total;
    }

    // Ports required for ONE member, derived exactly as
    // updatePortCapacityDisplay derives it for the selected layer:
    // calculatePortAssignments does all the maths (and stamps
    // _autoPortsRequired on the way through), and a custom flow overrides the
    // automatic figure with the highest port the user actually drew. Split out
    // here rather than called through the display function because that one
    // only ever looks at this.currentLayer, and a group's members are not it.
    //
    // v0.11.0 step 6: this is now the ONE implementation. The sidebar readout,
    // the group roll-up and the canvas label each grew their own copy, and the
    // moment a port spans two members those three copies print three different
    // numbers at the user. `assignments` lets a caller that has already run
    // calculatePortAssignments (for the Low Latency derate note) pass it in
    // rather than paying for the walk twice.
    getLayerPortsRequired(layer, assignments = null) {
        if (!layer || (layer.type || 'screen') !== 'screen') return 0;
        const a = assignments || this.calculatePortAssignments(layer) || [];
        const auto = layer._autoPortsRequired
            || a.reduce((max, x) => Math.max(max, (x && x.port) || 0), 0);
        // The paths object is defaulted rather than required. Guarding the whole
        // branch on `layer.customPortPaths` meant a member in custom flow that
        // had never had its custom state initialised - a project saved before
        // the key existed, or a peer that inherited the group's flow pattern
        // without ensureCustomFlowState running on it - skipped the
        // served-by-a-peer check below and reported its AUTOMATIC port count.
        // On a wall where a neighbour's port already feeds every one of its
        // cabinets that is a phantom extra port in the roll-up.
        if (this.isCustomFlow(layer)) {
            const paths = layer.customPortPaths || {};
            const customPorts = Object.keys(paths)
                .map(p => parseInt(p, 10))
                .filter(p => (paths[p] || []).length > 0);
            if (customPorts.length > 0) return Math.max(...customPorts);
            // FULL coverage by a peer's port is the only honest zero - every
            // cabinet here is on the neighbour's cable, and that cable is
            // counted on the neighbour.
            if (this._layerFullyServedByPeerPath(layer, 'customPortPaths')) return 0;
            // PARTIAL coverage falls through to this member's OWN requirement.
            //
            // What is the honest number for the cabinets a peer did NOT pick
            // up? It is somewhere between ceil(their pixels / port capacity)
            // and the requirement of the whole member, and the app cannot
            // narrow it: the automatic walk packs ports along whole rows or
            // columns of a grid, so dropping a cabinet out of the middle of one
            // does not reliably drop a port, and pro-rating the figure by the
            // uncovered share would quietly hand back FEWER ports than the
            // remaining cabinets need. Removing cabinets can never make the
            // automatic walk need more ports, so the whole member's own figure
            // is a true upper bound on what the remainder needs - at worst one
            // port too many on the order sheet, where the old behaviour was
            // 39 cabinets with nothing to plug them into.
            //
            // WHICH GRID is that walk over? THIS member's, here - reaching this
            // line means the member is on a custom flow, and a group with one
            // custom member does not cross automatically at all
            // (_autoCrossMembers). Where the group DOES cross, the walk is over
            // the whole wall and `auto` is already the wall's figure on the
            // first member and 0 on every other, so this branch never sees it.
            return auto > 0 ? auto : (layer.customPortIndex || 1);
        }
        // For a crossing group this is the figure the ONE combined walk
        // produced, reported by the group's first member and by nobody else -
        // see getAutoRoutePlan. It is not the sum of what the members would each
        // have needed alone, and it can be LOWER than that sum: two members that
        // each need 1.5 ports round up to 2 + 2 = 4 apart and pack into 3
        // together. Losing that per-member rounding waste is the point.
        return auto;
    }

    // Circuits required for ONE member. Mirrors getLayerPortsRequired exactly:
    // the automatic assignment's circuit count, overridden by the highest
    // circuit the user drew in custom mode, and zero for a member whose
    // cabinets are fed by a peer's crossing circuit.
    //
    // `autoCircuits` defaults to the cached _powerCircuitsRequired because the
    // two callers that want this figure (the power label editor and the canvas
    // label) both run right after something already computed it.
    getLayerCircuitsRequired(layer, autoCircuits = null) {
        if (!layer || (layer.type || 'screen') !== 'screen') return 0;
        let auto = autoCircuits;
        if (auto === null || auto === undefined) auto = Number(layer._powerCircuitsRequired) || 0;
        // Defaulted, not required - same phantom-circuit reason as the ports
        // twin above.
        if (this.isCustomPower(layer)) {
            const paths = layer.powerCustomPaths || {};
            const customCircuits = Object.keys(paths)
                .map(c => parseInt(c, 10))
                .filter(c => (paths[c] || []).length > 0);
            if (customCircuits.length > 0) {
                // Splitter merges collapse drawn circuits into shared ones:
                // each merge group of the drawn set is ONE circuit, so the
                // highest-number convention gives back (group size - 1) per
                // group. Routed through the same validated-read helper the
                // engine and screenCircuits use; with no merges this is
                // exactly the old Math.max figure.
                const max = Math.max(...customCircuits);
                const groups = (typeof this.appliedSplitterGroups === 'function')
                    ? this.appliedSplitterGroups(layer, customCircuits).merge : [];
                const reduction = groups.reduce((t, g) => t + (g.length - 1), 0);
                return Math.max(1, max - reduction);
            }
            // Same rule as the ports twin above, and the same reasoning for
            // partial coverage: only a member whose every cabinet is on a
            // peer's circuit contributes nothing. One cabinet picked up by the
            // neighbour must not zero the circuits the rest of the wall draws.
            if (this._layerFullyServedByPeerPath(layer, 'powerCustomPaths')) return 0;
            return auto > 0 ? auto : (layer.powerCustomIndex || 1);
        }
        return auto;
    }

    // The canvas a layer counts on, by the SAME rule the Screens sidebar uses
    // to decide which canvas section a row lands in (app-canvas-ui.js
    // regroupLayersByCanvas): Show Look / Data / Power read the show override
    // first, Pixel Map / Cabinet ID read the processor canvas. Kept as its own
    // helper so the roll-up and the sidebar can never drift apart.
    _totalsCanvasIdOf(layer) {
        if (!layer) return null;
        const cr = window.canvasRenderer;
        const isShowView = !!(cr && typeof cr.isShowLookView === 'function'
            && cr.isShowLookView());
        return ((isShowView && layer.show_canvas_id) ? layer.show_canvas_id
            : layer.canvas_id) || null;
    }

    // The canvas a GROUP's totals are reported on. The sidebar puts the group
    // row in the canvas section its topmost member row sits in, and lifts only
    // the members that share that section (app-screen-groups.js
    // regroupLayersByGroup), so the roll-up anchors on the first canvas - in
    // project canvas order - that holds a screen member. Falls back to the
    // first member's own canvas when the project carries no canvas list at all
    // (single-canvas projects and every unit test that builds a bare project),
    // which keeps those counting every member exactly as before.
    _groupAnchorCanvasId(members) {
        const screens = (members || []).filter(
            l => l && (l.type || 'screen') === 'screen');
        if (screens.length === 0) return null;
        const cids = screens.map(l => this._totalsCanvasIdOf(l));
        const canvases = (this.project && this.project.canvases) || [];
        for (const c of canvases) {
            if (c && cids.includes(c.id)) return c.id;
        }
        return cids[0];
    }

    // Combined totals for a group. Safe on an empty group, a group of one, a
    // group whose members are all hidden, and a group that has picked up an
    // image or text layer - those are counted as skipped, not as screens.
    //
    // `canvasId` overrides which canvas the totals are reported for; leave it
    // out and the group's anchor canvas (above) is used. The renderer wants it
    // when it labels a group on a canvas that is not the anchor.
    getGroupTotals(group, canvasId = undefined) {
        const g = this.resolveGroup(group);
        const members = this.getGroupMembers(g);
        // v0.11.0 audit fix: members sitting on ANOTHER canvas were summed in.
        // A group row on canvas 1 read "3 screens - 48 cab - 960 kg" while
        // showing 2 rows, because one member had been moved to canvas 2. That
        // kg figure is what gets handed to a rigger, so it has to describe the
        // wall in front of them and nothing else.
        const anchorCanvasId = (canvasId === undefined)
            ? this._groupAnchorCanvasId(members) : (canvasId || null);
        const totals = {
            groupId: g ? (g.id || null) : null,
            name: g ? (g.name || null) : null,
            canvasId: anchorCanvasId,   // the canvas these totals describe
            memberCount: 0,        // screens actually counted
            hiddenCount: 0,        // members skipped because layer.visible is false
            nonScreenCount: 0,     // members skipped because they are not screens
            offCanvasCount: 0,     // members skipped because they sit on another canvas
            wattsUnset: [],        // members with no panelWatts entered
            cabinets: 0,
            pixels: 0,
            equivalentPanels: 0,
            weightKg: 0,
            weightLb: 0,
            watts: 0,
            voltage: null,         // the shared voltage, or null when they differ
            voltages: [],          // distinct voltages, first-seen order
            voltageMismatch: false,
            amps1ph: null,
            amps3ph: null,
            portsPrimary: 0,
            portsBackup: 0,
            circuits: 0,
            powerError: null,      // first member whose circuits could not be built
            members: [],
        };

        const voltages = [];
        members.forEach(layer => {
            if ((layer.type || 'screen') !== 'screen') {
                totals.nonScreenCount++;
                return;
            }
            // A member on another canvas is a different workspace entirely -
            // the same rule getPathScopeLayers and canvas.js _groupDrawnMembers
            // already apply. Counted, not silently dropped, so the caller can
            // say WHY the row count and the screen count differ.
            if (this._totalsCanvasIdOf(layer) !== anchorCanvasId) {
                totals.offCanvasCount++;
                return;
            }
            // v0.11.0: `visible === false`, not `!visible`. A layer that simply
            // has no `visible` key is visible everywhere else in the app - the
            // Python side reads `layer.get('visible', True)` and the layer list
            // and canvas both test `=== false`. Treating a missing key as hidden
            // silently drops that screen's cabinets, weight and watts from the
            // group total.
            if (layer.visible === false) {
                totals.hiddenCount++;
                return;
            }
            const activePanels = (layer.panels || []).filter(p => !p.blank && !p.hidden);
            const equivalentPanels = activePanels.reduce(
                (sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
            const pixels = activePanels.reduce(
                (sum, p) => sum + this.getPanelPixelArea(p), 0);

            // parseFloat(...) || 0 rather than a stand-in default, because
            // calculatePowerAssignments below reads panelWatts the same way -
            // a group reporting 200 W a cabinet while reporting 0 circuits
            // would be incoherent. The weight fallback mirrors the canvas
            // weight label (layer.panel_weight || 20) so the group figure and
            // the member's own label can never disagree.
            //
            // v0.11.0 audit: this is now the ONE rule project-wide - the
            // getPowerCounts stand-in of 200 W a cabinet is gone, because a
            // wattage the user never entered is not a safer answer than no
            // wattage, it is just a wrong one nobody can trace. A screen with
            // no panelWatts is named in `wattsUnset` so the UI can say "no
            // wattage entered" instead of printing a confident 0 A.
            const panelWatts = parseFloat(layer.panelWatts) || 0;
            if (!(panelWatts > 0)) totals.wattsUnset.push(layer.id);
            const watts = panelWatts * equivalentPanels;
            const panelWeightValue = layer.panel_weight || 20;
            const panelWeightKg = (layer.weight_unit || 'kg') === 'lb'
                ? (panelWeightValue / 2.20462)
                : panelWeightValue;
            const weightKg = equivalentPanels * panelWeightKg;
            const voltage = parseFloat(layer.powerVoltage) || 0;
            if (!voltages.includes(voltage)) voltages.push(voltage);

            const powerAssignments = this.calculatePowerAssignments(layer)
                || { circuits: [], error: null };
            // The automatic figure is only the answer when the automatic map
            // is the one in use. A member on a custom power flow is wired the
            // way the user DREW it, so counting the assignment the app would
            // have made instead reports circuits that are not on the wall -
            // and step 6 made that reachable, because a circuit can now be
            // drawn across members. getLayerCircuitsRequired picks whichever
            // map is enabled, and returns 0 for a member whose cabinets are
            // fed by a peer's crossing circuit so one cable is not counted
            // twice. Ports have gone through the matching function since
            // step 6; this brings power into line with data.
            const autoCircuits = (powerAssignments.circuits || []).length;
            const circuits = this.getLayerCircuitsRequired(layer, autoCircuits);
            const powerError = powerAssignments.error
                ? powerAssignments.error.message : null;
            if (powerError && !totals.powerError) totals.powerError = powerError;
            const ports = this.getLayerPortsRequired(layer);

            totals.memberCount++;
            totals.cabinets += activePanels.length;
            totals.pixels += pixels;
            totals.equivalentPanels += equivalentPanels;
            totals.weightKg += weightKg;
            totals.watts += watts;
            totals.portsPrimary += ports;
            totals.circuits += circuits;
            totals.members.push({
                id: layer.id,
                name: layer.name || '',
                cabinets: activePanels.length,
                pixels,
                equivalentPanels,
                weightKg,
                weightLb: weightKg * 2.20462,
                watts,
                voltage,
                // Per member as well as combined, so a mixed-voltage group has
                // something real to show instead of a blended figure.
                amps1ph: voltage > 0 ? watts / voltage : 0,
                amps3ph: voltage > 0 ? watts / (voltage * 1.73) : 0,
                ports,
                circuits,
                powerError,
            });
        });

        totals.weightLb = totals.weightKg * 2.20462;
        // Every primary port has a backup/return port, same convention as
        // getPortCounts.
        totals.portsBackup = totals.portsPrimary;
        totals.voltages = voltages;
        totals.voltageMismatch = voltages.length > 1;
        if (totals.voltageMismatch) {
            // 200 A at 110 V and 200 A at 208 V are not the same load, so
            // there is no honest combined amps figure. Null forces the caller
            // to show the per-member ones rather than print a plausible
            // average nobody can act on.
            totals.voltage = null;
            totals.amps1ph = null;
            totals.amps3ph = null;
        } else {
            const voltage = voltages.length === 1 ? voltages[0] : 0;
            totals.voltage = voltages.length === 1 ? voltage : null;
            totals.amps1ph = voltage > 0 ? totals.watts / voltage : 0;
            totals.amps3ph = voltage > 0 ? totals.watts / (voltage * 1.73) : 0;
        }
        return totals;
    }

    // ── Automatic routing across a group's members ────────────────────────
    //
    // A GROUP IS ONE BIGGER SCREEN, so the automatic port and circuit walk runs
    // over the whole wall instead of once per member. The user's words: a
    // crossing group "wouldn't change the count necessarily it just basically
    // increases screen size". The practical win is the per-member rounding
    // waste: two members each needing 1.5 ports round up to 2 + 2 = 4 today,
    // where one walk across the pair needs 3. A count that DROPS after grouping
    // is this working, not a bug.
    //
    // WHEN MAY IT CROSS. Every member has to be the same panel, because the
    // walk packs one uniform run of cabinets:
    //   data   same RESOLUTION - cabinet_width and cabinet_height equal. The
    //          physical millimetres are irrelevant; a 128x128 cabinet chains the
    //          same whether its box is 500 mm or 600 mm.
    //   power  same resolution AND the same panelWatts, because a circuit is
    //          packed by load.
    // So a group can legitimately cross for data and not for power - a 500 mm
    // and a 600 mm cabinet at the same resolution but different draw. That falls
    // out of the rule and is intended.
    //
    // HALF TILES DO NOT BLOCK IT. A half tile is the same panel cropped, not a
    // different panel, so the comparison is the panel SPEC and never
    // halfFirstColumn / halfLastColumn / halfFirstRow / halfLastRow or anything
    // derived from them. Their reduced load is already carried per cabinet by
    // getPanelPixelArea / getPanelLoadFactor.
    //
    // MIXED RESOLUTION KEEPS TODAY'S BEHAVIOUR - each member routes its own
    // grid and the user wires the seam with a custom path. The lattice below
    // orders a mixed wall perfectly well (tests/test_audit_cross_member.py
    // proves it across all eight patterns on a 1m + 0.5m wall); the gate is
    // deliberately stricter than the ordering can manage, because there is no
    // single port capacity or circuit load that describes two different panels.
    //
    // THE GROUP CAN DECLINE. "Route <group> as one screen" (group.
    // routeDataAsOne, Data Settings) turns the DATA crossing off for one
    // group - some walls are cabled per section on site regardless of what
    // the panels would allow.
    // The check sits here rather than in every reader because this is the one
    // gate they all pass through: the walk, the counts, the arrows, the group
    // roll-up and the peer's sidebar figure all revert together.
    _autoCrossMembers(layer, kind, ignoreToggle = false) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        if (!layer.group_id) return null;
        // "Route data as one screen" - the group's own switch on this walk.
        // Absent is ON, so every group made before the switch existed keeps
        // crossing; only a stored false takes the wall back to per-member
        // routing, cabled exactly as ungrouped screens. DATA only: a circuit
        // packs by load and the power gate below reads exactly as it did.
        // `ignoreToggle` lets the Data Settings row ask whether the wall
        // COULD cross, so the switch can grey out where crossing is never on
        // offer.
        if (kind === 'data' && !ignoreToggle) {
            const own = (typeof this.getGroupOfLayer === 'function')
                ? this.getGroupOfLayer(layer) : null;
            if (own && own.routeDataAsOne === false) return null;
        }
        // A hidden member is not part of the wall this walk describes, and it
        // must not be the one holding the group's whole requirement - see
        // getGroupTotals, which skips hidden members outright.
        if (layer.visible === false) return null;
        if (typeof this.getPathScopeLayers !== 'function') return null;
        // No renderer means no position lattice, and ordering a crossing walk
        // by the panels' own indices would snake it through an order that
        // exists nowhere on site. Refuse to cross rather than cross badly - and
        // refuse it HERE, so the owner and its peers reach the same answer.
        const cr = (typeof window !== 'undefined') ? window.canvasRenderer : null;
        if (!cr || typeof cr.getPositionLattice !== 'function') return null;

        const scope = this.getPathScopeLayers(layer).filter(l => l
            && (l.type || 'screen') === 'screen'
            && Array.isArray(l.panels) && l.panels.length > 0
            && l.visible !== false);
        if (scope.length < 2) return null;

        // A member the user has hand-wired is not on the automatic map at all,
        // and half a wall walked automatically while the other half is drawn is
        // not one screen. One custom member takes the whole group back to
        // per-member routing, which is exactly what it did before.
        const custom = kind === 'power'
            ? (l => this.isCustomPower(l)) : (l => this.isCustomFlow(l));
        if (scope.some(custom)) return null;

        // ONE PROCESSOR RASTER. getPathScopeLayers already keeps the members
        // to one SHOW canvas, which is what makes a cable drawable across them.
        // A port is judged against the processor's raster though - panel.x/y are
        // laid out from the layer's offset on canvas_id, and the low-latency
        // (1 - Y/H) derate measures Y down that raster - so two members that
        // share a show canvas while sitting on different rasters have no honest
        // combined port load and no honest H. Same refusal _crossMemberLoadPanels
        // makes for a hand-drawn crossing port's load badge.
        const raster = scope[0].canvas_id || null;
        if (!scope.every(l => (l.canvas_id || null) === raster)) return null;

        // Compare the panel SPEC, never the half-tile flags.
        const w = Number(scope[0].cabinet_width) || 0;
        const h = Number(scope[0].cabinet_height) || 0;
        if (!(w > 0) || !(h > 0)) return null;
        if (!scope.every(l => (Number(l.cabinet_width) || 0) === w
                && (Number(l.cabinet_height) || 0) === h)) return null;
        if (kind === 'power') {
            const watts = parseFloat(scope[0].panelWatts) || 0;
            if (!(watts > 0)) return null;
            if (!scope.every(l => (parseFloat(l.panelWatts) || 0) === watts)) return null;
        }

        // ONE canonical order, so every member derives the SAME wall. The path
        // scope puts the asking layer first, which would give each member a
        // different first member and a different owner; the group's own member
        // order does not move with who is asking.
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        const rank = new Map();
        ((group && typeof this.getGroupMembers === 'function')
            ? (this.getGroupMembers(group) || []) : []).forEach((m, i) => {
            if (m) rank.set(m.id, i);
        });
        const at = m => (rank.has(m.id) ? rank.get(m.id) : Number.MAX_SAFE_INTEGER);
        return scope.slice().sort((a, b) => at(a) - at(b) || (a.id - b.id));
    }

    // The wall an automatic route walks, or null when this layer routes alone -
    // which is every ungrouped screen, every group of one and every group whose
    // members are not the same panel, so those take exactly the path they took
    // before this existed.
    //
    // ORDERING IS BY POSITION, NOT BY INDEX. A member's row 3 and a peer's row 3
    // are two different heights on the wall the moment the members sit at
    // different offsets, so the cabinets are ranked on the shared position
    // lattice (canvas.js getPositionLattice) and then walked by the same
    // getPatternOrderForGrid the hand-drawn cross-member patterns use. There is
    // exactly one ordering in this app and this is it; a second one would
    // eventually snake the wall in a different order than the cabinet IDs read.
    //
    // ONE OWNER REPORTS THE WALL. members[0] carries the whole group's route;
    // every other member returns an empty assignment and a requirement of 0.
    // That is the same convention a member fully served by a peer's hand-drawn
    // path already follows (_layerFullyServedByPeerPath), and it is what stops
    // the group roll-up counting one port twice.
    getAutoRoutePlan(layer, kind = 'data') {
        const members = this._autoCrossMembers(layer, kind);
        if (!members) return null;
        const owner = members[0];
        // A peer only ever asks one question - am I the owner - and the answer
        // is no. Returning before the lattice is built keeps a frame to ONE
        // ranking per group instead of one per member; this runs from every
        // render of every member and from both roll-ups.
        if (owner.id !== layer.id) {
            return { kind, members, owner, isOwner: false };
        }
        const pattern = kind === 'power'
            ? (owner.powerFlowPattern || 'tl-h') : (owner.flowPattern || 'tl-h');

        const picks = [];
        members.forEach(m => (m.panels || []).forEach(panel => picks.push({ layer: m, panel })));

        // Hidden cabinets are IN the walk and dropped on the way out, exactly as
        // getOrderedPanelsByPattern has always treated them: the serpentine runs
        // over the whole grid, so a hidden cabinet still consumes its slot and
        // does not reverse the row it sits in.
        const grid = this._latticeGridForPicks(owner, picks);
        const ordered = this._orderPicksForPattern(owner, pattern, picks, grid);

        return {
            kind,
            members,
            owner,
            isOwner: true,
            pattern,
            ordered,
            rowOf: grid.rowOf,
            colOf: grid.colOf,
            rows: grid.rows,
            columns: grid.cols,
        };
    }

    // Is this member's routing carried by ANOTHER member, rather than missing?
    //
    // Two ways that happens, and both make a requirement of 0 the honest figure
    // rather than a screen with nothing plugged into it:
    //   * the group routes automatically as one screen and this is not the
    //     member that owns the walk (v0.12);
    //   * every one of its cabinets is already on a peer's hand-drawn cable
    //     (v0.11.0).
    // Read by the sidebar, which otherwise prints a red ERROR next to a wall
    // that is correctly routed.
    isServedByPeerRouting(layer, kind = 'data') {
        const plan = this.getAutoRoutePlan(layer, kind);
        if (plan && !plan.isOwner) return true;
        const custom = kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer);
        if (!custom) return false;
        return this._layerFullyServedByPeerPath(
            layer, kind === 'power' ? 'powerCustomPaths' : 'customPortPaths');
    }

    // `plan` (from getAutoRoutePlan) swaps the layer's own grid for the wall's
    // position lattice: same serpentine, ranked slots instead of panel indices.
    // Null - every ungrouped screen - reads the panels' own row/col and this is
    // expression for expression what it always was.
    getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, orderedUnitIndices, includeHidden = false, plan = null) {
        if (!layer || !Array.isArray(layer.panels) || !Array.isArray(orderedUnitIndices)) return [];
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        const source = plan ? plan.ordered.map(c => c.panel) : layer.panels;
        const rowOfPanel = plan ? (p => plan.rowOf.get(p)) : (p => p.row);
        const colOfPanel = plan ? (p => plan.colOf.get(p)) : (p => p.col);
        const gridRows = plan ? plan.rows : layer.rows;
        const gridCols = plan ? plan.columns : layer.columns;
        const panelMap = new Map();
        source.forEach(panel => {
            panelMap.set(`${rowOfPanel(panel)},${colOfPanel(panel)}`, panel);
        });

        const ordered = [];
        orderedUnitIndices.forEach((unitIdx, unitPos) => {
            if (isHorizontalFirst) {
                const leftToRight = startsLeft ? (unitPos % 2 === 0) : (unitPos % 2 !== 0);
                if (leftToRight) {
                    for (let col = 0; col < gridCols; col++) {
                        const panel = panelMap.get(`${unitIdx},${col}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                } else {
                    for (let col = gridCols - 1; col >= 0; col--) {
                        const panel = panelMap.get(`${unitIdx},${col}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                }
            } else {
                const topToBottom = startsTop ? (unitPos % 2 === 0) : (unitPos % 2 !== 0);
                if (topToBottom) {
                    for (let row = 0; row < gridRows; row++) {
                        const panel = panelMap.get(`${row},${unitIdx}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                } else {
                    for (let row = gridRows - 1; row >= 0; row--) {
                        const panel = panelMap.get(`${row},${unitIdx}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                }
            }
        });
        return ordered;
    }

    // v0.11.0: the sub-grid `bounds` argument added for the retired 512 px
    // NovaStar Low Latency bands is gone with them - low latency now walks the
    // whole screen like every other mode, so this is back to its plain form.
    getOrderedPanelsByPattern(layer, pattern = 'tl-h', includeHidden = false) {
        if (!layer || !Array.isArray(layer.panels) || layer.panels.length === 0) return [];
        const cols = Number(layer.columns) || 0;
        const rows = Number(layer.rows) || 0;
        if (cols <= 0 || rows <= 0) return [];

        const panelMap = new Map();
        layer.panels.forEach(panel => {
            panelMap.set(`${panel.row},${panel.col}`, panel);
        });

        const [startCorner, direction] = pattern.split('-');
        let startRow = 0;
        let startCol = 0;
        let rowDir = 1;
        let colDir = 1;

        switch (startCorner) {
            case 'tr':
                startCol = cols - 1;
                colDir = -1;
                break;
            case 'bl':
                startRow = rows - 1;
                rowDir = -1;
                break;
            case 'br':
                startRow = rows - 1;
                startCol = cols - 1;
                rowDir = -1;
                colDir = -1;
                break;
            default:
                break;
        }

        const isVerticalFirst = direction === 'v';
        const ordered = [];

        if (isVerticalFirst) {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const reverse = colOffset % 2 === 1;
                if (reverse) {
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                }
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const reverse = rowOffset % 2 === 1;
                if (reverse) {
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                }
            }
        }

        return ordered;
    }

    // v0.8: workspace offset for the layer's parent canvas. Used by every
    // rect-test that compares workspace-coord rectangles against panel-coord
    // (canvas-relative) panel positions. Returns {wx:0, wy:0} for legacy
    // single-canvas projects so existing math is unaffected.
    // v0.8.6.2: in Show Look / Data / Power, route through the layer's
    // effective canvas (show_canvas_id || canvas_id) and the canvas's
    // show_workspace_x/y so marquee hit-test lines up with what's drawn.
    // Also includes the per-layer showOffset since show views render at
    // processor offset + showOffset.
    _getLayerWorkspaceOffset(layer) {
        if (!layer || !this.project) return { wx: 0, wy: 0 };
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const arr = this.project.canvases;
        if (Array.isArray(arr) && arr.length > 0) {
            const cid = isShowView
                ? (layer.show_canvas_id || layer.canvas_id)
                : layer.canvas_id;
            const c = cid ? arr.find(x => x && x.id === cid) : null;
            if (c) {
                let wx, wy;
                if (isShowView) {
                    wx = (c.show_workspace_x == null ? (c.workspace_x || 0) : (c.show_workspace_x || 0));
                    wy = (c.show_workspace_y == null ? (c.workspace_y || 0) : (c.show_workspace_y || 0));
                } else {
                    wx = c.workspace_x || 0;
                    wy = c.workspace_y || 0;
                }
                if (isShowView) {
                    // Show Look render offset is (showOffset - layer.offset),
                    // not raw showOffset, because getLayerBounds returns
                    // panel coords that already include layer.offset_x/y.
                    // Mirrors canvas.js getLayerRenderOffset.
                    const procX = Number(layer.offset_x) || 0;
                    const procY = Number(layer.offset_y) || 0;
                    const showX = (layer.showOffsetX != null) ? Number(layer.showOffsetX) : procX;
                    const showY = (layer.showOffsetY != null) ? Number(layer.showOffsetY) : procY;
                    wx += (showX - procX);
                    wy += (showY - procY);
                }
                return { wx, wy };
            }
        }
        // Pre-Slice-1 / orphan-layer fallback: no canvases array.
        return { wx: 0, wy: 0 };
    }

    getLayerBounds(layer) {
        if (layer && (layer.type || 'screen') === 'image') {
            const scale = Number(layer.imageScale) || 1;
            const width = (Number(layer.imageWidth) || 0) * scale;
            const height = (Number(layer.imageHeight) || 0) * scale;
            return {
                x1: Number(layer.offset_x) || 0,
                y1: Number(layer.offset_y) || 0,
                x2: (Number(layer.offset_x) || 0) + width,
                y2: (Number(layer.offset_y) || 0) + height
            };
        }
        if (layer && Array.isArray(layer.panels) && layer.panels.length > 0) {
            let minX = Infinity;
            let minY = Infinity;
            let maxX = -Infinity;
            let maxY = -Infinity;
            layer.panels.forEach(panel => {
                const x1 = Number(panel.x) || 0;
                const y1 = Number(panel.y) || 0;
                const x2 = x1 + (Number(panel.width) || 0);
                const y2 = y1 + (Number(panel.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return { x1: minX, y1: minY, x2: maxX, y2: maxY };
        }
        const width = (Number(layer.columns) || 0) * (Number(layer.cabinet_width) || 0);
        const height = (Number(layer.rows) || 0) * (Number(layer.cabinet_height) || 0);
        return {
            x1: layer.offset_x,
            y1: layer.offset_y,
            x2: layer.offset_x + width,
            y2: layer.offset_y + height
        };
    }

    selectLayersInRect(rect, toggle = false) {
        if (!this.project || !this.project.layers) return;
        const minX = Math.min(rect.x1, rect.x2);
        const maxX = Math.max(rect.x1, rect.x2);
        const minY = Math.min(rect.y1, rect.y2);
        const maxY = Math.max(rect.y1, rect.y2);

        const hits = this.project.layers.filter(layer => {
            if (layer.visible === false) return false;
            const b = this.getLayerBounds(layer);
            // Shift bounds by the layer's canvas's workspace offset so they
            // line up with the workspace-coord rect (rect is in screen-world
            // space; bounds are canvas-relative).
            const off = this._getLayerWorkspaceOffset(layer);
            const intersects = (b.x1 + off.wx) <= maxX && (b.x2 + off.wx) >= minX
                && (b.y1 + off.wy) <= maxY && (b.y2 + off.wy) >= minY;
            return intersects;
        }).map(l => l.id);

        if (!toggle) {
            this.selectedLayerIds = new Set(hits);
        } else {
            hits.forEach(id => {
                if (this.selectedLayerIds.has(id)) {
                    this.selectedLayerIds.delete(id);
                } else {
                    this.selectedLayerIds.add(id);
                }
            });
        }
        const primaryId = hits.length > 0 ? hits[hits.length - 1] : (this.currentLayer ? this.currentLayer.id : null);
        if (primaryId && this.selectedLayerIds.has(primaryId)) {
            this.currentLayer = this.project.layers.find(l => l.id === primaryId) || this.currentLayer;
        } else if (this.selectedLayerIds.size > 0 && !this.currentLayer) {
            const firstId = this.selectedLayerIds.values().next().value;
            this.currentLayer = this.project.layers.find(l => l.id === firstId) || null;
        }
        this.lastSelectedLayerId = this.currentLayer ? this.currentLayer.id : null;
        if (!this.selectionAnchorLayerId && this.currentLayer) {
            this.selectionAnchorLayerId = this.currentLayer.id;
        }
        // Slice 4 + v0.8.3: auto-activate the canvas of the new primary
        // layer, but pass preserveSelection so a marquee that crosses
        // canvas boundaries doesn't clobber the multi-layer selection
        // we just built. Without this, the first drag-select on Data /
        // Power / Cabinet ID would silently drop everything from the
        // non-active canvas.
        this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        this.loadTextLayerToInputs();
        window.canvasRenderer.render();
    }

    selectLayer(layer) {
        // Defensive: Make sure we have a valid layer
        if (!layer || !layer.id) {
            console.error('SELECT LAYER: Invalid layer', layer);
            return;
        }

        // v0.11.0 audit fix: a live cabinet selection must not survive a
        // change of screen.
        //
        // Every one of the three Sets is addressed against the layer that was
        // current when it was filled: customSelection / powerCustomSelection
        // hold `${layerId}:${row},${col}` keys that only mean anything inside
        // the OWNER's path scope, and pixelMapSelection holds bare
        // `${row},${col}` keys that silently re-address the new screen's grid.
        // Left alone, a marquee drawn as member A stayed live after clicking
        // member B in the layers list and Apply Pattern then filled B's port 1
        // with A's 18 cabinets - with an identical highlight either side of the
        // switch, so nothing on screen said the target had moved.
        //
        // CLEARED rather than re-anchored. Re-anchoring would have to invent an
        // intent the user never expressed: the keys name cabinets on screens
        // that may not even be reachable from the new layer (another group,
        // another canvas), and "the same cabinets, now feeding a different
        // port" is not what picking a different screen in the list means to
        // anyone. Clearing matches every other selection in the app - picking a
        // new layer drops the old layer selection too - and the cost of being
        // wrong is one re-drag, against a mis-wired port.
        //
        // Guarded on the id actually CHANGING, because selectLayer is also the
        // re-selection path after undo/redo, load and layer updates, where the
        // "new" layer is the same screen rebuilt and the selection must
        // survive.
        if (!this.currentLayer || this.currentLayer.id !== layer.id) {
            if (this.customSelection) this.customSelection.clear();
            if (this.powerCustomSelection) this.powerCustomSelection.clear();
            if (this.pixelMapSelection) this.pixelMapSelection.clear();
            // The custom-flow and custom-power readouts are refreshed by
            // loadLayerToInputs at the end of this function; the Pixel Map bulk
            // bar is not on that path, so it is told here or it keeps showing a
            // count for a selection that no longer exists.
            if (typeof this.updatePixelMapBulkActionUI === 'function') {
                this.updatePixelMapBulkActionUI();
            }
        }

        this.currentLayer = layer;
        this.selectedLayerIds = new Set([layer.id]);
        this.lastSelectedLayerId = layer.id;
        this.selectionAnchorLayerId = layer.id;
        // Slice 4: auto-activate this layer's canvas. Idempotent, short-
        // circuits when already active so programmatic selectLayer calls
        // (post-load, post-create, post-delete) don't fire spurious PUTs.
        this._activateCanvasForLayer(layer);
        sendClientLog('select_layer_before_defaults', {
            layerId: layer.id,
            processorType: layer.processorType,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate
        });
        
        console.log('SELECT LAYER - selected id:', this.currentLayer.id);
        
        // Initialize client-side defaults if not set
        if (this.currentLayer.arrowLineWidth === undefined) {
            this.currentLayer.arrowLineWidth = 6;
        }
        if (this.currentLayer.arrowColor === undefined) {
            this.currentLayer.arrowColor = '#0042AA';
        }
        if (this.currentLayer.dataFlowColor === undefined) {
            this.currentLayer.dataFlowColor = '#FFFFFF';
        }
        if (this.currentLayer.dataFlowLabelSize === undefined) {
            this.currentLayer.dataFlowLabelSize = 30;
        }
        if (this.currentLayer.portLabelTemplatePrimary === undefined) {
            this.currentLayer.portLabelTemplatePrimary = 'P#';
        }
        if (this.currentLayer.portLabelTemplateReturn === undefined) {
            this.currentLayer.portLabelTemplateReturn = 'R#';
        }
        if (this.currentLayer.portLabelOverridesPrimary === undefined) {
            this.currentLayer.portLabelOverridesPrimary = {};
        }
        if (this.currentLayer.portLabelOverridesReturn === undefined) {
            this.currentLayer.portLabelOverridesReturn = {};
        }
        if (this.currentLayer.customPortPaths === undefined) {
            this.currentLayer.customPortPaths = {};
        }
        if (this.currentLayer.customPortIndex === undefined) {
            this.currentLayer.customPortIndex = 1;
        }
        if (this.currentLayer.primaryColor === undefined) {
            this.currentLayer.primaryColor = '#00FF00';
        }
        if (this.currentLayer.primaryTextColor === undefined) {
            this.currentLayer.primaryTextColor = '#000000';
        }
        if (this.currentLayer.backupColor === undefined) {
            this.currentLayer.backupColor = '#FF0000';
        }
        if (this.currentLayer.backupTextColor === undefined) {
            this.currentLayer.backupTextColor = '#FFFFFF';
        }
        if (this.currentLayer.powerLabelBgColor === undefined) {
            this.currentLayer.powerLabelBgColor = '#D95000';
        }
        if (this.currentLayer.powerLabelTextColor === undefined) {
            this.currentLayer.powerLabelTextColor = '#000000';
        }
        if (this.currentLayer.flowPattern === undefined) {
            this.currentLayer.flowPattern = 'tl-h';
        }
        if (this.currentLayer.screenNameSizeCabinet === undefined) {
            this.currentLayer.screenNameSizeCabinet = 30;
        }
        if (this.currentLayer.screenNameSizeDataFlow === undefined) {
            this.currentLayer.screenNameSizeDataFlow = 30;
        }
        if (this.currentLayer.screenNameSizePower === undefined) {
            this.currentLayer.screenNameSizePower = 30;
        }
        if (this.currentLayer.showDataFlowPortInfo === undefined) {
            this.currentLayer.showDataFlowPortInfo = false;
        }
        if (this.currentLayer.showDataFlowPortLoad === undefined) {
            this.currentLayer.showDataFlowPortLoad = false;
        }
        if (this.currentLayer.showPowerCircuitInfo === undefined) {
            this.currentLayer.showPowerCircuitInfo = false;
        }
        if (this.currentLayer.number_size === undefined) {
            this.currentLayer.number_size = 30;
        }
        if (this.currentLayer.bitDepth === undefined) {
            this.currentLayer.bitDepth = this.getPreferences().bitDepth;
        }
        if (this.currentLayer.frameRate === undefined) {
            this.currentLayer.frameRate = this.getPreferences().frameRate;
        }
        if (this.currentLayer.processorType === undefined) {
            this.currentLayer.processorType = this.getPreferences().processorType;
        }
        if (this.currentLayer.lowLatency === undefined) {
            this.currentLayer.lowLatency = !!this.getPreferences().lowLatency;
        }
        if (!this.currentLayer.type) {
            this.currentLayer.type = 'screen';
        }

        sendClientLog('select_layer_after_defaults', {
            layerId: this.currentLayer.id,
            layerName: this.currentLayer.name,
            type: this.currentLayer.type || 'screen',
            columns: this.currentLayer.columns,
            rows: this.currentLayer.rows,
            processorType: this.currentLayer.processorType,
            bitDepth: this.currentLayer.bitDepth,
            frameRate: this.currentLayer.frameRate,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            selectedLayerIds: this.selectedLayerIds ? [...this.selectedLayerIds] : [],
            showLabelName: this.currentLayer.showLabelName,
            showDataFlowPortInfo: this.currentLayer.showDataFlowPortInfo,
            showPowerCircuitInfo: this.currentLayer.showPowerCircuitInfo
        });
        
        console.log('SELECT LAYER - after defaults:', {
            arrowLineWidth: this.currentLayer.arrowLineWidth,
            arrowColor: this.currentLayer.arrowColor,
            dataFlowLabelSize: this.currentLayer.dataFlowLabelSize
        });

        this.renderLayers();
        this.loadLayerToInputs();
        this.loadTextLayerToInputs();
        // Repopulate the active view's per-layer label editor so the port-rename
        // (data-flow view) or circuit-rename (power view) sidebar reflects the
        // newly selected layer immediately. Without this, the editor only
        // refreshed the next time something else nudged it, which made the
        // first click after a layer-change appear empty until a second click.
        const viewMode = window.canvasRenderer && window.canvasRenderer.viewMode;
        if (viewMode === 'data-flow') {
            this.updatePortLabelEditor();
        } else if (viewMode === 'power') {
            this.updatePowerLabelEditor();
        }
        window.canvasRenderer.render();
    }

    deleteLayer(layerId) {
        if (this.project.layers.length === 1) {
            alert('Cannot delete the last layer');
            return;
        }
        
        // Check if we're deleting the currently selected layer
        const isDeletingSelected = this.currentLayer && this.currentLayer.id === layerId;
        const deletedIndex = this.project.layers.findIndex(l => l.id === layerId);
        
        // Save the current selection ID (if not deleting it)
        const keepSelectedId = isDeletingSelected ? null : this.currentLayer?.id;
        
        // Save client-side props for remaining layers BEFORE the delete
        const savedClientProps = {};
        this.project.layers.forEach(layer => {
            if (layer.id !== layerId) {
                savedClientProps[layer.id] = this.extractClientSideProps(layer);
            }
        });
        
        console.log('DELETE LAYER - deleting id:', layerId, 'isDeletingSelected:', isDeletingSelected);
        
        fetch(`/api/layer/${layerId}`, {
            method: 'DELETE'
        })
        .then(res => res.json())
        .then(project => {
            this.project = project;
            
            // Restore client-side properties to remaining layers
            this.project.layers.forEach(layer => {
                if (savedClientProps[layer.id]) {
                    Object.assign(layer, savedClientProps[layer.id]);
                }
            });
            
            // Handle selection
            if (this.project.layers.length > 0) {
                if (keepSelectedId) {
                    // Keep the same layer selected (it wasn't deleted)
                    const keepLayer = this.project.layers.find(l => l.id === keepSelectedId);
                    if (keepLayer) {
                        this.selectLayer(keepLayer);
                    }
                } else {
                    // We deleted the selected layer - select adjacent layer
                    // If deleted from bottom (index 0), select new bottom (index 0)
                    // Otherwise select the layer that's now at the deleted position (or last if at end)
                    const newIndex = Math.min(deletedIndex, this.project.layers.length - 1);
                    this.selectLayer(this.project.layers[newIndex]);
                }
            } else {
                this.currentLayer = null;
            }
            
            this.updateUI();
            
            // Save state after delete
            this.saveState('Delete Layer');
        });
    }
    
    toggleLayerVisibility(layerId) {
        const layer = this.project.layers.find(l => l.id === layerId);
        if (!layer) return;
        layer.visible = !layer.visible;
        sendClientLog('toggle_visibility', {
            id: layer.id,
            name: layer.name,
            visible: layer.visible
        });
        // v0.8.7.7.1: when a layer is hidden, drop it from selection
        // immediately so it can't be edited / dragged / sidebar-tweaked
        // through stale references. Without this you could (e.g.) hide
        // a layer and still drag its cached screen-name label, leaving
        // the offset in a bad state when the layer was later re-shown.
        if (!layer.visible) {
            // Clear stale per-layer caches that mousedown / drag handlers
            // hit-test against. The render loop will re-populate these
            // for visible layers on the next frame.
            if (layer._screenNameHitRect) layer._screenNameHitRect = null;

            const wasSelected = this.selectedLayerIds && this.selectedLayerIds.has(layer.id);
            const wasCurrent = this.currentLayer && this.currentLayer.id === layer.id;
            if (wasSelected && this.selectedLayerIds.size > 0) {
                this.selectedLayerIds.delete(layer.id);
            }
            if (wasCurrent) {
                // Promote the next still-visible selected layer (if any),
                // otherwise pick the first visible layer in the project,
                // otherwise leave currentLayer null.
                let promoted = null;
                if (this.selectedLayerIds && this.selectedLayerIds.size > 0) {
                    for (const id of this.selectedLayerIds) {
                        const l = this.project.layers.find(x => x.id === id);
                        if (l && l.visible !== false) { promoted = l; break; }
                    }
                }
                if (!promoted) {
                    promoted = this.project.layers.find(l => l.visible !== false && l.id !== layer.id) || null;
                    if (promoted) this.selectedLayerIds = new Set([promoted.id]);
                    else this.selectedLayerIds = new Set();
                }
                this.currentLayer = promoted;
                this.lastSelectedLayerId = promoted ? promoted.id : null;
                if (typeof this.loadLayerToInputs === 'function' && promoted) {
                    try { this.loadLayerToInputs(); } catch (_) {}
                }
            }
        }
        window.canvasRenderer.render();
        this.renderLayers();
        if (typeof this.updateUI === 'function') {
            try { this.updateUI(); } catch (_) {}
        }
        // v0.10.5: record the show/hide. Without an entry of its own it rode
        // along on whatever the user did next, so one Undo reverted both.
        this.saveState(layer.visible ? 'Show Layer' : 'Hide Layer');
    }

    setLockOnSelected(locked) {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        layers.forEach(layer => {
            layer.locked = locked;
            fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ locked })
            });
        });
        if (typeof sendClientLog === 'function') {
            sendClientLog('layer_lock_batch', { locked, layerIds: layers.map(l => l.id) });
        }
        this.renderLayers();
        this.saveState(locked ? 'Lock Layers' : 'Unlock Layers');
    }

    toggleLockOnSelected() {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        const anyUnlocked = layers.some(l => !l.locked);
        this.setLockOnSelected(anyUnlocked);
    }

    toggleLayerLock(layerId) {
        const layer = this.project.layers.find(l => l.id === layerId);
        if (!layer) return;
        layer.locked = !layer.locked;
        fetch(`/api/layer/${layer.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ locked: layer.locked })
        });
        if (typeof sendClientLog === 'function') {
            sendClientLog('layer_lock_toggle', { layerId: layer.id, locked: layer.locked });
        }
        this.renderLayers();
        this.saveState(layer.locked ? 'Lock Layer' : 'Unlock Layer');
    }
    
    togglePanelBlank(layerId, panelId) {
        fetch(`/api/layer/${layerId}/panel/${panelId}/toggle`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(panel => {
            const layer = this.project.layers.find(l => l.id === layerId);
            if (layer) {
                const panelIndex = layer.panels.findIndex(p => p.id === panelId);
                if (panelIndex >= 0) {
                    layer.panels[panelIndex] = panel;
                    window.canvasRenderer.render();
                }
            }
        });
    }
    
    togglePanelHidden(layerId, panelId) {
        fetch(`/api/layer/${layerId}/panel/${panelId}/toggle_hidden`, {
            method: 'POST'
        })
        .then(res => res.json())
        // v0.10.8.1: the route now rebuilds the layer's geometry (hiding a
        // panel re-anchors neighbouring half-tiles) and returns the whole
        // rebuilt layer, not the single panel - the old panel object is stale
        // once the panels array is regenerated.
        .then(serverLayer => {
            if (!this.applyServerLayer(serverLayer, 'toggle_panel_hidden')) return;
            const layer = this.project.layers.find(l => l.id === layerId);
            if (layer) {
                const panel = (layer.panels || []).find(p => p.id === panelId);
                if (panel) {
                    sendClientLog('toggle_panel_hidden', {
                        layerId, layerName: layer.name,
                        panelId, row: panel.row, col: panel.col,
                        hidden: panel.hidden
                    });
                }
                window.canvasRenderer.render();
            }
        });
    }
    
    updateLayer(saveHistory = false, historyAction = 'Update Layer') {
        if (!this.currentLayer) return;
        
        // Save state before update if requested
        if (saveHistory) {
            this.saveState(historyAction);
        }
        
        fetch(`/api/layer/${this.currentLayer.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.currentLayer)
        })
        .then(res => res.json())
        .then(layer => {
            const index = this.project.layers.findIndex(l => l.id === layer.id);
            if (index >= 0) {
                // Preserve client-side only properties that server might not return
                const preservedProps = {
                    screenNameOffsetX: this.currentLayer.screenNameOffsetX,
                    screenNameOffsetY: this.currentLayer.screenNameOffsetY,
                    screenNameOffsetXPixelMap: this.currentLayer.screenNameOffsetXPixelMap,
                    screenNameOffsetYPixelMap: this.currentLayer.screenNameOffsetYPixelMap,
                    screenNameOffsetXCabinet: this.currentLayer.screenNameOffsetXCabinet,
                    screenNameOffsetYCabinet: this.currentLayer.screenNameOffsetYCabinet,
                    screenNameOffsetXDataFlow: this.currentLayer.screenNameOffsetXDataFlow,
                    screenNameOffsetYDataFlow: this.currentLayer.screenNameOffsetYDataFlow,
                    screenNameOffsetXPower: this.currentLayer.screenNameOffsetXPower,
                    screenNameOffsetYPower: this.currentLayer.screenNameOffsetYPower,
                    screenNameOffsetXShowLook: this.currentLayer.screenNameOffsetXShowLook,
                    screenNameOffsetYShowLook: this.currentLayer.screenNameOffsetYShowLook,
                    gradientEnabled: this.currentLayer.gradientEnabled,
                    gradientType: this.currentLayer.gradientType,
                    gradientScope: this.currentLayer.gradientScope,
                    gradientPanelAlternate: this.currentLayer.gradientPanelAlternate,
                    gradientRadialCenterX: this.currentLayer.gradientRadialCenterX,
                    gradientRadialCenterY: this.currentLayer.gradientRadialCenterY,
                    gradientRadialRadius: this.currentLayer.gradientRadialRadius,
                    gradientAngle: this.currentLayer.gradientAngle,
                    gradientOpacity: this.currentLayer.gradientOpacity,
                    gradientBlend: this.currentLayer.gradientBlend,
                    gradientStops: this.currentLayer.gradientStops,
                    panelColorMode: this.currentLayer.panelColorMode,
                    panelColors: this.currentLayer.panelColors,
                    screenNameSize: this.currentLayer.screenNameSize,
                    screenNameSizeCabinet: this.currentLayer.screenNameSizeCabinet,
                    screenNameSizeDataFlow: this.currentLayer.screenNameSizeDataFlow,
                    screenNameSizePower: this.currentLayer.screenNameSizePower,
                    flowPattern: this.currentLayer.flowPattern,
                    dataFlowColor: this.currentLayer.dataFlowColor,
                    dataFlowLabelSize: this.currentLayer.dataFlowLabelSize,
                    arrowLineWidth: this.currentLayer.arrowLineWidth,
                    primaryColor: this.currentLayer.primaryColor,
                    primaryTextColor: this.currentLayer.primaryTextColor,
                    backupColor: this.currentLayer.backupColor,
                    backupTextColor: this.currentLayer.backupTextColor,
                    randomDataColors: this.currentLayer.randomDataColors,
                    portLabelTemplatePrimary: this.currentLayer.portLabelTemplatePrimary,
                    portLabelTemplateReturn: this.currentLayer.portLabelTemplateReturn,
                    portLabelOverridesPrimary: this.currentLayer.portLabelOverridesPrimary,
                    portLabelOverridesReturn: this.currentLayer.portLabelOverridesReturn,
                    customPortPaths: this.currentLayer.customPortPaths,
                    customPortIndex: this.currentLayer.customPortIndex,
                    customPortOverrides: this.currentLayer.customPortOverrides,
                    processorType: this.currentLayer.processorType,
                    lowLatency: this.currentLayer.lowLatency,
                    bitDepth: this.currentLayer.bitDepth,
                    frameRate: this.currentLayer.frameRate,
                    portMappingMode: this.currentLayer.portMappingMode,
                    powerVoltage: this.currentLayer.powerVoltage,
                    powerVoltageCustom: this.currentLayer.powerVoltageCustom,
                    powerAmperage: this.currentLayer.powerAmperage,
                    powerAmperageCustom: this.currentLayer.powerAmperageCustom,
                    panelWatts: this.currentLayer.panelWatts,
                    powerMaximize: this.currentLayer.powerMaximize,
                    powerOrganized: this.currentLayer.powerOrganized,
                    powerCustomPath: this.currentLayer.powerCustomPath,
                    powerFlowPattern: this.currentLayer.powerFlowPattern,
                    powerLineWidth: this.currentLayer.powerLineWidth,
                    powerLineColor: this.currentLayer.powerLineColor,
                    powerArrowColor: this.currentLayer.powerArrowColor,
                    powerRandomColors: this.currentLayer.powerRandomColors,
                    powerColorCodedView: this.currentLayer.powerColorCodedView,
                    powerCircuitColors: this.currentLayer.powerCircuitColors,
                    powerLabelSize: this.currentLayer.powerLabelSize,
                    powerLabelBgColor: this.currentLayer.powerLabelBgColor,
                    powerLabelTextColor: this.currentLayer.powerLabelTextColor,
                    powerLabelTemplate: this.currentLayer.powerLabelTemplate,
                    powerLabelOverrides: this.currentLayer.powerLabelOverrides,
                    powerSocaLengths: this.currentLayer.powerSocaLengths,
                    powerSocaPhaseOffset: this.currentLayer.powerSocaPhaseOffset,
                    powerSocaPhasePos: this.currentLayer.powerSocaPhasePos,
                    powerSocaDistro: this.currentLayer.powerSocaDistro,
                    powerSocaNames: this.currentLayer.powerSocaNames,
                    powerSocaNumber: this.currentLayer.powerSocaNumber,
                    powerSocaSplits: this.currentLayer.powerSocaSplits,
                    powerSocaKeying: this.currentLayer.powerSocaKeying,
                    powerBreakoutType: this.currentLayer.powerBreakoutType,
                    showSocaBrackets: this.currentLayer.showSocaBrackets,
                    powerSplitters: this.currentLayer.powerSplitters,
                    powerCustomPaths: this.currentLayer.powerCustomPaths,
                    powerCustomIndex: this.currentLayer.powerCustomIndex,
                    powerCustomOverrides: this.currentLayer.powerCustomOverrides,
                    border_color_pixel: this.currentLayer.border_color_pixel,
                    border_color_cabinet: this.currentLayer.border_color_cabinet,
                    border_color_data: this.currentLayer.border_color_data,
                    border_color_power: this.currentLayer.border_color_power,
                    lastPowerFlowPattern: this.currentLayer.lastPowerFlowPattern,
                    showDataFlowPortInfo: this.currentLayer.showDataFlowPortInfo,
                    showPowerCircuitInfo: this.currentLayer.showPowerCircuitInfo,
                    _powerTotalAmps1: this.currentLayer._powerTotalAmps1,
                    _powerTotalAmps3: this.currentLayer._powerTotalAmps3,
                    _powerCircuitsRequired: this.currentLayer._powerCircuitsRequired,
                    panel_weight: this.currentLayer.panel_weight,
                    weight_unit: this.currentLayer.weight_unit,
                    infoLabelSize: this.currentLayer.infoLabelSize,
                    type: this.currentLayer.type,
                    imageData: this.currentLayer.imageData,
                    imageWidth: this.currentLayer.imageWidth,
                    imageHeight: this.currentLayer.imageHeight,
                    imageScale: this.currentLayer.imageScale
                };
                
                console.log('PRESERVING PROPS:', preservedProps);
                
                // Merge preserved props back into returned layer
                Object.keys(preservedProps).forEach(key => {
                    if (preservedProps[key] !== undefined) {
                        layer[key] = preservedProps[key];
                    }
                });
                
                console.log('AFTER MERGE - layer.dataFlowColor:', layer.dataFlowColor);
                console.log('AFTER MERGE - layer.screenNameSize:', layer.screenNameSize);
                console.log('AFTER MERGE - layer.screenNameOffsetX:', layer.screenNameOffsetX);
                
                this.project.layers[index] = layer;
                this.currentLayer = layer;
                this.updateUI();
            }
        });
    }

    updateLayers(layers, saveHistory = false, historyAction = 'Update Layers') {
        if (!layers || layers.length === 0) return;
        if (!this.project || !this.project.layers) return;

        // v0.11.0: a screen group is one screen. When an edit propagated a
        // wall-level field to the peers that were not themselves selected,
        // those peers ride along on THIS call - same PUT, same history entry -
        // so a group can never be left half-updated on the server.
        if (this._withPendingGroupPeers) layers = this._withPendingGroupPeers(layers);

        if (saveHistory) {
            this.saveState(historyAction);
        }
        sendClientLog('update_layers', {
            count: layers.length,
            action: historyAction,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            layers: layers.map(l => ({
                id: l.id, name: l.name,
                columns: l.columns, rows: l.rows,
                offset_x: l.offset_x, offset_y: l.offset_y,
                showLabelName: l.showLabelName,
                showDataFlowPortInfo: l.showDataFlowPortInfo,
                showPowerCircuitInfo: l.showPowerCircuitInfo
            }))
        });

        const requests = layers.map(layer => {
            // Fields whose server echo does not carry what the client
            // holds, re-stamped onto the response below.
            //
            // v0.11.0: this used to snapshot the VALUES here, at request
            // time, and stamp that snapshot onto the response. Every gradient
            // control assigns a BRAND-NEW stops array (_applyGradient maps a
            // fresh object per stop), so a second edit made while the first
            // PUT was still in flight was undone the moment that first
            // response landed - the stop the user had just dragged jumped
            // back on its own, and the undo snapshot taken 400ms later
            // recorded the reverted value as if the user had chosen it.
            // Local round-trips are ~10ms and these controls fire on every
            // input event, so a drag hit it constantly.
            //
            // Read the LIVE layer at response time instead: the re-stamp can
            // then only ever carry the newest value, never resurrect an older
            // one. Names only, so there is nothing here to go stale.
            const preservedKeys = [
                'showOffsetX', 'showOffsetY', 'screenNameOffsetX',
                'screenNameOffsetY', 'screenNameOffsetXPixelMap',
                'screenNameOffsetYPixelMap',
                'screenNameOffsetXCabinet',
                'screenNameOffsetYCabinet',
                'screenNameOffsetXDataFlow',
                'screenNameOffsetYDataFlow', 'screenNameOffsetXPower',
                'screenNameOffsetYPower', 'screenNameOffsetXShowLook',
                'screenNameOffsetYShowLook', 'gradientEnabled',
                'transparentFill', 'rotation', 'gradientType',
                'gradientScope', 'gradientPanelAlternate',
                'gradientRadialCenterX', 'gradientRadialCenterY',
                'gradientRadialRadius', 'gradientAngle',
                'gradientOpacity', 'gradientBlend', 'gradientStops',
                'panelColorMode', 'panelColors', 'screenNameSize',
                'screenNameSizeCabinet', 'screenNameSizeDataFlow',
                'screenNameSizePower', 'flowPattern', 'dataFlowColor',
                'dataFlowLabelSize', 'arrowLineWidth', 'primaryColor',
                'primaryTextColor', 'backupColor', 'backupTextColor',
                'randomDataColors', 'portLabelTemplatePrimary',
                'portLabelTemplateReturn',
                'portLabelOverridesPrimary',
                'portLabelOverridesReturn', 'customPortPaths',
                'customPortIndex', 'customPortOverrides',
                'processorType', 'lowLatency',
                'bitDepth', 'frameRate', 'portMappingMode',
                'powerVoltage', 'powerVoltageCustom', 'powerAmperage',
                'powerAmperageCustom', 'panelWatts', 'powerMaximize',
                'powerOrganized', 'powerCustomPath',
                'powerFlowPattern', 'powerLineWidth',
                'powerLineColor', 'powerArrowColor',
                'powerRandomColors', 'powerColorCodedView',
                'powerCircuitColors', 'powerLabelSize',
                'powerLabelBgColor', 'powerLabelTextColor',
                'powerLabelTemplate', 'powerLabelOverrides',
                'powerCustomPaths', 'powerCustomIndex',
                'powerCustomOverrides',
                'border_color_pixel', 'border_color_cabinet',
                'border_color_data', 'border_color_power',
                'lastPowerFlowPattern', 'showDataFlowPortInfo',
                'lastFlowPattern',
                'sizeByDimensions', 'targetWidth', 'targetHeight',
                'targetUnit',
                'showPowerCircuitInfo', '_powerTotalAmps1',
                '_powerTotalAmps3', '_powerCircuitsRequired',
                '_portsRequired', '_autoPortsRequired',
                'panel_weight', 'weight_unit', 'infoLabelSize',
                'type', 'imageData', 'imageWidth', 'imageHeight',
                'imageScale',
                'imageShadowEnabled', 'imageShadowColor',
                'imageShadowOpacity', 'imageShadowAngle',
                'imageShadowDistance', 'imageShadowSpread',
                'imageShadowSize',
                // Production suite: the soca plan must survive the round-trip
                // or the power map loses its home runs.
                'powerSocaLengths', 'powerSocaPhaseOffset',
                'powerSocaPhasePos', 'powerSocaDistro', 'powerBreakoutType',
                'showSocaBrackets', 'powerSplitters',
                // The names typed onto multis, the numbers pinned onto them
                // (the shared-box key), the circuit boundaries a multi was
                // split at, and the stamp saying the stores above are keyed
                // by the multi's stable index. Drop the stamp here and the
                // rekey runs a second time on reload.
                'powerSocaNames', 'powerSocaNumber', 'powerSocaSplits',
                'powerSocaKeying'
            ];

            return fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(layer)
            })
            .then(res => res.json())
            .then(updated => {
                const index = this.project.layers.findIndex(l => l.id === updated.id);
                // Deleted while this request was in flight - there is nothing
                // to merge into, and stamping a copy we then drop would just
                // be dead work.
                if (index < 0) return;
                // The LIVE object: the one any later edit mutated while the
                // request was out. Reading it here is the whole point - the
                // re-stamp can only ever carry the newest value.
                const live = this.project.layers[index];
                preservedKeys.forEach(key => {
                    if (live[key] !== undefined) updated[key] = live[key];
                });
                this.project.layers[index] = updated;
            });
        });

        Promise.all(requests).then(() => {
            // Keep currentLayer reference if possible
            if (this.currentLayer) {
                const refreshed = this.project.layers.find(l => l.id === this.currentLayer.id);
                if (refreshed) this.currentLayer = refreshed;
            }
            this.updateUI();
            if (window.canvasRenderer) {
                if (window.canvasRenderer.viewMode === 'power') {
                    this.updatePowerCapacityDisplay();
                } else if (window.canvasRenderer.viewMode === 'data-flow') {
                    this.updatePortCapacityDisplay();
                    this.updatePortLabelEditor();
                }
                // Always re-render after server response to reflect final state
                window.canvasRenderer.render();
            }
        });
    }
    
    updateLayerFromInputs() {
        const targetLayers = this.getSelectedLayers();
        if (targetLayers.length === 0) return;
        
        // Evaluate math expressions and update the input fields with results
        const readNumber = (id) => {
            const el = document.getElementById(id);
            if (!el) return { value: null, raw: null };
            const raw = String(el.value || '').trim();
            if (raw === '') return { value: null, raw: '' };
            return { value: evaluateMathExpression(raw), raw };
        };

        const offsetXVal = readNumber('offset-x').value;
        const offsetYVal = readNumber('offset-y').value;
        const showOffsetXVal = readNumber('show-offset-x').value;
        const showOffsetYVal = readNumber('show-offset-y').value;

        // For multi-select: only apply the offset field that was actually changed by the user.
        // This prevents typing in Y from overwriting all layers' X values (or vice versa).
        const multiSelected = targetLayers.length > 1;
        const lastChanged = this._lastChangedInputId || null;
        const applyOffsetX = offsetXVal !== null && (!multiSelected || lastChanged === 'offset-x');
        const applyOffsetY = offsetYVal !== null && (!multiSelected || lastChanged === 'offset-y');
        // Show-offset writes are gated strictly on lastChanged so that editing
        // the pixel-map offset doesn't fight the auto-link logic below (which
        // mirrors the new offset_x to showOffsetX while they're equal). The
        // show-offset inputs only set their fields when the user actually
        // edits them (single-select OR multi-select).
        const applyShowOffsetX = showOffsetXVal !== null && lastChanged === 'show-offset-x';
        const applyShowOffsetY = showOffsetYVal !== null && lastChanged === 'show-offset-y';
        const cabinetWidthVal = readNumber('cabinet-width').value;
        const cabinetHeightVal = readNumber('cabinet-height').value;
        const columnsVal = readNumber('screen-columns').value;
        const rowsVal = readNumber('screen-rows').value;
        // v0.10.2: Size by Wall Dimensions mode - the user enters the wall
        // size they want and columns/rows are derived per layer (rounded to
        // the nearest whole tile).
        const sizeByDimEl = document.getElementById('size-by-dimensions');
        const sizeByDimVal = sizeByDimEl && !sizeByDimEl.indeterminate ? sizeByDimEl.checked : null;
        const targetUnitEl = document.getElementById('target-unit');
        const targetUnitVal = targetUnitEl ? targetUnitEl.value : null;
        const targetWidthVal = readNumber('target-width').value;
        const targetHeightVal = readNumber('target-height').value;
        const numberSizeVal = readNumber('number-size').value;
        // The four screen-level half-tile flags were replaced by per-panel
        // halfTile state. The variables below remain (always null) so the
        // existing "if halfXxxVal !== null" assignment block stays a no-op
        // without further changes elsewhere.
        const halfFirstColumnVal = null;
        const halfLastColumnVal = null;
        const halfFirstRowVal = null;
        const halfLastRowVal = null;
        
        // Panel physical dimensions
        const panelWidthMMVal = readNumber('panel-width-mm').value;
        const panelHeightMMVal = readNumber('panel-height-mm').value;
        const panelWeightVal = readNumber('panel-weight-kg').value;
        const panelWeightUnitEl = document.getElementById('panel-weight-unit');
        const panelWeightUnitVal = panelWeightUnitEl ? panelWeightUnitEl.value : null;
        const imageScaleEl = document.getElementById('image-scale');
        const imageScaleVal = imageScaleEl ? (parseFloat(imageScaleEl.value) / 100) : null;
        
        // Border settings
        const showPanelBordersEl = document.getElementById('show-panel-borders');
        const showCircleWithXEl = document.getElementById('show-circle-with-x');
        const borderColorEl = document.getElementById('border-color');
        const borderColorCabinetEl = document.getElementById('border-color-cabinet');
        const borderColorDataEl = document.getElementById('border-color-data');
        const borderColorPowerEl = document.getElementById('border-color-power');
        const primaryTextColorEl = document.getElementById('primary-text-color');
        const backupTextColorEl = document.getElementById('backup-text-color');
        const powerLabelBgColorEl = document.getElementById('power-label-bg-color');
        const powerLabelTextColorEl = document.getElementById('power-label-text-color');
        const showPanelBordersVal = showPanelBordersEl && !showPanelBordersEl.indeterminate ? showPanelBordersEl.checked : null;
        const showCircleWithXVal = showCircleWithXEl && !showCircleWithXEl.indeterminate ? showCircleWithXEl.checked : null;
        const borderColorVal = borderColorEl ? borderColorEl.value : null;
        const borderColorCabinetVal = borderColorCabinetEl ? borderColorCabinetEl.value : null;
        const borderColorDataVal = borderColorDataEl ? borderColorDataEl.value : null;
        const borderColorPowerVal = borderColorPowerEl ? borderColorPowerEl.value : null;
        const primaryTextColorVal = primaryTextColorEl ? primaryTextColorEl.value : null;
        const backupTextColorVal = backupTextColorEl ? backupTextColorEl.value : null;
        const powerLabelBgColorVal = powerLabelBgColorEl ? powerLabelBgColorEl.value : null;
        const powerLabelTextColorVal = powerLabelTextColorEl ? powerLabelTextColorEl.value : null;
        
        
        // Per-layer label settings
        const showLabelNameEl = document.getElementById('show-label-name');
        const showLabelSizePxEl = document.getElementById('show-label-size-px');
        const showLabelSizeMEl = document.getElementById('show-label-size-m');
        const showLabelSizeFtEl = document.getElementById('show-label-size-ft');
        const showLabelInfoEl = document.getElementById('show-label-info');
        const showLabelWeightEl = document.getElementById('show-label-weight');
        const labelsColorEl = document.getElementById('labels-color');
        // labelsFontSize is now read via readNumber('labels-fontsize') below;
        // the element handle above used to be referenced directly with parseInt
        // and converted blank input into NaN, which then leaked through the
        // multi-select bulk update as a real null write. The readNumber path
        // returns null cleanly and skips the assignment in that case.
        const useFractionalInchesEl = document.getElementById('use-fractional-inches');

        const showLabelNameVal = showLabelNameEl && !showLabelNameEl.indeterminate ? showLabelNameEl.checked : null;
        const showLabelSizePxVal = showLabelSizePxEl && !showLabelSizePxEl.indeterminate ? showLabelSizePxEl.checked : null;
        const showLabelSizeMVal = showLabelSizeMEl && !showLabelSizeMEl.indeterminate ? showLabelSizeMEl.checked : null;
        const showLabelSizeFtVal = showLabelSizeFtEl && !showLabelSizeFtEl.indeterminate ? showLabelSizeFtEl.checked : null;
        const showLabelInfoVal = showLabelInfoEl && !showLabelInfoEl.indeterminate ? showLabelInfoEl.checked : null;
        const showLabelWeightVal = showLabelWeightEl && !showLabelWeightEl.indeterminate ? showLabelWeightEl.checked : null;
        const labelsColorVal = labelsColorEl ? labelsColorEl.value : null;
        // Use readNumber() so blank/NaN reads come back as null and are skipped
        // by the `!== null` guard below. Without this, multi-select with mixed
        // values shows an empty input, parseInt('') = NaN, and every selected
        // layer's labelsFontSize gets clobbered to NaN → null on the server.
        const labelsFontSizeVal = readNumber('labels-fontsize').value;
        const infoLabelSizeVal = readNumber('info-label-size').value;
        const useFractionalInchesVal = useFractionalInchesEl && !useFractionalInchesEl.indeterminate ? useFractionalInchesEl.checked : null;
        
        // Per-layer offset settings
        const showOffsetTLEl = document.getElementById('show-offset-tl');
        const showOffsetTREl = document.getElementById('show-offset-tr');
        const showOffsetBLEl = document.getElementById('show-offset-bl');
        const showOffsetBREl = document.getElementById('show-offset-br');
        const showOffsetTLVal = showOffsetTLEl && !showOffsetTLEl.indeterminate ? showOffsetTLEl.checked : null;
        const showOffsetTRVal = showOffsetTREl && !showOffsetTREl.indeterminate ? showOffsetTREl.checked : null;
        const showOffsetBLVal = showOffsetBLEl && !showOffsetBLEl.indeterminate ? showOffsetBLEl.checked : null;
        const showOffsetBRVal = showOffsetBREl && !showOffsetBREl.indeterminate ? showOffsetBREl.checked : null;
        
        const showNumbersEl = document.getElementById('show-numbers');
        const showNumbersVal = showNumbersEl && !showNumbersEl.indeterminate ? showNumbersEl.checked : null;

        // v0.11.0: screen groups. Snapshot the shareable fields BEFORE the
        // write loop below, so the propagation afterwards can tell what the
        // user actually changed. The per-member fields this loop writes
        // (cabinet size, columns, rows, offsets, panel weight) are absent from
        // GROUP_SHARED_LAYER_FIELDS and therefore never travel to a peer.
        const groupSharedBefore = this._snapshotSharedFields
            ? this._snapshotSharedFields(targetLayers) : null;

        // Update the layer properties for all selected layers
        targetLayers.forEach(layer => {
            const isImage = (layer.type || 'screen') === 'image';
            if (!layer.locked) {
                // Capture whether the show offset is currently linked to the
                // processor offset (i.e. equal). If so, editing the pixel-map
                // offset should also update showOffset so Show Look / Data /
                // Power follow the move. Once they diverge (because the user
                // explicitly set a different show offset), pixel-map edits
                // stop touching showOffset.
                const linkedX = Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0);
                const linkedY = Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0);
                if (applyOffsetX) {
                    // v0.9.3: the field shows the rotated footprint's left; convert
                    // back to the stored (unrotated) offset.
                    layer.offset_x = offsetXVal - window.canvasRenderer.getLayerFootprintOffset(layer).dx;
                    if (linkedX) layer.showOffsetX = layer.offset_x;
                }
                if (applyOffsetY) {
                    layer.offset_y = offsetYVal - window.canvasRenderer.getLayerFootprintOffset(layer).dy;
                    if (linkedY) layer.showOffsetY = layer.offset_y;
                }
                if (applyShowOffsetX) layer.showOffsetX = showOffsetXVal;
                if (applyShowOffsetY) layer.showOffsetY = showOffsetYVal;
            }
            if (isImage) {
                if (imageScaleVal !== null && !Number.isNaN(imageScaleVal)) {
                    layer.imageScale = Math.max(0.01, imageScaleVal);
                }
            } else {
                if (cabinetWidthVal !== null) layer.cabinet_width = cabinetWidthVal;
                if (cabinetHeightVal !== null) layer.cabinet_height = cabinetHeightVal;
                if (columnsVal !== null) layer.columns = Math.round(columnsVal);
                if (rowsVal !== null) layer.rows = Math.round(rowsVal);
                if (sizeByDimVal !== null) layer.sizeByDimensions = sizeByDimVal;
                if (layer.sizeByDimensions) {
                    if (targetWidthVal !== null) layer.targetWidth = targetWidthVal;
                    if (targetHeightVal !== null) layer.targetHeight = targetHeightVal;
                    if (targetUnitVal !== null) layer.targetUnit = targetUnitVal;
                    // Derive columns/rows from the targets using THIS layer's
                    // panel dimensions (multi-select safe). Overrides any
                    // manual columns/rows while the mode is on.
                    const fit = this.computeTilesForWall(layer);
                    if (fit.columns !== null) layer.columns = fit.columns;
                    if (fit.rows !== null) layer.rows = fit.rows;
                }
                if (halfFirstColumnVal !== null) layer.halfFirstColumn = halfFirstColumnVal;
                if (halfLastColumnVal !== null) layer.halfLastColumn = halfLastColumnVal;
                if (halfFirstRowVal !== null) layer.halfFirstRow = halfFirstRowVal;
                if (halfLastRowVal !== null) layer.halfLastRow = halfLastRowVal;
                if (showNumbersVal !== null) layer.show_numbers = showNumbersVal;
                if (numberSizeVal !== null) layer.number_size = Math.round(numberSizeVal);
                if (panelWidthMMVal !== null) layer.panel_width_mm = panelWidthMMVal;
                if (panelHeightMMVal !== null) layer.panel_height_mm = panelHeightMMVal;
                if (panelWeightVal !== null) layer.panel_weight = panelWeightVal;
                if (panelWeightUnitVal !== null) layer.weight_unit = panelWeightUnitVal;
                if (showPanelBordersVal !== null) layer.show_panel_borders = showPanelBordersVal;
                if (showCircleWithXVal !== null) layer.show_circle_with_x = showCircleWithXVal;
                if (borderColorVal !== null) layer.border_color_pixel = borderColorVal;
                if (borderColorCabinetVal !== null) layer.border_color_cabinet = borderColorCabinetVal;
                if (borderColorDataVal !== null) layer.border_color_data = borderColorDataVal;
                if (borderColorPowerVal !== null) layer.border_color_power = borderColorPowerVal;
            }
            if (primaryTextColorVal !== null) layer.primaryTextColor = primaryTextColorVal;
            if (backupTextColorVal !== null) layer.backupTextColor = backupTextColorVal;
            if (powerLabelBgColorVal !== null) layer.powerLabelBgColor = powerLabelBgColorVal;
            if (powerLabelTextColorVal !== null) layer.powerLabelTextColor = powerLabelTextColorVal;

            if (showLabelNameVal !== null) layer.showLabelName = showLabelNameVal;
            if (showLabelSizePxVal !== null) layer.showLabelSizePx = showLabelSizePxVal;
            if (showLabelSizeMVal !== null) layer.showLabelSizeM = showLabelSizeMVal;
            if (showLabelSizeFtVal !== null) layer.showLabelSizeFt = showLabelSizeFtVal;
            if (showLabelInfoVal !== null) layer.showLabelInfo = showLabelInfoVal;
            if (showLabelWeightVal !== null) layer.showLabelWeight = showLabelWeightVal;
            if (labelsColorVal !== null) layer.labelsColor = labelsColorVal;
            if (labelsFontSizeVal !== null) layer.labelsFontSize = labelsFontSizeVal;
            if (infoLabelSizeVal !== null) layer.infoLabelSize = infoLabelSizeVal;
            if (useFractionalInchesVal !== null) layer.useFractionalInches = useFractionalInchesVal;

            if (showOffsetTLVal !== null) layer.showOffsetTL = showOffsetTLVal;
            if (showOffsetTRVal !== null) layer.showOffsetTR = showOffsetTRVal;
            if (showOffsetBLVal !== null) layer.showOffsetBL = showOffsetBLVal;
            if (showOffsetBRVal !== null) layer.showOffsetBR = showOffsetBRVal;
        });
        
        // Trigger immediate render so changes show up right away
        window.canvasRenderer.render();
        
        // Update input fields with evaluated results
        if (offsetXVal !== null) document.getElementById('offset-x').value = offsetXVal;
        if (offsetYVal !== null) document.getElementById('offset-y').value = offsetYVal;
        if (cabinetWidthVal !== null && document.getElementById('cabinet-width')) document.getElementById('cabinet-width').value = cabinetWidthVal;
        if (cabinetHeightVal !== null && document.getElementById('cabinet-height')) document.getElementById('cabinet-height').value = cabinetHeightVal;
        if (columnsVal !== null && document.getElementById('screen-columns')) document.getElementById('screen-columns').value = Math.round(columnsVal);
        if (rowsVal !== null && document.getElementById('screen-rows')) document.getElementById('screen-rows').value = Math.round(rowsVal);
        // In Size by Wall Dimensions mode the columns/rows just derived from
        // the targets win - reflect the primary layer's computed values.
        if (this.currentLayer && this.currentLayer.sizeByDimensions) {
            if (document.getElementById('screen-columns')) document.getElementById('screen-columns').value = this.currentLayer.columns;
            if (document.getElementById('screen-rows')) document.getElementById('screen-rows').value = this.currentLayer.rows;
        }
        this.refreshSizeByDimensionsUI();
        if (numberSizeVal !== null && document.getElementById('number-size')) document.getElementById('number-size').value = Math.round(numberSizeVal);
        if (panelWidthMMVal !== null && document.getElementById('panel-width-mm')) document.getElementById('panel-width-mm').value = panelWidthMMVal;
        if (panelHeightMMVal !== null && document.getElementById('panel-height-mm')) document.getElementById('panel-height-mm').value = panelHeightMMVal;
        if (panelWeightVal !== null && document.getElementById('panel-weight-kg')) document.getElementById('panel-weight-kg').value = panelWeightVal;
        
        // Update port capacity display when panel size changes (screen layers only)
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'screen') {
            this.updatePortCapacityDisplay();
        }
        
        // v0.11.0: carry the wall-level fields this edit changed to the rest of
        // each group. updateLayers() picks the peers up from the pending set,
        // so they land in the same PUT and the same undo step.
        if (groupSharedBefore && this._propagateChangedSharedFields) {
            this._propagateChangedSharedFields(targetLayers, groupSharedBefore);
        }

        this.updateLayers(targetLayers);
        // v0.10.5: every caller of this method is a 'change' handler, i.e. an
        // edit the user has already committed (typed and tabbed out, toggled a
        // checkbox, picked from a dropdown). Those each deserve their own undo
        // step. The old debounce folded a run of commits made within 500ms of
        // each other into a single snapshot, so one Ctrl+Z reverted several
        // edits at once. Continuous streams (slider drags, typing into the
        // text-layer content box) still go through debouncedSaveState.
        this.saveState('Update Properties');
    }

    // v0.10.2: Size by Wall Dimensions - how many tiles for the target wall
    // size. ft/m use the panel's physical size; px uses the cabinet pixel
    // size. Rounds to the NEAREST whole tile (17 ft on 1.64 ft tiles is 10
    // tiles, because 16.4 ft is closer than 18.04 ft); the readout shows the
    // actual built size so a quote can state it.
    computeTilesForWall(layer) {
        const unit = layer.targetUnit || 'ft';
        const tw = Number(layer.targetWidth);
        const th = Number(layer.targetHeight);
        let columns = null;
        let rows = null;
        if (unit === 'px') {
            const cw = Number(layer.cabinet_width) || 0;
            const ch = Number(layer.cabinet_height) || 0;
            if (Number.isFinite(tw) && tw > 0 && cw > 0) columns = Math.max(1, Math.round(tw / cw));
            if (Number.isFinite(th) && th > 0 && ch > 0) rows = Math.max(1, Math.round(th / ch));
        } else {
            const factor = unit === 'm' ? 1000 : 304.8; // target -> mm
            const pw = Number(layer.panel_width_mm) || 0;
            const ph = Number(layer.panel_height_mm) || 0;
            if (Number.isFinite(tw) && tw > 0 && pw > 0) columns = Math.max(1, Math.round((tw * factor) / pw));
            if (Number.isFinite(th) && th > 0 && ph > 0) rows = Math.max(1, Math.round((th * factor) / ph));
        }
        return { columns, rows };
    }

    // Show/hide the target fields, lock Columns/Rows while the mode drives
    // them, and render the tiles + actual-size readout for the primary layer.
    refreshSizeByDimensionsUI() {
        const checkbox = document.getElementById('size-by-dimensions');
        const fields = document.getElementById('size-by-dimensions-fields');
        const result = document.getElementById('size-by-dimensions-result');
        if (!checkbox || !fields) return;
        const on = checkbox.checked && !checkbox.indeterminate;
        fields.style.display = on ? '' : 'none';
        ['screen-columns', 'screen-rows'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.readOnly = on;
                el.style.opacity = on ? '0.55' : '';
            }
        });
        if (!result) return;
        const primary = this.currentLayer && (this.currentLayer.type || 'screen') === 'screen' ? this.currentLayer : null;
        if (!on || !primary) {
            result.innerHTML = '';
            return;
        }
        const cols = Number(primary.columns) || 0;
        const rows = Number(primary.rows) || 0;
        const wM = cols * (Number(primary.panel_width_mm) || 0) / 1000;
        const hM = rows * (Number(primary.panel_height_mm) || 0) / 1000;
        const wPx = cols * (Number(primary.cabinet_width) || 0);
        const hPx = rows * (Number(primary.cabinet_height) || 0);
        const ft = (m) => (m / 0.3048).toFixed(2);
        result.innerHTML = `${cols} &times; ${rows} = <b>${cols * rows} tiles</b><br>` +
            `Actual: ${wM.toFixed(2)} &times; ${hM.toFixed(2)} m &nbsp;&middot;&nbsp; ` +
            `${ft(wM)} &times; ${ft(hM)} ft &nbsp;&middot;&nbsp; ${wPx} &times; ${hPx} px`;
    }

    loadLayerToInputs() {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        const primary = this.currentLayer || layers[0];
        const allImages = layers.every(l => (l.type || 'screen') === 'image');
        const allText = layers.every(l => (l.type || 'screen') === 'text');
        const screenGridSection = document.getElementById('screen-grid-settings');
        const imageSection = document.getElementById('image-layer-section');
        if (screenGridSection) {
            screenGridSection.style.display = (allImages || allText) ? 'none' : '';
        }
        if (imageSection) {
            imageSection.style.display = allImages ? '' : 'none';
        }
        document.querySelectorAll('.screen-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = (allImages || allText) ? 'none' : '';
        });
        document.querySelectorAll('.image-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allImages ? '' : 'none';
        });
        document.querySelectorAll('.text-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allText ? '' : 'none';
        });
        this.updateLayerPanelVisibility(allImages, allText);

        const getCommon = (getter) => {
            const first = getter(layers[0]);
            const mixed = layers.some(l => getter(l) !== first);
            return { mixed, value: first };
        };

        const setTextInput = (id, common) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (common.mixed) {
                el.value = '';
                el.placeholder = '-';
            } else {
                el.value = common.value;
                el.placeholder = '';
            }
        };

        const setCheckbox = (id, common) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (common.mixed) {
                el.indeterminate = true;
            } else {
                el.indeterminate = false;
                el.checked = !!common.value;
            }
        };

        // v0.9.3: show the rotated footprint's top-left (offset + delta) so the
        // Screen Info X,Y matches where the rotated screen actually sits.
        setTextInput('offset-x', getCommon(l => Math.round((Number(l.offset_x) || 0) + window.canvasRenderer.getLayerFootprintOffset(l).dx)));
        setTextInput('offset-y', getCommon(l => Math.round((Number(l.offset_y) || 0) + window.canvasRenderer.getLayerFootprintOffset(l).dy)));
        // Show Look offsets, separate from processor offsets (Pixel Map).
        setTextInput('show-offset-x', getCommon(l => (l.showOffsetX ?? l.offset_x) || 0));
        setTextInput('show-offset-y', getCommon(l => (l.showOffsetY ?? l.offset_y) || 0));

        // Image layer controls
        const imageScaleEl = document.getElementById('image-scale');
        const imageScaleRangeEl = document.getElementById('image-scale-range');
        const imageSizeEl = document.getElementById('image-size-display');
        if (allImages) {
            const scaleCommon = getCommon(l => Math.round((l.imageScale || 1) * 100));
            if (imageScaleEl) {
                imageScaleEl.value = scaleCommon.mixed ? '' : scaleCommon.value;
                imageScaleEl.placeholder = scaleCommon.mixed ? '-' : '';
            }
            if (imageScaleRangeEl) {
                imageScaleRangeEl.value = scaleCommon.mixed ? '100' : String(scaleCommon.value);
            }
            if (imageSizeEl) {
                const w = primary.imageWidth || 0;
                const h = primary.imageHeight || 0;
                imageSizeEl.textContent = `${w}×${h}px`;
            }
            // Drop Shadow. Read straight off the layer so a reload, an undo or
            // a selection change all show what is actually being rendered.
            const shadowNumbers = [
                ['image-shadow-opacity', 'imageShadowOpacity', 75],
                ['image-shadow-angle', 'imageShadowAngle', 120],
                ['image-shadow-distance', 'imageShadowDistance', 10],
                ['image-shadow-spread', 'imageShadowSpread', 0],
                ['image-shadow-size', 'imageShadowSize', 10],
            ];
            const shadowOnEl = document.getElementById('image-shadow-enabled');
            if (shadowOnEl) {
                const onCommon = getCommon(l => !!l.imageShadowEnabled);
                shadowOnEl.indeterminate = !!onCommon.mixed;
                shadowOnEl.checked = onCommon.mixed ? false : !!onCommon.value;
            }
            shadowNumbers.forEach(([id, key, dflt]) => {
                const el = document.getElementById(id);
                if (!el) return;
                const c = getCommon(l => (l[key] == null ? dflt : Number(l[key])));
                el.value = c.mixed ? '' : String(c.value);
                el.placeholder = c.mixed ? '-' : '';
            });
            const shadowColorEl = document.getElementById('image-shadow-color');
            const shadowColorHexEl = document.getElementById('image-shadow-color-hex');
            const colorCommon = getCommon(l => l.imageShadowColor || '#000000');
            const colorVal = colorCommon.mixed ? '#000000' : String(colorCommon.value);
            if (shadowColorEl) shadowColorEl.value = colorVal;
            if (shadowColorHexEl) shadowColorHexEl.value = colorVal.toUpperCase();
        } else {
            if (imageScaleEl) {
                imageScaleEl.value = '';
                imageScaleEl.placeholder = '';
            }
            if (imageScaleRangeEl) {
                imageScaleRangeEl.value = '100';
            }
            if (imageSizeEl) {
                imageSizeEl.textContent = '-';
            }
        }
        setTextInput('cabinet-width', getCommon(l => l.cabinet_width));
        setTextInput('cabinet-height', getCommon(l => l.cabinet_height));
        setTextInput('screen-columns', getCommon(l => l.columns));
        setTextInput('screen-rows', getCommon(l => l.rows));
        // v0.10.2: restore Size by Wall Dimensions state for the selection
        setCheckbox('size-by-dimensions', getCommon(l => !!l.sizeByDimensions));
        setTextInput('target-width', getCommon(l => l.targetWidth ?? ''));
        setTextInput('target-height', getCommon(l => l.targetHeight ?? ''));
        const targetUnitSel = document.getElementById('target-unit');
        if (targetUnitSel) {
            const unitCommon2 = getCommon(l => l.targetUnit || 'ft');
            if (!unitCommon2.mixed) targetUnitSel.value = unitCommon2.value;
        }
        this.refreshSizeByDimensionsUI();
        // (legacy half-* checkboxes were removed when half-tile state moved
        // to per-panel; the four screen-level flags are migrated to per-panel
        // halfTile values on first load.)
        setCheckbox('show-numbers', getCommon(l => l.show_numbers !== false));
        setTextInput('number-size', getCommon(l => l.number_size || 24));
        
        // Load Cabinet ID settings
        const cabinetIdStyle = primary.cabinetIdStyle || 'column-row';
        const cabinetIdStyleRadio = document.querySelector(`input[name="cabinet-id-style"][value="${cabinetIdStyle}"]`);
        if (cabinetIdStyleRadio) cabinetIdStyleRadio.checked = true;
        
        const cabinetIdPosition = primary.cabinetIdPosition || 'center';
        const cabinetIdPositionRadio = document.querySelector(`input[name="cabinet-id-position"][value="${cabinetIdPosition}"]`);
        if (cabinetIdPositionRadio) cabinetIdPositionRadio.checked = true;
        
        const cabinetIdColor = primary.cabinetIdColor || '#ffffff';
        if (document.getElementById('cabinet-id-color')) {
            document.getElementById('cabinet-id-color').value = cabinetIdColor;
        }
        if (document.getElementById('cabinet-id-color-hex')) {
            document.getElementById('cabinet-id-color-hex').value = cabinetIdColor.toUpperCase();
        }
        
        // Load panel physical dimensions if elements exist
        setTextInput('panel-width-mm', getCommon(l => l.panel_width_mm || 500));
        setTextInput('panel-height-mm', getCommon(l => l.panel_height_mm || 500));
        setTextInput('panel-weight-kg', getCommon(l => l.panel_weight || 20));
        const weightUnitEl = document.getElementById('panel-weight-unit');
        if (weightUnitEl) {
            const unitCommon = getCommon(l => l.weight_unit || 'kg');
            if (!unitCommon.mixed) {
                weightUnitEl.value = unitCommon.value;
            }
        }
        
        // Load border settings (default to TRUE when undefined) - sync across all tabs
        const showBorders = getCommon(l => l.show_panel_borders !== undefined ? l.show_panel_borders : true);
        // v0.8.8.x: per-layer border width.
        const borderWidth = getCommon(l => l.panel_border_width != null ? l.panel_border_width : 2);
        ['panel-border-width', 'panel-border-width-cabinet', 'panel-border-width-data', 'panel-border-width-power'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = borderWidth.mixed ? '' : borderWidth.value;
        });
        const borderColorPixel = getCommon(l => l.border_color_pixel || l.border_color || '#ffffff');
        const borderColorCabinet = getCommon(l => l.border_color_cabinet || l.border_color || '#ffffff');
        const borderColorData = getCommon(l => l.border_color_data || l.border_color || '#ffffff');
        const borderColorPower = getCommon(l => l.border_color_power || l.border_color || '#ffffff');
        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            if (showBorders.mixed) {
                el.indeterminate = true;
            } else {
                el.indeterminate = false;
                el.checked = !!showBorders.value;
            }
        });
        
        const setColorControl = (pickerId, hexId, common) => {
            const picker = document.getElementById(pickerId);
            const hex = document.getElementById(hexId);
            const value = common.value || '#ffffff';
            if (picker) picker.value = value;
            if (hex) {
                if (common.mixed) {
                    hex.value = '';
                    hex.placeholder = '-';
                } else {
                    hex.value = value.toUpperCase();
                    hex.placeholder = '';
                }
            }
        };
        setColorControl('border-color', 'border-color-hex', borderColorPixel);
        setColorControl('border-color-cabinet', 'border-color-cabinet-hex', borderColorCabinet);
        setColorControl('border-color-data', 'border-color-data-hex', borderColorData);
        setColorControl('border-color-power', 'border-color-power-hex', borderColorPower);
        
        // Border width is fixed at 2px - no input to load
        
        if (document.getElementById('show-circle-with-x')) {
            const common = getCommon(l => l.show_circle_with_x !== undefined ? l.show_circle_with_x : true);
            setCheckbox('show-circle-with-x', common);
        }
        
        // Load per-layer label settings (with proper defaults)
        // show-label-name always reflects the pixel-map property (showLabelName).
        // Per-tab checkboxes (show-label-name-cabinet etc.) are set separately below.
        // Helper: read per-tab property, falling back to global showLabelName → true
        const _tabLabel = (l, prop) => l[prop] !== undefined ? l[prop] : (l.showLabelName !== undefined ? l.showLabelName : true);
        setCheckbox('show-label-name', getCommon(l => l.showLabelName !== undefined ? l.showLabelName : true));
        setCheckbox('show-label-size-px', getCommon(l => l.showLabelSizePx || false));
        setCheckbox('show-label-size-m', getCommon(l => l.showLabelSizeM || false));
        setCheckbox('show-label-size-ft', getCommon(l => l.showLabelSizeFt || false));
        setCheckbox('show-label-info', getCommon(l => l.showLabelInfo || false));
        setCheckbox('show-label-weight', getCommon(l => l.showLabelWeight || false));
        
        const labelsColor = primary.labelsColor || '#ffffff';
        document.getElementById('labels-color').value = labelsColor;
        if (document.getElementById('labels-color-hex')) {
            document.getElementById('labels-color-hex').value = labelsColor.toUpperCase();
        }
        setTextInput('labels-fontsize', getCommon(l => l.labelsFontSize || 30));
        const infoSizeCommon = getCommon(l => l.infoLabelSize || 14);
        const infoSizeInput = document.getElementById('info-label-size');
        const infoSizeValue = document.getElementById('info-label-size-value');
        if (infoSizeInput) {
            infoSizeInput.value = infoSizeCommon.mixed ? 14 : infoSizeCommon.value;
        }
        if (infoSizeValue) {
            infoSizeValue.textContent = `${infoSizeCommon.mixed ? 14 : infoSizeCommon.value}`;
        }
        setCheckbox('use-fractional-inches', getCommon(l => l.useFractionalInches || false));
        
        // Load per-layer offset settings
        setCheckbox('show-offset-tl', getCommon(l => l.showOffsetTL || false));
        setCheckbox('show-offset-tr', getCommon(l => l.showOffsetTR || false));
        setCheckbox('show-offset-bl', getCommon(l => l.showOffsetBL || false));
        setCheckbox('show-offset-br', getCommon(l => l.showOffsetBR || false));
        
        // Update Screen Name checkboxes on other tabs, each reads its own per-tab property
        // with fallback to global showLabelName → true (backwards compat with old project files)
        if (document.getElementById('show-label-name-cabinet')) {
            setCheckbox('show-label-name-cabinet', getCommon(l => _tabLabel(l, 'showLabelNameCabinet')));
        }
        if (document.getElementById('show-label-name-data')) {
            setCheckbox('show-label-name-data', getCommon(l => _tabLabel(l, 'showLabelNameDataFlow')));
        }
        if (document.getElementById('show-label-name-power')) {
            setCheckbox('show-label-name-power', getCommon(l => _tabLabel(l, 'showLabelNamePower')));
        }
        
        // Load Data Flow settings - with hex fields
        const dataFlowColor = primary.dataFlowColor || '#FFFFFF';
        if (document.getElementById('data-flow-color')) {
            document.getElementById('data-flow-color').value = dataFlowColor;
        }
        if (document.getElementById('data-flow-color-hex')) {
            document.getElementById('data-flow-color-hex').value = dataFlowColor.toUpperCase();
        }
        
        const arrowColor = primary.arrowColor || '#0042AA';
        if (document.getElementById('arrow-color')) {
            document.getElementById('arrow-color').value = arrowColor;
        }
        if (document.getElementById('arrow-color-hex')) {
            document.getElementById('arrow-color-hex').value = arrowColor.toUpperCase();
        }
        
        const primaryColor = primary.primaryColor || '#00FF00';
        if (document.getElementById('primary-color')) {
            document.getElementById('primary-color').value = primaryColor;
        }
        if (document.getElementById('primary-color-hex')) {
            document.getElementById('primary-color-hex').value = primaryColor.toUpperCase();
        }
        const primaryTextColor = primary.primaryTextColor || '#000000';
        if (document.getElementById('primary-text-color')) {
            document.getElementById('primary-text-color').value = primaryTextColor;
        }
        if (document.getElementById('primary-text-color-hex')) {
            document.getElementById('primary-text-color-hex').value = primaryTextColor.toUpperCase();
        }
        
        const backupColor = primary.backupColor || '#FF0000';
        if (document.getElementById('backup-color')) {
            document.getElementById('backup-color').value = backupColor;
        }
        if (document.getElementById('backup-color-hex')) {
            document.getElementById('backup-color-hex').value = backupColor.toUpperCase();
        }
        const backupTextColor = primary.backupTextColor || '#FFFFFF';
        if (document.getElementById('backup-text-color')) {
            document.getElementById('backup-text-color').value = backupTextColor;
        }
        if (document.getElementById('backup-text-color-hex')) {
            document.getElementById('backup-text-color-hex').value = backupTextColor.toUpperCase();
        }

        refreshAllColorSwatches();
        
        setTextInput('arrow-line-width', getCommon(l => l.arrowLineWidth || 6));
        setTextInput('label-size', getCommon(l => l.dataFlowLabelSize || 30));
        setCheckbox('random-colors', getCommon(l => l.randomDataColors || false));
        if (document.getElementById('custom-flow-toggle')) {
            document.getElementById('custom-flow-toggle').checked = this.currentLayer.flowPattern === 'custom';
        }
        this.updateCustomFlowUI();
        if (document.getElementById('port-label-template-primary')) {
            document.getElementById('port-label-template-primary').value = this.currentLayer.portLabelTemplatePrimary || 'P#';
        }
        if (document.getElementById('port-label-template-return')) {
            document.getElementById('port-label-template-return').value = this.currentLayer.portLabelTemplateReturn || 'R#';
        }
        
        // Load processor type, bit depth and frame rate
        if (document.getElementById('processor-type')) {
            const prefs = this.getPreferences();
            document.getElementById('processor-type').value = this.currentLayer.processorType || prefs.processorType || 'novastar-armor';
            this.updateBitDepthOptions();
            this.updateFrameRateOptions();
        }
        if (document.getElementById('bit-depth')) {
            document.getElementById('bit-depth').value = this.currentLayer.bitDepth || this.getPreferences().bitDepth || 8;
        }
        if (document.getElementById('frame-rate')) {
            document.getElementById('frame-rate').value = this.currentLayer.frameRate || this.getPreferences().frameRate || 60;
        }
        // v0.11.0: checkbox + note follow the selected layer's processor.
        this.updateLowLatencyUI();

        // Load port mapping mode button states
        const mappingMode = this.currentLayer.portMappingMode || 'organized';
        const mappingOrgBtn = document.getElementById('mapping-organized');
        const mappingMaxBtn = document.getElementById('mapping-max-capacity');
        if (mappingOrgBtn && mappingMaxBtn) {
            // v0.11.0: highlight is the .active class (theme rules are
            // !important), not inline background/color.
            mappingOrgBtn.classList.toggle('active', mappingMode === 'organized');
            mappingMaxBtn.classList.toggle('active', mappingMode !== 'organized');
        }
        
        // Update port capacity display
        this.updatePortCapacityDisplay();
        this.updatePortLabelEditor();
        
        // Load flow pattern selection
        const flowPattern = this.currentLayer.flowPattern || 'tl-h';
        document.querySelectorAll('.flow-pattern-btn:not(.power-flow-pattern-btn)').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-pattern') === flowPattern) {
                btn.classList.add('active');
            }
        });

        // Load Power settings
        const powerVoltageSelect = document.getElementById('power-voltage-select');
        const powerVoltageCustomInput = document.getElementById('power-voltage-custom');
        const powerAmperageSelect = document.getElementById('power-amperage-select');
        const powerAmperageCustomInput = document.getElementById('power-amperage-custom');
        const powerPanelWattsInput = document.getElementById('power-panel-watts');
        const powerLineWidthInput = document.getElementById('power-line-width');
        const powerLabelSizeInput = document.getElementById('power-label-size');
        const powerMaximizeCheckbox = document.getElementById('power-maximize');
        const powerOrganizedCheckbox = document.getElementById('power-organized');
        const powerCustomToggle = document.getElementById('power-custom-toggle');
        const powerRandomColorsCheckbox = document.getElementById('power-random-colors');
        const powerColorCodedViewCheckbox = document.getElementById('power-color-coded-view');

        if (powerVoltageSelect && powerVoltageCustomInput) {
            const presets = ['110', '208', '220', '230', '240'];
            const currentVoltage = String(this.currentLayer.powerVoltage ?? 110);
            if (presets.includes(currentVoltage)) {
                powerVoltageSelect.value = currentVoltage;
                powerVoltageCustomInput.style.display = 'none';
            } else {
                powerVoltageSelect.value = 'custom';
                powerVoltageCustomInput.style.display = 'inline-block';
            }
            powerVoltageCustomInput.value = this.currentLayer.powerVoltageCustom ?? this.currentLayer.powerVoltage ?? 110;
        }
        if (powerAmperageSelect && powerAmperageCustomInput) {
            const presets = ['15', '20'];
            const currentAmp = String(this.currentLayer.powerAmperage ?? 15);
            if (presets.includes(currentAmp)) {
                powerAmperageSelect.value = currentAmp;
                powerAmperageCustomInput.style.display = 'none';
            } else {
                powerAmperageSelect.value = 'custom';
                powerAmperageCustomInput.style.display = 'inline-block';
            }
            powerAmperageCustomInput.value = this.currentLayer.powerAmperageCustom ?? this.currentLayer.powerAmperage ?? 15;
        }
        if (powerPanelWattsInput) {
            powerPanelWattsInput.value = this.currentLayer.panelWatts ?? 200;
        }
        if (powerLineWidthInput) {
            powerLineWidthInput.value = this.currentLayer.powerLineWidth ?? 8;
        }
        if (powerLabelSizeInput) {
            powerLabelSizeInput.value = this.currentLayer.powerLabelSize ?? 14;
        }
        if (powerMaximizeCheckbox) {
            powerMaximizeCheckbox.checked = !!this.currentLayer.powerMaximize;
        }
        if (powerOrganizedCheckbox) {
            powerOrganizedCheckbox.checked = this.currentLayer.powerOrganized !== false;
            if (powerMaximizeCheckbox && powerMaximizeCheckbox.checked) {
                powerOrganizedCheckbox.checked = false;
            }
        }
        if (powerCustomToggle) {
            powerCustomToggle.checked = this.currentLayer.powerFlowPattern === 'custom';
        }
        if (powerRandomColorsCheckbox) {
            powerRandomColorsCheckbox.checked = !!this.currentLayer.powerRandomColors;
        }
        if (powerColorCodedViewCheckbox) {
            powerColorCodedViewCheckbox.checked = !!this.currentLayer.powerColorCodedView;
        }
        const powerCircuitColorCustomInput = document.getElementById('power-circuit-color-custom');
        const powerCircuitColorCustomHexInput = document.getElementById('power-circuit-color-custom-hex');
        const powerCircuitColorPresetInput = document.getElementById('power-circuit-color-preset');
        if (powerCircuitColorCustomInput && powerCircuitColorCustomHexInput) {
            const defaultCircuitColors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
            const firstColor = defaultCircuitColors.A || '#FF0000';
            powerCircuitColorCustomInput.value = firstColor;
            powerCircuitColorCustomHexInput.value = firstColor.toUpperCase();
        }
        if (powerCircuitColorPresetInput) {
            powerCircuitColorPresetInput.value = 'custom';
        }
        const powerCircuitColorSection = document.getElementById('power-circuit-color-section');
        if (powerCircuitColorSection) {
            powerCircuitColorSection.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        this.updatePowerCircuitColorEditor();
        if (document.getElementById('power-label-template')) {
            document.getElementById('power-label-template').value = this.currentLayer.powerLabelTemplate || 'S1-#';
        }
        this.updatePowerLabelEditor();
        const showDataFlowPortInfoEl = document.getElementById('show-data-flow-port-info');
        if (showDataFlowPortInfoEl) {
            showDataFlowPortInfoEl.checked = !!this.currentLayer.showDataFlowPortInfo;
        }
        const showDataFlowPortLoadEl = document.getElementById('show-data-flow-port-load');
        if (showDataFlowPortLoadEl) {
            showDataFlowPortLoadEl.checked = !!this.currentLayer.showDataFlowPortLoad;
        }
        const showPowerCircuitInfoEl = document.getElementById('show-power-circuit-info');
        if (showPowerCircuitInfoEl) {
            showPowerCircuitInfoEl.checked = !!this.currentLayer.showPowerCircuitInfo;
        }
        if (document.getElementById('power-line-color')) {
            document.getElementById('power-line-color').value = this.currentLayer.powerLineColor || '#FF0000';
        }
        if (document.getElementById('power-line-color-hex')) {
            document.getElementById('power-line-color-hex').value = (this.currentLayer.powerLineColor || '#FF0000').toUpperCase();
        }
        if (document.getElementById('power-arrow-color')) {
            document.getElementById('power-arrow-color').value = this.currentLayer.powerArrowColor || '#0042AA';
        }
        if (document.getElementById('power-arrow-color-hex')) {
            document.getElementById('power-arrow-color-hex').value = (this.currentLayer.powerArrowColor || '#0042AA').toUpperCase();
        }
        if (document.getElementById('power-label-bg-color')) {
            document.getElementById('power-label-bg-color').value = this.currentLayer.powerLabelBgColor || '#D95000';
        }
        if (document.getElementById('power-label-bg-color-hex')) {
            document.getElementById('power-label-bg-color-hex').value = (this.currentLayer.powerLabelBgColor || '#D95000').toUpperCase();
        }
        if (document.getElementById('power-label-text-color')) {
            document.getElementById('power-label-text-color').value = this.currentLayer.powerLabelTextColor || '#000000';
        }
        if (document.getElementById('power-label-text-color-hex')) {
            document.getElementById('power-label-text-color-hex').value = (this.currentLayer.powerLabelTextColor || '#000000').toUpperCase();
        }

        document.querySelectorAll('.power-flow-pattern-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-pattern') === (this.currentLayer.powerFlowPattern || 'tl-h')) {
                btn.classList.add('active');
            }
        });
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        
        // Load tab-specific screen name sizes
        if (document.getElementById('screen-name-size')) {
            document.getElementById('screen-name-size').value = this.currentLayer.screenNameSizeDataFlow || 30;
        }
        if (document.getElementById('screen-name-size-cabinet')) {
            document.getElementById('screen-name-size-cabinet').value = this.currentLayer.screenNameSizeCabinet || 30;
        }
        if (document.getElementById('screen-name-size-power')) {
            document.getElementById('screen-name-size-power').value = this.currentLayer.screenNameSizePower || 30;
        }
        
        const normalizeColorObject = (value, fallbackHex) => {
            const fallback = this.hexToRgb(fallbackHex);
            if (!value) return fallback;
            if (typeof value === 'string') {
                const parsed = this.hexToRgb(value);
                return parsed || fallback;
            }
            const r = Number(value.r);
            const g = Number(value.g);
            const b = Number(value.b);
            if (Number.isFinite(r) && Number.isFinite(g) && Number.isFinite(b)) {
                return { r, g, b };
            }
            return fallback;
        };
        const c1 = normalizeColorObject(this.currentLayer.color1, '#404680');
        const c2 = normalizeColorObject(this.currentLayer.color2, '#959CB8');
        const hex1 = this.rgbToHex(c1.r, c1.g, c1.b);
        const hex2 = this.rgbToHex(c2.r, c2.g, c2.b);
        document.getElementById('color1-picker').value = hex1;
        document.getElementById('color2-picker').value = hex2;
        if (document.getElementById('color1-hex')) {
            document.getElementById('color1-hex').value = hex1.toUpperCase();
        }
        if (document.getElementById('color2-hex')) {
            document.getElementById('color2-hex').value = hex2.toUpperCase();
        }
        const transparentFillEl = document.getElementById('transparent-fill');
        if (transparentFillEl) transparentFillEl.checked = !!this.currentLayer.transparentFill;
        const screenRotationEl = document.getElementById('screen-rotation');
        if (screenRotationEl) screenRotationEl.value = String((((Number(this.currentLayer.rotation) || 0) % 360) + 360) % 360);
        // On Windows the visible element is a separate ".../-swatch" div (the
        // native input is hidden), and its background is otherwise only set
        // while editing. Refresh it here so selecting a layer always shows
        // THAT layer's colors, otherwise the two screens' swatches look
        // swapped. Harmless on macOS where the swatch is hidden.
        const color1Swatch = document.getElementById('color1-picker-swatch');
        const color2Swatch = document.getElementById('color2-picker-swatch');
        if (color1Swatch) color1Swatch.style.background = hex1;
        if (color2Swatch) color2Swatch.style.background = hex2;
        // v0.8.7.8: sync the gradient editor to the (now current) layer.
        if (typeof this.loadGradientEditor === 'function') this.loadGradientEditor();
        if (typeof this.loadPaletteEditor === 'function') this.loadPaletteEditor();
    }

    updateLayerPanelVisibility(allImages, allText) {
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const activeTab = mode === 'data-flow' ? 'data-flow' : mode;
        const nonScreen = allImages || allText;
        document.querySelectorAll('.tab-panel').forEach(panel => {
            if (panel.getAttribute('data-tab') !== activeTab) {
                panel.style.display = 'none';
                return;
            }
            if (panel.classList.contains('screen-only')) {
                panel.style.display = nonScreen ? 'none' : 'block';
                return;
            }
            if (panel.classList.contains('image-only')) {
                panel.style.display = allImages ? 'block' : 'none';
                return;
            }
            if (panel.classList.contains('text-only')) {
                panel.style.display = allText ? 'block' : 'none';
                return;
            }
            panel.style.display = 'block';
        });
    }
    
    
    // Get supported bit depths for a processor
    getSupportedBitDepths(processorType) {
        const table = this.portCapacityTables[processorType];
        if (!table) return [8, 10, 12];
        return Object.keys(table).map(Number).sort((a, b) => a - b);
    }
    
    // Get supported frame rates for a processor + bit depth
    getSupportedFrameRates(processorType, bitDepth) {
        const table = this.portCapacityTables[processorType];
        if (!table || !table[bitDepth]) return [];
        return Object.keys(table[bitDepth]).map(Number).sort((a, b) => a - b);
    }
    
    // v0.11.0: descriptor for a processor's Low Latency behaviour, or null when
    // the processor has no entry (a stale value like the retired brompton-ull).
    getLowLatencyProfile(processorType) {
        return this.lowLatencyProfiles[processorType || 'novastar-armor'] || null;
    }

    // v0.11.0: true when the processor's Low Latency behaviour is real but its
    // math has not shipped yet ('y-derate' / 'port-width' in pass 1). Callers
    // must SAY so rather than let the displayed capacity imply it is included.
    isLowLatencyCapacityPending(processorType) {
        const profile = this.getLowLatencyProfile(processorType);
        if (!profile || !profile.supported) return false;
        const kind = (profile.capacity && profile.capacity.kind) || 'none';
        return !this.lowLatencyImplementedKinds.includes(kind);
    }

    // v0.11.0: apply the processor's Low Latency capacity behaviour on top of a
    // table lookup.
    //   'factor'      - Brompton publishes ULL as the normal column halved and
    //                   floored, so floor here too. Flooring also means we
    //                   never hand back MORE capacity than the manual does.
    //   'none'        - no pixels-per-port cost.
    //   'novastar-ll' - geometric: the table value IS the port's TOTAL, so it
    //                   comes back unchanged. The (1 - Y/H) derate needs each
    //                   port's position and is applied in
    //                   calculatePortAssignments instead.
    applyLowLatencyCapacity(capacity, processorType, lowLatency) {
        if (!lowLatency || !(capacity > 0)) return capacity;
        const profile = this.getLowLatencyProfile(processorType);
        if (!profile || !profile.supported) return capacity;
        const cap = profile.capacity || {};
        if (cap.kind === 'factor') return Math.floor(capacity * cap.factor);
        return capacity;
    }

    // v0.11.0: the geometric Low Latency rules for THIS layer, or null when
    // they do not apply (low latency off, or a processor family whose low
    // latency is a plain capacity change). Returns the descriptor's own
    // capacity block: { yDerate } - true on every NovaStar line, legacy and
    // COEX, per NovaStar's own answer.
    getLowLatencyGeometry(layer) {
        if (!layer || !layer.lowLatency) return null;
        if ((layer.type || 'screen') !== 'screen') return null;
        const profile = this.getLowLatencyProfile(layer.processorType || 'novastar-armor');
        if (!profile || !profile.supported) return null;
        const cap = profile.capacity || {};
        return cap.kind === 'novastar-ll' ? cap : null;
    }

    // v0.11.0: pixel-raster height of the layer's OWN canvas - the H in the
    // NovaStar (1 - Y/H) derate. Panel x/y are already canvas-relative (the
    // server builds them from offset_x/offset_y), so they compare directly
    // against this. Falls back to the pre-canvases project raster, then 0;
    // 0 means "unknown" and callers must not derate rather than guess.
    getLayerCanvasHeight(layer) {
        if (!layer) return 0;
        const canvases = (this.project && this.project.canvases) || [];
        const canvas = (Array.isArray(canvases) && layer.canvas_id)
            ? canvases.find(c => c && c.id === layer.canvas_id)
            : null;
        const height = canvas
            ? Number(canvas.raster_height) || 0
            : Number(this.project && this.project.raster_height) || 0;
        return height > 0 ? height : 0;
    }

    // v0.11.0: capacity of one NovaStar Low Latency port, given the topmost
    // canvas Y of its visible cabinets. Every NovaStar line calls this now -
    // top alignment is a requirement of the mode itself, not a COEX extra.
    // `total` is the plain table lookup at the current bit depth and frame
    // rate - never a fixed constant, so the derate tracks 8/10/12-bit and the
    // frame rate like everything else.
    // Y = 0 (a top-aligned port, which is what a correctly built layout gives)
    // returns `total` untouched. An unknown canvas height derates NOTHING.
    lowLatencyPortCapacity(total, minY, canvasHeight) {
        if (!(total > 0)) return 0;
        if (!(canvasHeight > 0)) return total;
        const factor = Math.min(1, Math.max(0, 1 - ((Number(minY) || 0) / canvasHeight)));
        return Math.floor(factor * total);
    }

    // v0.11.0: NovaStar 5G's minimum Ethernet-port load width, in pixels, or 0
    // for every other processor - which is to say "this rule does not exist
    // there", not "the threshold happens to be zero".
    //
    // PROVENANCE, so nobody widens this later: NovaStar publish the note under
    // the "Ethernet Port Load Capacity" table on their 5G page (XA50 Pro /
    // CA50E receiving cards) and NOWHERE else -
    //   "The load capacity of a single Ethernet port can only achieve its
    //    maximum when the load width is 128 pixels or more. If the load width
    //    is less than that, the load capacity will be reduced accordingly,
    //    calculated as (128 - load width) x load height."
    // It is deliberately NOT applied to novastar-armor, novastar-coex-1g,
    // brompton, megapixel-1g or megapixel-2.5g. The owner has rejected
    // extending it to those lines, including on a "it is the conservative
    // direction" argument: the rule is not published for them, and inventing
    // it would under-report their capacity and add ports to a live show for no
    // reason. Change the processor key here only against a published source.
    novastarMinLoadWidth(processorType) {
        return processorType === 'novastar-5g' ? 128 : 0;
    }

    // v0.11.0: `capacity` less the 5G minimum-load-width penalty, for a port
    // whose VISIBLE cabinets span `width` x `height` pixels.
    //
    // "load width" is the ETHERNET PORT'S load width - the horizontal pixel
    // extent of the cabinets carried on that port - not one cabinet's width.
    // A port carrying two 60 x 120 cabinets side by side is 120 px wide, so
    // 120 < 128 and it IS penalised.
    //
    // Physically the controller reserves a band at least 128 px wide: a port
    // filling only 120 px of it wastes (128 - 120) x height, and the usable
    // capacity drops by exactly that wasted area. Same "reserved area" idea as
    // the Armor bounding-rectangle rule. Clamped at 0 - a port narrow and tall
    // enough to eat the whole figure carries nothing, not a negative.
    minLoadWidthPortCapacity(capacity, processorType, width, height) {
        const minWidth = this.novastarMinLoadWidth(processorType);
        if (!(minWidth > 0) || !(capacity > 0)) return capacity;
        const w = Number(width) || 0;
        const h = Number(height) || 0;
        if (!(w > 0) || !(h > 0) || w >= minWidth) return capacity;
        return Math.max(0, capacity - ((minWidth - w) * h));
    }

    // Calculate port capacity using lookup tables with interpolation
    // v0.11.0: `lowLatency` layers the processor's Low Latency behaviour on
    // top of the raw lookup. Split in two so pass 2, which needs per-port
    // geometry, has a seam that does not disturb the table lookup.
    calculatePortCapacity(bitDepth, frameRate, processorType, lowLatency = false) {
        const capacity = this.lookupPortCapacity(bitDepth, frameRate, processorType);
        return this.applyLowLatencyCapacity(capacity, processorType, lowLatency);
    }

    // Raw manufacturer-table lookup, before any Low Latency behaviour.
    lookupPortCapacity(bitDepth, frameRate, processorType) {
        processorType = processorType || 'novastar-armor';
        const table = this.portCapacityTables[processorType];
        
        if (!table) return 0;
        
        // Find closest bit depth
        const availableBitDepths = Object.keys(table).map(Number);
        let useBitDepth = bitDepth;
        if (!table[bitDepth]) {
            // Find closest available bit depth (prefer higher for safety)
            useBitDepth = availableBitDepths.reduce((best, bd) => 
                Math.abs(bd - bitDepth) < Math.abs(best - bitDepth) ? bd : best
            );
        }
        
        const fpsTable = table[useBitDepth];
        if (!fpsTable) return 0;
        
        // Exact match
        const exactFps = Math.round(frameRate);
        if (fpsTable[exactFps]) return fpsTable[exactFps];
        
        // Interpolate between two closest frame rates
        const fpsList = Object.keys(fpsTable).map(Number).sort((a, b) => a - b);
        
        // Find surrounding entries
        let lower = fpsList[0];
        let upper = fpsList[fpsList.length - 1];
        
        for (let i = 0; i < fpsList.length - 1; i++) {
            if (fpsList[i] <= frameRate && fpsList[i + 1] >= frameRate) {
                lower = fpsList[i];
                upper = fpsList[i + 1];
                break;
            }
        }
        
        // Below the table: clamp UP to the lowest published row. Capacity runs
        // as 1/frame rate, so the lowest published row is LESS capacity than a
        // slower frame rate really has - the conservative direction, more
        // ports than needed and never fewer. It is also the only way 23.976 Hz
        // (offered in the frame rate list, below every table's 24 Hz first
        // row) has an answer at all, and the tables round it to 24 anyway.
        if (frameRate <= fpsList[0]) return fpsTable[fpsList[0]];
        // ABOVE the table: no capacity. DANGEROUS as it stood - this clamped
        // to the LAST row, so novastar-armor (no row past 120 Hz) answered a
        // 240 Hz question with its 120 Hz figure: double the real capacity and
        // therefore half the ports. The group settings dialog can produce
        // exactly that state, because processor, bit depth and frame rate are
        // picked independently of one another.
        //
        // Nothing is extrapolated to replace it. The manufacturer's published
        // table is authoritative and no figure in this app is derived from a
        // formula, so a frame rate the manufacturer does not publish for this
        // processor has no answer - and 0 is the value the UI already treats
        // as "no capacity": Pixels/Port renders "N/A", Panels/Port renders
        // ERROR, Ports Required renders ERROR, and calculatePortAssignments
        // returns no assignment rather than a plausible map. Loud and empty
        // beats quiet and wrong. Use getSupportedFrameRates to see what a
        // processor actually publishes.
        if (frameRate > fpsList[fpsList.length - 1]) return 0;
        
        // Linear interpolation
        const lowerCap = fpsTable[lower];
        const upperCap = fpsTable[upper];
        const ratio = (frameRate - lower) / (upper - lower);
        return Math.floor(lowerCap + (upperCap - lowerCap) * ratio);
    }
    
    // Check if processor uses rectangle-based port assignment (NovaStar Armor only)
    usesRectangleConstraint(processorType) {
        return processorType === 'novastar-armor';
    }
    
    // v0.11.0: keep the Low Latency checkbox and its note in step with the
    // selected layer's processor. The note is the descriptor's own text; when
    // the behaviour is a pass-2 geometric one the note says the constraint is
    // NOT in the figures, so nobody reads an unchanged Pixels/Port as proof
    // that low latency has been accounted for.
    //
    // Three things sit in this area and they each say ONE thing, once:
    //   #low-latency-note        - beside the checkbox, what turning Low
    //                              Latency ON would cost. Shown only while it
    //                              is OFF, because once it is on the rules list
    //                              says the same thing properly and at length.
    //   #low-latency-rules       - under the readout, the rules in force for
    //                              this processor. Shown only while ON.
    //   #low-latency-derate-note - under the rules, what the derate is costing
    //                              THIS screen right now. Shown only when a
    //                              port is actually being derated.
    // Two of the three can be on screen at a time and they never overlap.
    updateLowLatencyUI() {
        const checkbox = document.getElementById('low-latency');
        const note = document.getElementById('low-latency-note');
        // The derate note below the figures is re-stated by
        // updatePortCapacityDisplay once the ports are known; clear it here so
        // it cannot survive that function's early returns on a stale layer.
        this.setLowLatencyDerateNote(null);
        // Same reason: a stale layer's rules must not outlive it.
        this.setLowLatencyRules(null);
        if (!checkbox && !note) return;

        const layer = this.currentLayer;
        const isScreen = !!layer && (layer.type || 'screen') === 'screen';
        const processorType = (isScreen && layer.processorType) || 'novastar-armor';
        const profile = isScreen ? this.getLowLatencyProfile(processorType) : null;
        const supported = !!(profile && profile.supported);
        const enabled = !!(isScreen && layer.lowLatency && supported);

        if (checkbox) {
            checkbox.checked = !!(isScreen && layer.lowLatency);
            checkbox.disabled = !supported;
        }
        if (note) {
            // v0.11.0: stand down once the rules list is up. This note used to
            // show in both states, which put a short version of the rules
            // directly above the long version and read as two half-answers.
            let text = (supported && !enabled) ? (profile.note || '') : '';
            if (text && this.isLowLatencyCapacityPending(processorType)) {
                text += ' Not applied to the figures below yet.';
            }
            note.textContent = text;
            // v0.11.0: the receiving-card list is a tooltip - too long for the
            // note itself, and the MRV328/MRV336 trap is already in the note.
            // Set in both states: the rules list carries the same tooltip on
            // its own card line, and this one is what the checkbox row offers.
            note.title = supported ? (profile.cards || '') : '';
        }
        if (enabled) this.setLowLatencyRules(profile);
    }

    // v0.11.0: list the Low Latency rules in force for the selected layer's
    // processor, directly under the Pixels/Port readout - the one figure that
    // cannot show them. That figure is the flat table lookup for the whole
    // layer, so it carries neither the per-port (1 - Y/H) derate nor the 5G
    // narrow-port penalty, and on its own it can disagree with the per-port
    // percentages on the canvas. This list is what reconciles the two.
    //
    // `profile` is the lowLatencyProfiles entry, or null to clear (Low Latency
    // off, no layer, an image layer, or a stale processor with no entry).
    //
    // DISPLAY ONLY. Every rule here is already in the math - see
    // applyLowLatencyCapacity ('factor' / 'none'), lowLatencyPortCapacity
    // ((1 - Y/H)) and minLoadWidthPortCapacity (the 128 px penalty). The 128 px
    // rule appears only on the entry whose novastarMinLoadWidth is non-zero, so
    // the UI's scope is the math's scope rather than a rule invented for the
    // other lines.
    setLowLatencyRules(profile) {
        const el = document.getElementById('low-latency-rules');
        if (!el) return;
        const rules = (profile && Array.isArray(profile.rules)) ? profile.rules : [];
        el.textContent = '';
        if (rules.length === 0) {
            el.style.display = 'none';
            return;
        }
        rules.forEach(rule => {
            const item = document.createElement('li');
            item.textContent = (rule && rule.text) || '';
            if (rule && rule.tip) item.title = rule.tip;
            el.appendChild(item);
        });
        el.style.display = '';
    }

    // v0.11.0: say WHY a Low Latency port count moved. Pixels/Port is the
    // port's TOTAL; a NovaStar port that does not start at canvas Y=0 keeps
    // only (1 - Y/H) of it, so without this line nudging a screen down the
    // canvas would silently change Ports Required and read as a bug. `derate`
    // is layer._lowLatencyDerate - null whenever nothing was derated, and then
    // the line is cleared.
    setLowLatencyDerateNote(derate) {
        const el = document.getElementById('low-latency-derate-note');
        if (!el) return;
        if (!derate || !(derate.deratedPorts > 0)) {
            el.textContent = '';
            el.style.display = 'none';
            return;
        }
        const verb = derate.deratedPorts === 1 ? 'port starts' : 'ports start';
        el.textContent = `Low Latency: ${derate.deratedPorts} of ${derate.totalPorts} `
            + `${verb} below the top of the ${derate.canvasHeight.toLocaleString()} px `
            + `canvas, so capacity there drops to as little as `
            + `${derate.worstCapacity.toLocaleString()} px, from `
            + `${derate.portCapacity.toLocaleString()} px.`;
        el.style.display = '';
    }

    // Update bit depth dropdown options based on selected processor
    updateBitDepthOptions() {
        const bitDepthSelect = document.getElementById('bit-depth');
        if (!bitDepthSelect || !this.currentLayer) return;
        
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const supported = this.getSupportedBitDepths(processorType);
        const currentBitDepth = this.currentLayer.bitDepth || 8;
        
        // Update options
        bitDepthSelect.innerHTML = '';
        supported.forEach(bd => {
            const opt = document.createElement('option');
            opt.value = bd;
            opt.textContent = `${bd}-bit`;
            bitDepthSelect.appendChild(opt);
        });
        
        // If current bit depth is still valid, keep it; otherwise pick the first
        if (supported.includes(currentBitDepth)) {
            bitDepthSelect.value = currentBitDepth;
        } else {
            bitDepthSelect.value = supported[0];
            this.currentLayer.bitDepth = supported[0];
        }
    }
}

for (const k of Object.getOwnPropertyNames(_ScreenInfo.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ScreenInfo.prototype, k));
    }
}
