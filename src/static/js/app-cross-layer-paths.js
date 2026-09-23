// app-cross-layer-paths: cross-member manual paths for LEDRasterApp - the
// scope a hand-drawn port or circuit may reach, how a path step names a
// peer member's cabinet, and how a step resolves back to a cabinet (or
// reads as dangling). Also the owner lookups a conflicting click asks.
import { LEDRasterApp } from './app-core.js';

class _CrossLayerPaths {

    // ── Cross-member manual paths (v0.11.0, step 6) ──────────────────────
    //
    // A group IS ONE WALL, so a hand-drawn port path or power circuit has to
    // be allowed to run off one member and onto the next. The path itself
    // never moves: it stays on the layer that OWNS the port or circuit -
    // a port is a physical output on ONE processor - and only the individual
    // step learns where the cable landed.
    //
    //     {row, col}            a panel in the OWNING layer. Unchanged, and
    //                           the shape 100% of existing projects have.
    //     {row, col, layerId}   a panel in a PEER member of the same group.
    //
    // Why a key on the STEP rather than a new key on the layer: the server's
    // add / update allow-lists silently DROP layer keys they do not know,
    // which has already cost this codebase two features (processorType,
    // lowLatency). A step lives inside customPortPaths, which is already
    // allow-listed, so it rides in for free.
    //
    // Why (layerId, row, col) rather than panel.id: _build_panels regenerates
    // panel ids on every geometry rebuild, so an id is worthless the moment
    // anyone changes a column count. (row, col) is the only durable address.
    //
    // Every helper below returns the ungrouped answer for an ungrouped layer,
    // and a path with no layerId anywhere reads exactly as it did before, so a
    // project without groups takes precisely the code path it took before.

    // The canvas a manual path treats a layer as living on. Paths are only
    // ever drawn in Data Flow and Power, which are both Show Look views, so
    // the show override is the right answer REGARDLESS of which tab is open.
    // Deliberately NOT canvasRenderer._effectiveLayerCanvasId, which flips
    // with viewMode: reachability that changed the moment the user clicked the
    // Pixel Map tab would mean the same stored step resolving on one tab and
    // reading as dangling on another.
    _pathCanvasIdOf(layer) {
        if (!layer) return null;
        return layer.show_canvas_id || layer.canvas_id || null;
    }

    // Every layer a path owned by `layer` may legally touch. The owner is
    // always first, so callers that want "the owner, then its peers" get a
    // stable order without re-sorting.
    getPathScopeLayers(layer) {
        if (!layer) return [];
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return [layer];
        const cid = this._pathCanvasIdOf(layer);
        const scope = [layer];
        (this.getGroupMembers(group) || []).forEach(m => {
            if (!m || m.id === layer.id) return;
            if ((m.type || 'screen') !== 'screen') return;
            // The same rule canvas.js _groupDrawnMembers applies: a member
            // sitting on another canvas is a different workspace entirely, so
            // a cable drawn onto it would be drawn at a position that means
            // nothing. Hidden members are NOT excluded here (where
            // _groupDrawnMembers does exclude them) - hiding a screen must not
            // quietly invalidate paths the user already drew onto it, because
            // unhiding has to bring them straight back.
            if (this._pathCanvasIdOf(m) !== cid) return;
            scope.push(m);
        });
        return scope;
    }

    // ---- Clearing hand-drawn runs on a grouped screen -----------------------
    //
    // A group is one wall, and a run a member owns may sit on a peer's
    // cabinets: the owner is whichever screen was current when it was drawn.
    // Clear Circuit / Clear Port and Clear All used to reach only the current
    // layer's own runs, so a run a peer drew across this screen stayed put with
    // nothing on this screen able to remove it (Matt, 2026-09-22, the Orlando
    // file: SL's circuit 1 was 13 cabinets of SR - "S1-1 can't be cleared ...
    // nor have a way to delete it").
    //
    // clearCustomRun: the current layer's run `num` goes, and every peer's run
    // `num` loses the entries that land on this layer (a peer run emptied that
    // way is removed). clearAllCustomRuns: every member of the path scope drops
    // all its runs and overrides - the wall is back to automatic. Both return
    // the layers written, for the PUT (_persistWith adds them to the selection).
    _customRunKeys(kind) {
        return kind === 'power'
            ? { paths: 'powerCustomPaths', index: 'powerCustomIndex',
                overrides: 'powerCustomOverrides', ensure: 'ensureCustomPowerState' }
            : { paths: 'customPortPaths', index: 'customPortIndex',
                overrides: 'customPortOverrides', ensure: 'ensureCustomFlowState' };
    }

    clearCustomRun(layer, kind, num) {
        if (!layer) return [];
        const k = this._customRunKeys(kind);
        this[k.ensure](layer);
        layer[k.paths][num] = [];
        const touched = [layer];
        this.getPathScopeLayers(layer).forEach(peer => {
            if (!peer || peer.id === layer.id) return;
            const paths = peer[k.paths];
            if (!paths || !Array.isArray(paths[num]) || paths[num].length === 0) return;
            const kept = paths[num].filter(e => this.getPathEntryLayerId(peer, e) !== layer.id);
            if (kept.length === paths[num].length) return;
            if (kept.length) paths[num] = kept; else delete paths[num];
            touched.push(peer);
        });
        return touched;
    }

    clearAllCustomRuns(layer, kind) {
        if (!layer) return [];
        const k = this._customRunKeys(kind);
        const touched = [];
        this.getPathScopeLayers(layer).forEach(member => {
            if (!member) return;
            this[k.ensure](member);
            member[k.paths] = {};
            member[k.index] = 1;
            member[k.overrides] = [];
            if (this._overrideEditing && this._overrideEditing.kind === kind
                    && this._overrideEditing.layerId === member.id) {
                this._overrideEditing = null;
            }
            touched.push(member);
        });
        return touched;
    }

    _persistWith(touched) {
        const sel = this.getSelectedLayers() || [];
        const ids = new Set(sel.map(l => l && l.id));
        return sel.concat((touched || []).filter(l => l && !ids.has(l.id)));
    }

    // The layers a SELECTION owned by `layer` may touch: the path scope, less
    // the members the user cannot see.
    //
    // getPathScopeLayers deliberately keeps hidden members, because a path
    // already drawn onto a screen must survive that screen being hidden and
    // come straight back when it is unhidden. That is right for RESOLVING a
    // path and wrong for BUILDING one: a hidden member is not drawn
    // (canvas.js _groupDrawnMembers filters visible !== false) and cannot be
    // clicked (getPanelAt skips it), so a marquee, an arrow handoff or an
    // Apply Pattern that reached it wired cabinets nobody could see - 12 of
    // them, on a screen that is not on the canvas, into the visible screen's
    // port 1.
    //
    // The OWNER is never filtered out. It is the layer the user is working on
    // and the port belongs to it; dropping it would make a hidden current
    // layer un-drawable rather than merely un-reachable, and it keeps an
    // ungrouped screen byte-identical to before.
    //
    // `visible === false`, not `!visible`: a layer with no visible key is
    // visible everywhere else in this app (the server reads
    // layer.get('visible', True)).
    getSelectionScopeLayers(layer) {
        if (!layer) return [];
        return this.getPathScopeLayers(layer)
            .filter(l => l && (l.id === layer.id || l.visible !== false));
    }

    canPathReachLayer(ownerLayer, targetLayer) {
        if (!ownerLayer || !targetLayer) return false;
        if (ownerLayer.id === targetLayer.id) return true;
        return this.getPathScopeLayers(ownerLayer).some(l => l && l.id === targetLayer.id);
    }

    // The layer id a step names, resolving the plain form to the owner. Kept
    // separate from resolvePathEntryLayer because the conflict scan wants the
    // id without paying for a lookup and a legality check per step.
    getPathEntryLayerId(ownerLayer, entry) {
        const lid = entry ? entry.layerId : undefined;
        if (lid === undefined || lid === null) return ownerLayer ? ownerLayer.id : null;
        return lid;
    }

    resolvePathEntryLayer(ownerLayer, entry) {
        if (!ownerLayer || !entry) return null;
        const lid = entry.layerId;
        if (lid === undefined || lid === null || lid === ownerLayer.id) return ownerLayer;
        const target = ((this.project && this.project.layers) || [])
            .find(l => l && l.id === lid) || null;
        if (!target) return null;
        // A pointer at a layer that exists but is no longer a reachable peer
        // (ungrouped, regrouped, or dragged onto another canvas) is dead, not
        // drawable. The server prunes it on the next round-trip; until then
        // reading it as null keeps the renderer from drawing a cable onto an
        // unrelated screen.
        return this.canPathReachLayer(ownerLayer, target) ? target : null;
    }

    resolvePathEntry(ownerLayer, entry) {
        const layer = this.resolvePathEntryLayer(ownerLayer, entry);
        if (!layer || !entry) return null;
        const panel = this.getPanelByRowCol(layer, entry.row, entry.col);
        if (!panel) return null;
        return { layer, panel };
    }

    // Hidden panels are dropped HERE rather than by each caller, matching the
    // read-time `.filter(p => p && !p.hidden)` every path consumer already ran
    // before a step could name a peer.
    getResolvedPathPanels(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return [];
        const out = [];
        path.forEach(entry => {
            const resolved = this.resolvePathEntry(ownerLayer, entry);
            if (resolved && !resolved.panel.hidden) out.push(resolved);
        });
        return out;
    }

    // layerId is written ONLY when it differs from the owner, so a path that
    // never leaves its own screen is byte-for-byte the shape it has always
    // been. (The server's prune pass normalises a self-pointer the same way,
    // so the two sides can never drift into writing different files.)
    makePathEntry(ownerLayer, panelLayer, panel) {
        if (!panel) return null;
        const entry = { row: panel.row, col: panel.col };
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            entry.layerId = panelLayer.id;
        }
        return entry;
    }

    // The address of ONE cabinet on the wall. Path ownership, path dedupe and
    // (since v0.11.0's marquee) customSelection / powerCustomSelection are all
    // keyed on this, because inside a group `${row},${col}` names two cabinets
    // at once and every one of those jobs has to tell them apart.
    //
    // getPanelKey stays `${row},${col}` regardless: pixelMapSelection still
    // uses it - one screen, nothing grouped about it - and its overlay parses
    // the key back with `key.split(',').map(parseInt)`, which a layer id in
    // front would turn into the WRONG panel silently, with no error anywhere.
    getScopedPanelKey(layerId, panel) {
        return `${layerId}:${panel.row},${panel.col}`;
    }

    pathCrossesMembers(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return false;
        return path.some(e => e && e.layerId !== undefined && e.layerId !== null
            && e.layerId !== ownerLayer.id);
    }

    // Which layer does this panel object belong to, as far as a path owned by
    // `ownerLayer` is concerned? Null when the panel is not reachable at all.
    // Identity first - the click handler and the arrow keys both hand us the
    // panel straight out of a layer's own array - and the (row, col) fallback
    // is what keeps a caller that rebuilt the panel behaving exactly as before.
    _resolvePathPanelLayer(ownerLayer, panel, explicitLayer) {
        if (!ownerLayer || !panel) return null;
        if (explicitLayer) {
            return this.canPathReachLayer(ownerLayer, explicitLayer) ? explicitLayer : null;
        }
        const scope = this.getPathScopeLayers(ownerLayer);
        const byIdentity = scope.find(l => l && Array.isArray(l.panels)
            && l.panels.includes(panel));
        if (byIdentity) return byIdentity;
        return this.getPanelByRowCol(ownerLayer, panel.row, panel.col) ? ownerLayer : null;
    }

    _pathLayerName(layer) {
        if (!layer) return 'another screen';
        return layer.name || `Screen ${layer.id}`;
    }

    // "port 2", or "port 2 on North Lower" when the conflict lives on a peer.
    // R3C4 alone stops meaning anything the moment two grids are in play, so
    // a toast that names only the number sends the user hunting.
    _describePathConflict(conflict, kind) {
        if (!conflict) return '';
        const base = `${kind} ${conflict.number}`;
        return conflict.foreign ? `${base} on ${this._pathLayerName(conflict.layer)}` : base;
    }

    _describePathPanel(ownerLayer, panelLayer, panel) {
        const base = `R${panel.row + 1}C${panel.col + 1}`;
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            return `${base} on ${this._pathLayerName(panelLayer)}`;
        }
        return base;
    }

    /**
     * Which port / circuit (if any) already owns this cabinet, anywhere in the
     * owner's path scope. Returns {number, layer, layerId, foreign} or null.
     *
     * `foreign` is the whole reason this returns an object rather than the
     * bare number it used to: with a group in play the answer may live on a
     * different screen, and the caller has to be able to say which.
     */
    _findPathOwner(ownerLayer, panel, excludeNum, panelLayer, pathsKey) {
        if (!ownerLayer || !panel) return null;
        const source = panelLayer || ownerLayer;
        const key = this.getScopedPanelKey(source.id, panel);
        for (const scope of this.getPathScopeLayers(ownerLayer)) {
            const paths = scope && scope[pathsKey];
            if (!paths) continue;
            for (const numStr of Object.keys(paths)) {
                // Number("0") is 0, which is falsy - the old `Number(s) || s`
                // handed back the STRING "0" and then failed to match a
                // numeric exclude. Ports and circuits are 1-based so it never
                // bit anyone, but a quirk that only works because a value is
                // impossible is a trap for whoever changes that.
                const parsed = Number(numStr);
                const num = Number.isFinite(parsed) ? parsed : numStr;
                // Only the port being drawn RIGHT NOW is exempt, and only on
                // its own layer: port 1 of member A and port 1 of member B are
                // two different physical outputs (getGroupTotals sums each
                // member's own requirement), so a cabinet already claimed by
                // the peer's port 1 genuinely is taken.
                if (scope.id === ownerLayer.id && num === excludeNum) continue;
                const path = paths[numStr] || [];
                const hit = path.some(e => e && this.getScopedPanelKey(
                    this.getPathEntryLayerId(scope, e), e) === key);
                if (hit) {
                    return {
                        number: num,
                        layer: scope,
                        layerId: scope.id,
                        foreign: scope.id !== ownerLayer.id,
                    };
                }
            }
        }
        return null;
    }

    /**
     * The OTHER port (if any) that already owns this panel. Scans every layer
     * in the owner's path scope, not just the owner's own paths, so a cabinet
     * claimed by a port drawn from member A is seen as taken while drawing
     * from member B.
     */
    _findPanelOwnerPort(layer, panel, excludePortNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludePortNum, panelLayer, 'customPortPaths');
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludeCircuitNum, panelLayer, 'powerCustomPaths');
    }
}

for (const k of Object.getOwnPropertyNames(_CrossLayerPaths.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CrossLayerPaths.prototype, k));
    }
}
