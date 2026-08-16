// app-screen-groups: feature methods for LEDRasterApp, attached to the
// prototype via the carrier class.
//
// ── Screen groups (v0.11.0), step 3: the Screens sidebar ─────────────────
//
// A group IS A SINGLE LAYER. It is one wall that happens to be built from two
// cabinet sizes: the per-layer grid is uniform, so a wall of 1m JP5 cabinets
// AND 0.5m standard cabinets HAS to be two layers - but the user built one
// wall, and everything they do to it should treat it as one.
//
// That is why the sidebar shows ONE ROW per group, carrying the group's name
// and its combined figures (from getGroupTotals, step 2), with a disclosure
// arrow to expand to the members when one of them actually needs editing.
// Collapsed is the default, because the members are an implementation detail
// of how the wall was built, not the thing the user is managing.
//
// The same rule drives the rest of the file:
//   * visibility, lock, delete, duplicate and z-order act on the WHOLE group
//   * Screen Info edits propagate to every member for the settings a wall can
//     share (see GROUP_SHARED_LAYER_FIELDS below - the per-member fields are
//     the ones that describe an individual cabinet grid: its cabinet size,
//     columns, rows, position and per-cabinet weight/watts)
//   * a group's members can never end up separated in the layer list by an
//     unrelated screen
//
// Inline rename, the ⋮ actions menu and the popup wiring still follow the
// canvas-group precedent in app-canvas-ui.js (buildCanvasGroupEl /
// _wireCanvasGroupEl / openCanvasMenu), because that is how this app already
// names and acts on a thing in the Screens list.
//
// Persistence: every mutation writes BOTH sides of the relationship
// (project.groups[n].layer_ids and layer.group_id) and then PUTs the whole
// project. /api/project (restore_project) is the one funnel that runs
// _enforce_group_integrity, so the SERVER decides what a membership that
// disagrees with itself repairs to - none of that logic is repeated here.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ScreenGroups {

    // The settings every member must agree on BEFORE it can be a group.
    // A group is one screen, so a port crossing a member boundary needs a
    // single rule set to be checked against. These are what the mismatch
    // dialog resolves.
    //
    // lowLatency is here for the same reason bit depth is: it is a
    // PROCESSOR-WIDE mode, not a per-cabinet dressing. Two Brompton members
    // that disagree about it sit at 525,000 and 262,500 px/port, and a port
    // drawn across the boundary is then judged at whichever figure the owning
    // member happens to carry - one wall, two capacities, no error. It is also
    // in GROUP_SHARED_LAYER_FIELDS below, but that list only propagates on an
    // EDIT; without an entry here nothing checks it at creation.
    //
    // app.py's GROUP_SHARED_SETTINGS is the server's copy of this list. It is
    // only read by validate_group_settings, which no route calls today, so the
    // two being out of step cannot contradict a decision - but they should be
    // brought back into line the next time that file is touched.
    // powerVoltage is here because a GROUP is one wall, and one wall runs on
    // one supply. Two sections of the same wall on 110 V and 208 V is a wiring
    // error, not a configuration - so it is resolved at the point of grouping
    // like bit depth, rather than reported forever as "Mixed voltage" with no
    // way to answer it. (A PROJECT may legitimately span voltages: two walls,
    // two supplies. That case is handled the other way round - getPowerCounts
    // refuses to blend them and reports each voltage separately.)
    get GROUP_SHARED_SETTINGS() {
        return ['processorType', 'bitDepth', 'frameRate', 'lowLatency', 'powerVoltage'];
    }

    // Fields a Screen Info edit propagates to every member, because they
    // describe THE WALL rather than one cabinet grid inside it.
    //
    // Everything NOT in this list stays per member, and the omissions are
    // deliberate:
    //   columns / rows / cabinet_width / cabinet_height / panel_width_mm /
    //   panel_height_mm   the grid itself - the whole reason the wall needed
    //                     more than one layer
    //   panel_weight / panelWatts   per-CABINET figures. A 1m JP5 and a 0.5m
    //                     standard cabinet do not weigh or draw the same, and
    //                     getGroupTotals sums each member's own figure
    //   offset_x / offset_y / showOffsetX / showOffsetY / rotation   position.
    //                     The members sit at different places BY DESIGN; the
    //                     canvas already drags them as one
    //   sizeByDimensions / targetWidth / targetHeight / targetUnit   these
    //                     derive columns/rows, so they are grid, not wall
    //   panels            per-panel blank / hidden / half-tile state
    //   customPortPaths / customPortIndex / powerCustomPath /
    //   portLabelOverrides*   hand-drawn per-grid paths (cross-member paths
    //                     are explicitly out of scope)
    //   screenName*Offset*   label POSITIONS. The canvas draws one label per
    //                     group from the first member's config, so a peer's
    //                     stored offset must not be overwritten
    //   name / visible / locked / group_id / canvas_id   identity, and the
    //                     whole-group actions below own the rest
    get GROUP_SHARED_LAYER_FIELDS() {
        return [
            // Processor / data
            'processorType', 'lowLatency', 'bitDepth', 'frameRate',
            'portMappingMode', 'flowPattern',
            'portLabelTemplatePrimary', 'portLabelTemplateReturn',
            'showDataFlowPortInfo', 'showDataFlowPortLoad',
            'dataFlowColor', 'dataFlowLabelSize',
            'arrowColor', 'arrowLineWidth', 'arrowSize',
            'primaryColor', 'primaryTextColor', 'backupColor',
            'backupTextColor', 'randomDataColors',
            // Power
            'powerVoltage', 'powerVoltageCustom', 'powerAmperage',
            'powerAmperageCustom', 'powerMaximize', 'powerOrganized',
            'powerFlowPattern', 'powerLineWidth', 'powerLineColor',
            'powerArrowColor', 'powerRandomColors', 'powerColorCodedView',
            'powerCircuitColors', 'powerLabelBgColor', 'powerLabelTextColor',
            'powerLabelSize', 'powerLabelTemplate', 'showPowerCircuitInfo',
            // Cabinet fill / borders
            'color1', 'color2', 'transparentFill',
            'gradientEnabled', 'gradientType', 'gradientScope',
            'gradientPanelAlternate', 'gradientAngle', 'gradientOpacity',
            'gradientBlend', 'gradientStops', 'gradientRadialCenterX',
            'gradientRadialCenterY', 'gradientRadialRadius',
            'panelColorMode', 'panelColors',
            'show_panel_borders', 'show_circle_with_x', 'panel_border_width',
            'border_color', 'border_color_pixel', 'border_color_cabinet',
            'border_color_data', 'border_color_power',
            // Labels and readouts
            'showLabelName', 'showLabelSizePx', 'showLabelSizeM',
            'showLabelSizeFt', 'showLabelInfo', 'showLabelWeight',
            'labelsColor', 'labelsFontSize', 'infoLabelSize',
            'useFractionalInches',
            'showOffsetTL', 'showOffsetTR', 'showOffsetBL', 'showOffsetBR',
            'screenNameSize', 'screenNameSizeCabinet',
            'screenNameSizeDataFlow', 'screenNameSizePower',
            'show_numbers', 'number_size',
            'cabinetIdColor', 'cabinetIdPosition', 'cabinetIdStyle',
            'weight_unit',
        ];
    }

    // ── selection helpers ────────────────────────────────────────────────

    // Screen layers in the current selection. Images and text can never be
    // group members - the totals roll-up already counts them as skipped.
    getSelectedScreenLayers() {
        return (this.getSelectedLayers() || [])
            .filter(l => l && (l.type || 'screen') === 'screen');
    }

    // Group ids the current selection touches, first-seen order.
    getSelectedGroupIds() {
        const ids = [];
        this.getSelectedScreenLayers().forEach(layer => {
            if (!layer.group_id || ids.includes(layer.group_id)) return;
            if (this.resolveGroup(layer.group_id)) ids.push(layer.group_id);
        });
        return ids;
    }

    getGroupOfLayer(layer) {
        if (!layer || !layer.group_id) return null;
        return this.resolveGroup(layer.group_id);
    }

    // Grouping needs 2+ screens (a group of one is not a group - the same
    // rule _enforce_group_integrity applies server-side), and there is
    // nothing to make when the selection is already exactly one whole group.
    canGroupSelection() {
        const screens = this.getSelectedScreenLayers();
        if (screens.length < 2) return false;
        const groupIds = this.getSelectedGroupIds();
        if (groupIds.length === 1 && screens.every(l => l.group_id === groupIds[0])) {
            const group = this.resolveGroup(groupIds[0]);
            if (group && (group.layer_ids || []).length === screens.length) return false;
        }
        return true;
    }

    // ── shared-settings propagation ──────────────────────────────────────
    //
    // A group is one screen, so a Screen Info edit to any member is an edit to
    // the wall. Rather than teach ~70 individual control handlers about
    // groups, both edit funnels (applyToSelectedLayers and
    // updateLayerFromInputs) snapshot the shared fields, run their existing
    // work, and then copy across only the fields that ACTUALLY CHANGED.
    //
    // Diffing rather than blanket-copying matters: nudging one member's offset
    // must not silently repaint its peers just because the two happened to
    // disagree on a colour before they were ever grouped.

    _snapshotSharedFields(layers) {
        const snapshot = new Map();
        (layers || []).forEach(layer => {
            if (!layer || !layer.group_id || !this.resolveGroup(layer.group_id)) return;
            const values = {};
            this.GROUP_SHARED_LAYER_FIELDS.forEach(field => {
                values[field] = JSON.stringify(
                    layer[field] === undefined ? null : layer[field]);
            });
            snapshot.set(layer.id, values);
        });
        return snapshot;
    }

    _cloneFieldValue(value) {
        if (value === null || value === undefined || typeof value !== 'object') return value;
        return JSON.parse(JSON.stringify(value));
    }

    // Returns the peer layers that were written to, and remembers them so the
    // next updateLayers() carries them to the server in the SAME request and
    // the SAME undo step.
    _propagateChangedSharedFields(layers, snapshot) {
        if (!snapshot || snapshot.size === 0) return [];
        const edited = new Set((layers || []).map(l => l && l.id));
        const touched = new Map();
        (layers || []).forEach(layer => {
            const previous = snapshot.get(layer && layer.id);
            if (!previous) return;
            const group = this.getGroupOfLayer(layer);
            if (!group) return;
            const changed = this.GROUP_SHARED_LAYER_FIELDS.filter(field => (
                JSON.stringify(layer[field] === undefined ? null : layer[field])
                !== previous[field]
            ));
            if (changed.length === 0) return;
            this.getGroupMembers(group).forEach(peer => {
                if (!peer || peer.id === layer.id || edited.has(peer.id)) return;
                changed.forEach(field => {
                    peer[field] = this._cloneFieldValue(layer[field]);
                });
                touched.set(peer.id, peer);
            });
        });
        if (touched.size === 0) return [];
        if (!this._pendingGroupPeerIds) this._pendingGroupPeerIds = new Set();
        touched.forEach((peer, id) => this._pendingGroupPeerIds.add(id));
        sendClientLog('screen_group_shared_edit', { peers: [...touched.keys()] });
        return [...touched.values()];
    }

    // Called by updateLayers() so peers just written by the propagation ride
    // along on the same PUT. Clears the pending set: one edit, one carry.
    _withPendingGroupPeers(layers) {
        const pending = this._pendingGroupPeerIds;
        if (!pending || pending.size === 0) return layers;
        const out = [...(layers || [])];
        const have = new Set(out.map(l => l && l.id));
        pending.forEach(id => {
            if (have.has(id)) return;
            const layer = ((this.project && this.project.layers) || [])
                .find(l => l.id === id);
            if (layer) out.push(layer);
        });
        pending.clear();
        return out;
    }

    // ── model helpers ────────────────────────────────────────────────────

    // Mirrors app._next_group_id: the counter lives ON THE PROJECT, never
    // scans for the highest existing id, so deleting a group can never hand
    // its id back out to a different group. Writing next_group_seq here keeps
    // the server's sync_next_group_seq (which only ever raises it) in step.
    _nextGroupId() {
        if (!this.project) return 'g1';
        let highest = 0;
        ((this.project.groups) || []).forEach(g => {
            const m = /^g(\d+)$/.exec((g && g.id) || '');
            if (m) highest = Math.max(highest, parseInt(m[1], 10));
        });
        const stored = parseInt(this.project.next_group_seq, 10);
        const seq = Math.max(Number.isFinite(stored) ? stored : 0, highest + 1);
        this.project.next_group_seq = seq + 1;
        return `g${seq}`;
    }

    // "Group N" above the highest N already used, so a rename-then-add never
    // produces two groups with the same default name (same shape as the
    // canvas namer in app.py).
    _nextGroupName() {
        let maxN = 0;
        (((this.project) || {}).groups || []).forEach(g => {
            const m = /^Group\s+(\d+)$/.exec(((g && g.name) || '').trim());
            if (m) maxN = Math.max(maxN, parseInt(m[1], 10));
        });
        return `Group ${maxN + 1}`;
    }

    // The smart increment duplicateLayer uses, so a duplicated group reads
    // like a duplicated screen ("Main Wall" -> "Main Wall 1", "Wall2" -> "Wall3").
    _nextDuplicateName(baseName) {
        const match = String(baseName || '').match(/^(.*?)(\d+)$/);
        if (match) return `${match[1]}${parseInt(match[2], 10) + 1}`;
        return `${baseName || 'Copy'} 1`;
    }

    // Take a layer out of whatever group holds it, writing both sides.
    //
    // `onlyGroupId` scopes the detach to ONE group: the layer is removed from
    // that group's layer_ids and loses its group_id only if that is the group
    // it claimed. Every action driven from a specific group's menu passes it,
    // so an action aimed at one wall can never quietly rearrange another.
    _detachLayerFromGroups(layer, onlyGroupId = null) {
        if (!layer) return;
        (((this.project) || {}).groups || []).forEach(group => {
            if (!group || !Array.isArray(group.layer_ids)) return;
            if (onlyGroupId && group.id !== onlyGroupId) return;
            group.layer_ids = group.layer_ids.filter(id => id !== layer.id);
        });
        if (onlyGroupId && layer.group_id !== onlyGroupId) return;
        layer.group_id = null;
    }

    // Take the repaired project the PUT handed back as the new truth.
    //
    // The response is what the SERVER holds after _enforce_group_integrity and
    // _rebuild_layer_geometry_from_panel_states - and every field in it came
    // from the body this client just sent, so nothing client-only is lost by
    // adopting it whole. Adopting only PART of it is what made three separate
    // things wrong at once:
    //   * ungroup kept a cross-member path step the server had already pruned,
    //     and the snapshot taken right after held the client's version;
    //   * so ungroup -> regroup KEPT the wiring with no reload and LOST it
    //     with one - same actions, two outcomes;
    //   * duplicateGroup nudged offset_x/offset_y but deep-copied `panels`
    //     verbatim, and panel x/y are ABSOLUTE. The server re-anchors them;
    //     the client never adopted that, so Duplicate Group drew the copy
    //     exactly on top of the original and looked like it had done nothing.
    //
    // Selection and the current layer are ids, not object identity, so they
    // are re-pointed here rather than left aimed at the discarded copy.
    _adoptRepairedProject(repaired) {
        if (!repaired || !Array.isArray(repaired.layers) || !Array.isArray(repaired.groups)) {
            return false;
        }
        delete repaired._migration_notice;   // transient, response-only
        const currentId = this.currentLayer ? this.currentLayer.id : null;
        this.project = repaired;
        if (typeof this.dedupeProjectLayers === 'function') {
            this.dedupeProjectLayers('screen_group_commit');
        }
        const layers = this.project.layers || [];
        const byId = new Map(layers.map(l => [l.id, l]));
        this.currentLayer = (currentId !== null && byId.has(currentId))
            ? byId.get(currentId)
            : (layers[layers.length - 1] || null);
        if (this.selectedLayerIds) {
            const kept = [...this.selectedLayerIds].filter(id => byId.has(id));
            this.selectedLayerIds = new Set(
                kept.length ? kept : (this.currentLayer ? [this.currentLayer.id] : []));
        }
        if (this.lastSelectedLayerId != null && !byId.has(this.lastSelectedLayerId)) {
            this.lastSelectedLayerId = this.currentLayer ? this.currentLayer.id : null;
        }
        if (this.selectionAnchorLayerId != null && !byId.has(this.selectionAnchorLayerId)) {
            this.selectionAnchorLayerId = this.lastSelectedLayerId;
        }
        return true;
    }

    // Persist the group model and record ONE undo step for the whole action.
    //
    // The PUT goes through /api/project (restore_project), the one funnel
    // that runs _enforce_group_integrity - so the server, not this file,
    // decides what a membership that disagrees with itself repairs to. The
    // whole repaired project is adopted back (see _adoptRepairedProject), and
    // the snapshot is taken AFTER that, so the single history entry holds the
    // repaired state and an undo restores it whole.
    //
    // Two things make that adoption DETERMINISTIC rather than a race:
    //   1. commits are serialized on one promise chain, so a second group
    //      action never has its PUT in flight alongside the first. Without it,
    //      two overlapping commits both send `this.project` and the later
    //      response could be the one built from the STALER body.
    //   2. each issued commit takes a token; a response whose token is no
    //      longer the newest is logged and dropped instead of overwriting a
    //      project a newer commit already adopted.
    // `_groupCommitDepth` is the flag the path sanitiser reads so it cannot
    // prune wiring out of a project that is mid-commit.
    _commitGroupChange(actionLabel) {
        const run = async () => {
            const token = (this._groupCommitSeq = (this._groupCommitSeq || 0) + 1);
            this._groupCommitDepth = (this._groupCommitDepth || 0) + 1;
            let repaired = null;
            try {
                const res = await fetch('/api/project', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.project),
                });
                repaired = await res.json();
            } catch (err) {
                sendClientLog('screen_group_commit_failed', {
                    action: actionLabel, error: String(err),
                });
            } finally {
                this._groupCommitDepth -= 1;
            }
            if (token !== this._groupCommitSeq) {
                sendClientLog('screen_group_commit_superseded', {
                    action: actionLabel, token, current: this._groupCommitSeq,
                });
            } else {
                this._adoptRepairedProject(repaired);
            }
            this.saveState(actionLabel);
            sendClientLog('screen_group_change', {
                action: actionLabel,
                groups: (this.project.groups || []).map(g => ({
                    id: g.id, name: g.name, members: (g.layer_ids || []).length,
                })),
            });
            this.renderLayers();
            if (typeof this.loadLayerToInputs === 'function') {
                try { this.loadLayerToInputs(); } catch (_) { /* inputs are optional here */ }
            }
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const chain = Promise.resolve(this._groupCommitChain || null)
            .catch(() => {})
            .then(run);
        // The stored chain swallows failures so one broken commit cannot wedge
        // every later one; the returned promise still rejects for the caller.
        this._groupCommitChain = chain.catch(() => {});
        return chain;
    }

    // ── membership actions ───────────────────────────────────────────────

    async groupSelectedLayers() {
        const screens = this.getSelectedScreenLayers();
        if (screens.length < 2) return null;
        const chosen = await this._resolveGroupSettings(screens, 'create');
        if (!chosen) return null;  // Cancel groups nothing and changes nothing
        this._applyGroupSettings(screens, chosen);
        screens.forEach(layer => this._detachLayerFromGroups(layer));
        const group = {
            id: this._nextGroupId(),
            name: this._nextGroupName(),
            layer_ids: screens.map(l => l.id),
        };
        if (!Array.isArray(this.project.groups)) this.project.groups = [];
        this.project.groups.push(group);
        screens.forEach(layer => { layer.group_id = group.id; });
        // A group is ONE row in the list, so its members have to be one block
        // in the layer order before that row can be drawn.
        this._reflowGroupBlocks();
        await this._commitGroupChange('Group Screens');
        return group.id;
    }

    async addSelectedToGroup(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        const incoming = this.getSelectedScreenLayers()
            .filter(layer => layer.group_id !== group.id);
        if (incoming.length === 0) return false;
        // The same check runs here as on create: a screen joining a group
        // still has to agree with the screens already in it.
        const all = this.getGroupMembers(group).concat(incoming);
        const chosen = await this._resolveGroupSettings(all, 'add');
        if (!chosen) return false;
        this._applyGroupSettings(all, chosen);
        if (!Array.isArray(group.layer_ids)) group.layer_ids = [];
        incoming.forEach(layer => {
            this._detachLayerFromGroups(layer);
            group.layer_ids.push(layer.id);
            layer.group_id = group.id;
        });
        this._reflowGroupBlocks();
        await this._commitGroupChange('Add to Group');
        return true;
    }

    async ungroupSelectedLayers(groupId = null) {
        const ids = groupId ? [groupId] : this.getSelectedGroupIds();
        if (ids.length === 0) return false;
        (this.project.layers || []).forEach(layer => {
            if (layer && ids.includes(layer.group_id)) layer.group_id = null;
        });
        this.project.groups = ((this.project.groups) || [])
            .filter(group => !(group && ids.includes(group.id)));
        await this._commitGroupChange('Ungroup Screens');
        return true;
    }

    // `groupId` scopes the removal to ONE group - the group whose ⋮ menu the
    // user actually opened. Without it, a selection that spans two walls had
    // every one of its screens pulled out of whichever group held it, from a
    // menu that belongs to one of them and a menu item enabled by that one
    // group alone. Called with no argument (the keyboard/menu-bar path, where
    // there is no group in hand) it still means "out of whatever holds them".
    async removeSelectedFromGroup(groupId = null) {
        const group = groupId ? this.resolveGroup(groupId) : null;
        if (groupId && !group) return false;
        const layers = this.getSelectedScreenLayers().filter(
            l => l.group_id && (!group || l.group_id === group.id));
        if (layers.length === 0) return false;
        layers.forEach(layer => this._detachLayerFromGroups(
            layer, group ? group.id : null));
        // A group left with a single member is dissolved - by the server, on
        // the PUT inside _commitGroupChange. That rule lives in
        // _enforce_group_integrity and is deliberately not repeated here.
        await this._commitGroupChange('Remove from Group');
        return true;
    }

    async renameGroup(groupId, name) {
        const group = this.resolveGroup(groupId);
        const newName = (name || '').trim();
        if (!group || !newName || newName === group.name) return false;
        group.name = newName;
        await this._commitGroupChange('Rename Group');
        return true;
    }

    // ── whole-group actions ──────────────────────────────────────────────

    // One eye for the wall. If any member is showing, the toggle hides them
    // all, so the group can never be left half-drawn.
    async toggleGroupVisibility(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        const members = this.getGroupMembers(group);
        if (members.length === 0) return false;
        const anyVisible = members.some(m => m.visible !== false);
        members.forEach(m => { m.visible = !anyVisible; });
        if (anyVisible) {
            // Same reasoning as toggleLayerVisibility: a hidden layer must
            // leave the selection so nothing can still edit or drag it
            // through a stale reference.
            members.forEach(m => {
                m._screenNameHitRect = null;
                if (this.selectedLayerIds) this.selectedLayerIds.delete(m.id);
            });
            if (this.currentLayer && members.some(m => m.id === this.currentLayer.id)) {
                const promoted = (this.project.layers || [])
                    .find(l => l.visible !== false) || null;
                this.currentLayer = promoted;
                this.lastSelectedLayerId = promoted ? promoted.id : null;
                if (promoted && this.selectedLayerIds && this.selectedLayerIds.size === 0) {
                    this.selectedLayerIds.add(promoted.id);
                }
            }
        }
        await this._commitGroupChange(anyVisible ? 'Hide Group' : 'Show Group');
        return true;
    }

    // "Route data as one screen" - the group's switch on the automatic data
    // crossing (_autoCrossMembers, app-screen-info.js). Off: each screen
    // cables on its own, exactly as it would ungrouped. Stored on the GROUP
    // rather than the members because it describes the wall's one combined
    // route, and absent means on, so every group made before the switch
    // existed keeps crossing. Data only - power keeps its own gate.
    async toggleGroupRouteDataAsOne(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        group.routeDataAsOne = group.routeDataAsOne === false;
        await this._commitGroupChange('Toggle Group Data Routing');
        return true;
    }

    // Whether the members COULD route as one screen for data - the walk's own
    // gate with the switch held open. Read by the group menu, so the switch
    // greys out on a group where crossing is never on offer (mixed
    // resolution, different canvases, a hand-wired member) instead of
    // pretending there is a choice to make.
    _groupCanRouteDataAsOne(group) {
        const g = this.resolveGroup(group);
        if (!g || typeof this._autoCrossMembers !== 'function') return false;
        const member = this.getGroupMembers(g).find(l => l
            && (l.type || 'screen') === 'screen' && l.visible !== false);
        return !!(member && this._autoCrossMembers(member, 'data', true));
    }

    // One lock for the wall, same "any unlocked => lock them all" rule
    // toggleLockOnSelected uses for a multi-selection.
    async toggleGroupLock(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        const members = this.getGroupMembers(group);
        if (members.length === 0) return false;
        const locked = members.some(m => !m.locked);
        members.forEach(m => { m.locked = locked; });
        await this._commitGroupChange(locked ? 'Lock Group' : 'Unlock Group');
        return true;
    }

    // Deletes every member AND the group as ONE undoable action. Goes through
    // the whole-project PUT rather than N DELETE calls, so the removal cannot
    // be half-applied and one saveState covers all of it.
    async deleteGroup(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        const memberIds = new Set(this.getGroupMembers(group).map(l => l.id));
        if (memberIds.size === 0) return false;
        const remaining = (this.project.layers || []).filter(l => !memberIds.has(l.id));
        if (remaining.length === 0) {
            // Same guard deleteLayer applies: a project keeps at least one layer.
            alert('Cannot delete the last layer');
            return false;
        }
        this.project.layers = remaining;
        this.project.groups = ((this.project.groups) || [])
            .filter(g => !(g && g.id === groupId));
        const promoted = remaining[remaining.length - 1] || null;
        this.currentLayer = promoted;
        this.selectedLayerIds = new Set(promoted ? [promoted.id] : []);
        this.lastSelectedLayerId = promoted ? promoted.id : null;
        this.selectionAnchorLayerId = this.lastSelectedLayerId;
        await this._commitGroupChange('Delete Group');
        return true;
    }

    // Copies every member AND creates a new group holding the copies, as ONE
    // undoable action - a duplicated wall is still one wall. Layer ids are
    // minted client-side; restore_project runs sync_next_layer_id on the way
    // in, so the server's counter rebases above them.
    async duplicateGroup(groupId) {
        const group = this.resolveGroup(groupId);
        if (!group) return false;
        const members = this.getGroupMembers(group);
        if (members.length < 2) return false;
        let nextLayerId = (this.project.layers || [])
            .reduce((max, l) => Math.max(max, Number(l.id) || 0), 0) + 1;
        const newGroupId = this._nextGroupId();
        const clones = members.map(src => {
            const clone = JSON.parse(JSON.stringify(src));
            clone.id = nextLayerId++;
            clone.name = this._nextDuplicateName(src.name);
            clone.group_id = newGroupId;
            // The same 50px nudge duplicateLayer applies, so the copy is
            // visibly its own wall instead of hiding under the original. Every
            // member takes the SAME nudge, so the wall keeps its shape.
            clone.offset_x = (Number(src.offset_x) || 0) + 50;
            clone.offset_y = (Number(src.offset_y) || 0) + 50;
            if (src.showOffsetX != null) clone.showOffsetX = (Number(src.showOffsetX) || 0) + 50;
            if (src.showOffsetY != null) clone.showOffsetY = (Number(src.showOffsetY) || 0) + 50;
            return clone;
        });
        this.project.layers.push(...clones);
        // A hand-drawn port or circuit that crosses members names its peer by
        // layer id, and every one of those ids just changed. Remap them onto
        // the clones BEFORE the commit, or the copy's wiring reaches back into
        // the wall it was copied from - and then quietly disappears, because
        // the entry names a layer outside the copy's group and both the client
        // sanitiser and the server prune drop exactly that. Unwired, the user
        // loses the wiring with no error; wired, the copy is a real copy.
        this.remapCopiedLayerPaths(members.map((source, i) => ({ source, clone: clones[i] })));
        if (!Array.isArray(this.project.groups)) this.project.groups = [];
        const copy = {
            id: newGroupId,
            name: this._nextDuplicateName(group.name),
            layer_ids: clones.map(c => c.id),
        };
        // The routing switch describes the wall, and the copy is the same
        // wall again - so it cables the way the original does.
        if ('routeDataAsOne' in group) copy.routeDataAsOne = group.routeDataAsOne;
        this.project.groups.push(copy);
        this.currentLayer = clones[0];
        this.selectedLayerIds = new Set(clones.map(c => c.id));
        this.lastSelectedLayerId = clones[0].id;
        this.selectionAnchorLayerId = clones[0].id;
        await this._commitGroupChange('Duplicate Group');
        return newGroupId;
    }

    // ── z-order: the group moves as one block ────────────────────────────
    //
    // Display order is the reverse of the layers array (newest on top). These
    // helpers work in DISPLAY order and treat each group as a single unit, so
    // the row the user sees moving is the thing that actually moves.

    _displayUnits() {
        const layers = (this.project && this.project.layers) || [];
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const effCid = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        const units = [];
        const byKey = new Map();
        [...layers].reverse().forEach(layer => {
            const group = this.getGroupOfLayer(layer);
            if (group) {
                const key = `group:${group.id}`;
                let unit = byKey.get(key);
                if (!unit) {
                    unit = { key, groupId: group.id, ids: [], canvasId: effCid(layer) };
                    byKey.set(key, unit);
                    units.push(unit);
                }
                unit.ids.push(layer.id);
                return;
            }
            units.push({
                key: `layer:${layer.id}`, groupId: null,
                ids: [layer.id], canvasId: effCid(layer),
            });
        });
        return units;
    }

    // Re-emit a display-order id list with every group's members collected
    // behind the FIRST of them. A drag that dropped an unrelated screen into
    // the middle of a group is undone by this, which is why applyDisplayOrder
    // runs it on every reorder rather than each reorder path guarding itself.
    normalizeGroupBlocks(displayIds) {
        const layers = (this.project && this.project.layers) || [];
        const byId = new Map(layers.map(l => [l.id, l]));
        const out = [];
        const placed = new Set();
        (displayIds || []).forEach(id => {
            if (placed.has(id)) return;
            const layer = byId.get(id);
            const group = this.getGroupOfLayer(layer);
            if (!group) {
                out.push(id);
                placed.add(id);
                return;
            }
            (displayIds || []).forEach(peerId => {
                if (placed.has(peerId)) return;
                const peer = byId.get(peerId);
                if (peer && peer.group_id === group.id) {
                    out.push(peerId);
                    placed.add(peerId);
                }
            });
        });
        return out;
    }

    // Apply the block rule to the CURRENT order without recording history -
    // used right after a membership change, where the caller's own
    // _commitGroupChange already provides the single undo step.
    _reflowGroupBlocks() {
        const layers = (this.project && this.project.layers) || [];
        if (layers.length === 0) return;
        const displayIds = [...layers].reverse().map(l => l.id);
        const normalized = this.normalizeGroupBlocks(displayIds);
        const byId = new Map(layers.map(l => [l.id, l]));
        this.project.layers = normalized.map(id => byId.get(id))
            .filter(Boolean).reverse();
    }

    moveGroupWithinCanvas(groupId, delta) {
        const units = this._displayUnits();
        const index = units.findIndex(u => u.groupId === groupId);
        if (index < 0) return false;
        const unit = units[index];
        const sameCanvas = units.filter(u => u.canvasId === unit.canvasId);
        const localIndex = sameCanvas.indexOf(unit);
        const nextLocal = localIndex + delta;
        if (nextLocal < 0 || nextLocal >= sameCanvas.length) return false;
        const other = sameCanvas[nextLocal];
        const a = units.indexOf(unit);
        const b = units.indexOf(other);
        [units[a], units[b]] = [units[b], units[a]];
        const displayIds = units.reduce((acc, u) => acc.concat(u.ids), []);
        this.applyDisplayOrder(displayIds, 'Reorder Group');
        return true;
    }

    // First / last unit in its canvas => the matching arrow is dead.
    _groupOrderState(groupId) {
        const units = this._displayUnits();
        const unit = units.find(u => u.groupId === groupId);
        if (!unit) return { atTop: true, atBottom: true };
        const sameCanvas = units.filter(u => u.canvasId === unit.canvasId);
        const localIndex = sameCanvas.indexOf(unit);
        return {
            atTop: localIndex <= 0,
            atBottom: localIndex < 0 || localIndex >= sameCanvas.length - 1,
        };
    }

    // ── settings agreement ───────────────────────────────────────────────

    // Client mirror of app.validate_group_settings, same contract: only the
    // fields that actually disagree land in `conflicts`, listing the distinct
    // values in first-seen order, and a field missing from a layer reads as
    // null and is a value like any other. `values` carries EVERY field so the
    // dialog can show the ones that already match as confirmation.
    // One member's value for a shared setting.
    //
    // lowLatency is a MODE, and "absent" is the same mode as "off" - a layer
    // written before the field existed and one with the box unticked are the
    // same screen, so they must not read as two values and open a dialog over
    // nothing.
    _groupSettingValueOf(layer, field) {
        if (!layer) return null;
        if (field === 'lowLatency') return !!layer.lowLatency;
        // An absent voltage is not a third opinion - it is the default the app
        // would use anyway (create_layer writes 110). Reading it as null made
        // a screen built without the key look like it DISAGREED with one that
        // has it, so grouping two perfectly ordinary screens raised a voltage
        // conflict over nothing. Same normalisation lowLatency gets above.
        if (field === 'powerVoltage') {
            const v = parseFloat(layer.powerVoltage);
            return Number.isFinite(v) && v > 0 ? v : 110;
        }
        return layer[field] === undefined ? null : layer[field];
    }

    validateGroupSettings(layers) {
        const values = {};
        this.GROUP_SHARED_SETTINGS.forEach(field => { values[field] = []; });
        (layers || []).forEach(layer => {
            if (!layer) return;
            this.GROUP_SHARED_SETTINGS.forEach(field => {
                const value = this._groupSettingValueOf(layer, field);
                if (!values[field].includes(value)) values[field].push(value);
            });
        });
        const conflicts = {};
        this.GROUP_SHARED_SETTINGS.forEach(field => {
            if (values[field].length > 1) conflicts[field] = values[field];
        });
        return { ok: Object.keys(conflicts).length === 0, conflicts, values };
    }

    _applyGroupSettings(layers, chosen) {
        if (!chosen) return;
        Object.keys(chosen).forEach(field => {
            (layers || []).forEach(layer => {
                if (layer) layer[field] = chosen[field];
            });
        });
        // The processor owns which bit depths and frame rates exist, so the
        // two Screen Info selects have to be rebuilt against what was just
        // written - the same call the single-screen processor handler makes.
        // Without it the sidebar keeps offering the OLD processor's rates.
        if (typeof this.updateBitDepthOptions === 'function') this.updateBitDepthOptions();
        if (typeof this.updateFrameRateOptions === 'function') this.updateFrameRateOptions();
        if (typeof this.updateLowLatencyUI === 'function') this.updateLowLatencyUI();
    }

    // Resolves to the values to write ({} when nothing had to be chosen), or
    // null when the user cancelled.
    _resolveGroupSettings(layers, mode) {
        const check = this.validateGroupSettings(layers);
        if (check.ok) return Promise.resolve({});
        return this.openGroupSettingsDialog(layers, check, mode);
    }

    // ── mismatch dialog ──────────────────────────────────────────────────

    _groupSettingFieldLabel(field) {
        return {
            processorType: 'Processor',
            bitDepth: 'Bit Depth',
            frameRate: 'Frame Rate',
            lowLatency: 'Low Latency',
            powerVoltage: 'Voltage',
        }[field] || field;
    }

    // Read the human label off the Screen Info select that owns the field, so
    // the dialog can never drift from the wording the sidebar already uses.
    _groupSettingValueLabel(field, value) {
        // A boolean field has no <select> to read: it is the Low Latency
        // checkbox, and false is a real answer rather than "not set".
        if (field === 'lowLatency') return value ? 'On' : 'Off';
        if (value === null || value === undefined || value === '') return 'Not set';
        const selectId = {
            processorType: 'processor-type',
            bitDepth: 'bit-depth',
            frameRate: 'frame-rate',
            powerVoltage: 'power-voltage-select',
        }[field];
        const select = selectId ? document.getElementById(selectId) : null;
        if (select) {
            const match = Array.from(select.options)
                .find(opt => opt.value === String(value));
            if (match) return match.textContent.trim();
        }
        // A custom voltage has no <option> to read - it is typed into
        // power-voltage-custom - so name the unit rather than showing a bare
        // number next to "Voltage".
        if (field === 'powerVoltage') return `${value} V`;
        return String(value);
    }

    // ── the combination has to exist ─────────────────────────────────────
    //
    // The dialog used to build one <select> per field independently from the
    // members' distinct values, so picking Processor = Armor next to Frame
    // Rate = 240 produced a screen whose frame rate is off the end of its
    // processor's table - a state the Screen Info panel cannot reach, because
    // there the processor <select> rebuilds (and clamps) the other two. These
    // helpers give the dialog the same clamp, from the same tables.

    // Values `field` may hold on `processorType`, or null when the processor
    // does not constrain it.
    _legalGroupSettingValues(field, processorType) {
        if (field === 'bitDepth') {
            return (typeof this.getSupportedBitDepths === 'function')
                ? this.getSupportedBitDepths(processorType) : null;
        }
        if (field === 'frameRate') {
            return (typeof this.getSelectableFrameRates === 'function')
                ? this.getSelectableFrameRates(processorType) : null;
        }
        if (field === 'lowLatency') {
            const profile = (typeof this.getLowLatencyProfile === 'function')
                ? this.getLowLatencyProfile(processorType) : null;
            // Same rule updateLowLatencyUI applies to the checkbox: a
            // processor with no Low Latency mode can only be off.
            return (profile && profile.supported) ? [false, true] : [false];
        }
        return null;   // the processor itself: every member's value is real
    }

    // Numbers reach here as numbers from the sidebar and as strings from a
    // hand-edited file, and 60 must not read as a different rate from '60'.
    _groupSettingValueMatches(a, b) {
        if (a === b) return true;
        if (typeof a === 'boolean' || typeof b === 'boolean') return !!a === !!b;
        if (a === null || a === undefined || b === null || b === undefined) return false;
        const na = Number(a);
        const nb = Number(b);
        return Number.isFinite(na) && Number.isFinite(nb) && na === nb;
    }

    // The processor the dialog is currently resolving against: whatever the
    // processor chooser shows, or the members' agreed value when there is no
    // chooser because they already agree.
    _chosenGroupSettingProcessor(picked) {
        if (picked && Object.prototype.hasOwnProperty.call(picked, 'processorType')) {
            return picked.processorType;
        }
        const check = this._groupSettingsCheck || { conflicts: {}, values: {} };
        const list = (check.conflicts || {}).processorType
            || (check.values || {}).processorType || [];
        return list.length ? list[0] : null;
    }

    // Which value a rebuilt chooser lands on. Keeping the user's pick comes
    // first. After that it is the same preference the Screen Info selects
    // apply when a processor change invalidates the old value: for a frame
    // rate, fall DOWN to the highest rate this processor publishes below the
    // one the screens were on - never up. Capacity runs as 1/fps, so landing
    // on a HIGHER rate would overstate pixels per port and under-count ports,
    // and that is the direction that leaves a crew short on site. Nothing
    // below it means the lowest published rate, which is index 0 (both
    // candidate lists arrive ascending).
    _preferredGroupSettingIndex(field, candidates, previousValue, fellBack, hint) {
        if (previousValue !== undefined) {
            const kept = candidates.findIndex(
                v => this._groupSettingValueMatches(v, previousValue));
            if (kept >= 0) return kept;
        }
        if (fellBack && field === 'frameRate') {
            const target = Number(hint);
            if (Number.isFinite(target)) {
                let best = -1;
                candidates.forEach((value, index) => {
                    const rate = Number(value);
                    if (!Number.isFinite(rate) || rate >= target) return;
                    if (best < 0 || rate > Number(candidates[best])) best = index;
                });
                if (best >= 0) return best;
            }
        }
        return 0;
    }

    openGroupSettingsDialog(layers, check, mode = 'create') {
        this._wireGroupSettingsModal();
        const modal = document.getElementById('group-settings-modal');
        const conflictsEl = document.getElementById('group-settings-conflicts');
        if (!modal || !conflictsEl) return Promise.resolve(null);

        const count = (layers || []).length;
        const sublabel = document.getElementById('group-settings-sublabel');
        if (sublabel) {
            sublabel.textContent = `A group calculates and exports as one screen, `
                + `so all ${count} screens have to share these settings.`;
        }

        this._groupSettingsCheck = check;
        this._renderGroupSettingsRows();

        const note = document.getElementById('group-settings-note');
        if (note) {
            note.textContent = mode === 'add'
                ? 'Cancel leaves the group and the screens unchanged.'
                : 'Cancel leaves the screens ungrouped and unchanged.';
        }

        modal.style.display = 'block';
        return new Promise(resolve => { this._groupSettingsResolve = resolve; });
    }

    // Build (or rebuild) the chooser rows for the settings the group has to
    // agree on. Re-runs whenever the Processor pick changes, because the
    // processor decides which bit depths and frame rates exist at all - the
    // whole point of the rebuild is that a combination the hardware does not
    // have can never be assembled out of three independent dropdowns.
    _renderGroupSettingsRows() {
        const check = this._groupSettingsCheck || { conflicts: {}, values: {} };
        const conflictsEl = document.getElementById('group-settings-conflicts');
        if (!conflictsEl) return;

        // What the user has picked so far, read back as VALUES so a rebuild
        // that changes the option list cannot silently re-point an index.
        const picked = {};
        conflictsEl.querySelectorAll('.group-settings-select').forEach(select => {
            const field = select.dataset.field;
            const list = (this._groupSettingsChoices || {})[field] || [];
            const index = parseInt(select.value, 10);
            if (field && index >= 0 && index < list.length) picked[field] = list[index];
        });

        const processorType = this._chosenGroupSettingProcessor(picked);
        const choices = {};
        const fellBack = {};
        const bases = {};
        const chooserFields = [];
        this.GROUP_SHARED_SETTINGS.forEach(field => {
            const base = ((check.conflicts || {})[field]
                || (check.values || {})[field] || []).slice();
            bases[field] = base;
            const legal = this._legalGroupSettingValues(field, processorType);
            let candidates = legal
                ? base.filter(v => legal.some(l => this._groupSettingValueMatches(l, v)))
                : base;
            // A value the members agreed on but this processor does not have
            // still needs answering, so it becomes a chooser rather than a
            // line of confirmation text.
            const forced = !!legal && candidates.length !== base.length;
            fellBack[field] = candidates.length === 0;
            if (fellBack[field]) candidates = legal ? legal.slice() : base;
            choices[field] = candidates;
            if (candidates.length > 1 || forced) chooserFields.push(field);
        });
        this._groupSettingsChoices = choices;

        conflictsEl.innerHTML = '';
        chooserFields.forEach(field => {
            const row = document.createElement('div');
            row.className = 'info-row group-settings-row';
            row.dataset.field = field;
            const label = document.createElement('label');
            label.textContent = this._groupSettingFieldLabel(field);
            const select = document.createElement('select');
            select.className = 'info-select group-settings-select';
            select.dataset.field = field;
            choices[field].forEach((value, index) => {
                const option = document.createElement('option');
                option.value = String(index);
                option.textContent = this._groupSettingValueLabel(field, value);
                select.appendChild(option);
            });
            select.value = String(this._preferredGroupSettingIndex(
                field, choices[field], picked[field], fellBack[field],
                (bases[field] || [])[0]));
            if (field === 'processorType') {
                select.addEventListener('change', () => this._renderGroupSettingsRows());
            }
            row.appendChild(label);
            row.appendChild(select);
            conflictsEl.appendChild(row);
        });

        // Fields that already agree - and that the chosen processor actually
        // offers - are shown as confirmation, so the user can see what the
        // group inherits without having to check each screen.
        const matchingEl = document.getElementById('group-settings-matching');
        const matchingSection = document.getElementById('group-settings-matching-section');
        if (matchingEl) {
            matchingEl.innerHTML = '';
            const matching = this.GROUP_SHARED_SETTINGS
                .filter(field => !chooserFields.includes(field));
            matching.forEach(field => {
                const row = document.createElement('div');
                row.className = 'group-settings-match';
                row.dataset.field = field;
                const value = choices[field].length
                    ? choices[field][0] : (check.values[field] || [])[0];
                row.textContent = `${this._groupSettingFieldLabel(field)}: `
                    + this._groupSettingValueLabel(field, value);
                matchingEl.appendChild(row);
            });
            if (matchingSection) {
                matchingSection.style.display = matching.length ? 'block' : 'none';
            }
        }
    }

    closeGroupSettingsDialog(result = null) {
        const modal = document.getElementById('group-settings-modal');
        if (modal) modal.style.display = 'none';
        const resolve = this._groupSettingsResolve;
        this._groupSettingsResolve = null;
        if (resolve) resolve(result);
    }

    _confirmGroupSettingsDialog() {
        const chosen = {};
        const choices = this._groupSettingsChoices || {};
        document.querySelectorAll('#group-settings-conflicts .group-settings-select')
            .forEach(select => {
                const field = select.dataset.field;
                const values = choices[field] || [];
                const index = parseInt(select.value, 10);
                if (field && index >= 0 && index < values.length) {
                    chosen[field] = values[index];
                }
            });
        this.closeGroupSettingsDialog(this._coerceGroupSettings(chosen));
    }

    // Last gate before the values are written to every member: whatever the
    // dialog ended up holding has to be a combination the processor actually
    // has. The rows above are built so this is already true; it runs anyway
    // because this is the function whose OUTPUT becomes the group's settings,
    // and a combination that does not exist must not be able to leave here.
    _coerceGroupSettings(chosen) {
        const out = Object.assign({}, chosen || {});
        const check = this._groupSettingsCheck || { conflicts: {}, values: {} };
        const agreed = (field) => {
            if (Object.prototype.hasOwnProperty.call(out, field)) return out[field];
            const list = (check.values || {})[field] || [];
            return list.length === 1 ? list[0] : undefined;
        };
        const processorType = agreed('processorType');
        ['bitDepth', 'frameRate', 'lowLatency'].forEach(field => {
            const legal = this._legalGroupSettingValues(field, processorType);
            if (!legal || legal.length === 0) return;
            const value = agreed(field);
            if (value === undefined) return;
            if (legal.some(l => this._groupSettingValueMatches(l, value))) return;
            const index = this._preferredGroupSettingIndex(
                field, legal, undefined, true, value);
            out[field] = legal[index];
            sendClientLog('group_settings_coerced', {
                field, from: value, to: out[field], processorType,
            });
        });
        return out;
    }

    // Wired on first open rather than at boot: the modal is only ever reached
    // from a group action, and nothing else on the page touches it.
    _wireGroupSettingsModal() {
        if (this._groupSettingsWired) return;
        const modal = document.getElementById('group-settings-modal');
        if (!modal) return;
        const cancel = document.getElementById('group-settings-cancel');
        const apply = document.getElementById('group-settings-apply');
        if (cancel) cancel.addEventListener('click', () => this.closeGroupSettingsDialog(null));
        if (apply) apply.addEventListener('click', () => this._confirmGroupSettingsDialog());
        // Backdrop click and Escape cancel, same as the preset modals.
        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.closeGroupSettingsDialog(null);
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._groupSettingsResolve) {
                this.closeGroupSettingsDialog(null);
            }
        });
        this._groupSettingsWired = true;
    }

    // ── sidebar ──────────────────────────────────────────────────────────

    isGroupExpanded(groupId) {
        return !!(this._expandedGroupIds && this._expandedGroupIds.has(groupId));
    }

    // Expansion is a view cursor, like the active canvas: it is not project
    // data, so it records no undo step and never reaches the server.
    setGroupExpanded(groupId, expanded) {
        if (!this._expandedGroupIds) this._expandedGroupIds = new Set();
        if (expanded) this._expandedGroupIds.add(groupId);
        else this._expandedGroupIds.delete(groupId);
        const wrap = document.querySelector(`.screen-group[data-group-id="${groupId}"]`);
        if (!wrap) return;
        wrap.classList.toggle('collapsed', !expanded);
        const toggle = wrap.querySelector('.screen-group-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            toggle.textContent = expanded ? '▾' : '▸';
            toggle.title = expanded
                ? 'Hide the screens this group is built from'
                : 'Show the screens this group is built from';
        }
    }

    // Replace each group's member rows with ONE row for the group, holding the
    // members in a disclosure body. Runs after regroupLayersByCanvas so it can
    // lift the rows that pass has already placed.
    regroupLayersByGroup(container) {
        const groups = (((this.project) || {}).groups) || [];
        if (!Array.isArray(groups) || groups.length === 0) return;
        groups.forEach(group => {
            if (!group || !Array.isArray(group.layer_ids)) return;
            const nodes = group.layer_ids
                .map(id => container.querySelector(`.layer-item[data-layer-id="${id}"]`))
                .filter(Boolean);
            if (nodes.length < 2) return;  // a group of one is not a group
            // Keep the order the list already put the rows in, so grouping
            // never reshuffles the newest-on-top layer order.
            nodes.sort((a, b) => (
                (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1
            ));
            const first = nodes[0];
            const parent = first.parentNode;
            if (!parent) return;
            // A member sitting in a DIFFERENT canvas group stays put: a group
            // lives inside a canvas, and moving the row would misreport which
            // canvas that screen belongs to.
            const own = nodes.filter(node => node.parentNode === parent);
            const wrap = this.buildScreenGroupEl(group, own.length);
            parent.insertBefore(wrap, first);
            const body = wrap.querySelector('.screen-group-body');
            own.forEach(node => {
                node.classList.add('grouped');
                body.appendChild(node);
            });
        });
    }

    // The combined figures the group's single row carries: how many screens
    // the wall is built from, then its cabinets and weight - the two figures
    // read first when a wall is quoted or hung. Both come straight from
    // getGroupTotals (step 2), which already evaluates EACH member against ITS
    // OWN cabinet size and weight before summing, so this is correct for any
    // number of members and any mix of cabinet sizes.
    // The screen count comes from the ROLL-UP, not from getGroupMembers.
    //
    // v0.11.0 audit: the cabinet and weight figures are filtered to the canvas
    // this row is drawn on, but the count was a raw member count - so a group
    // with a member moved to another canvas read "3 screens · 48 cab · 960 kg"
    // above two rows, mixing a count of three walls with the weight of two.
    // The kg on that row is what gets handed to a rigger; the two halves of it
    // have to be counting the same screens.
    formatGroupTotalsLine(group) {
        const totals = this.getGroupTotals(group);
        const members = this.getGroupMembers(group);
        const units = new Set(members.map(l => (l && l.weight_unit) || 'kg'));
        const unit = units.size === 1 ? [...units][0] : 'kg';
        const weight = unit === 'lb' ? totals.weightLb : totals.weightKg;
        const n = (value) => Math.round(Number(value) || 0).toLocaleString('en-US');
        const counted = Number(totals.memberCount) || 0;
        const line = `${counted} screens · ${n(totals.cabinets)} cab `
            + `· ${n(weight)} ${unit}`;
        // Say so rather than quietly counting fewer: a member sitting on
        // another canvas is still in the group, and its absence from these
        // figures is exactly the sort of thing that goes unnoticed.
        const elsewhere = Number(totals.offCanvasCount) || 0;
        return elsewhere > 0 ? `${line} (+${elsewhere} on another canvas)` : line;
    }

    buildScreenGroupEl(group, memberCount) {
        const members = this.getGroupMembers(group);
        const expanded = this.isGroupExpanded(group.id);
        const allHidden = members.length > 0 && members.every(m => m.visible === false);
        const allLocked = members.length > 0 && members.every(m => m.locked);
        const selected = members.length > 0 && this.selectedLayerIds
            && members.every(m => this.selectedLayerIds.has(m.id));
        const order = this._groupOrderState(group.id);

        const wrap = document.createElement('div');
        wrap.className = 'screen-group' + (expanded ? '' : ' collapsed')
            + (allHidden ? ' hidden' : '') + (selected ? ' active' : '');
        wrap.dataset.groupId = group.id;
        wrap.dataset.memberCount = String(memberCount);

        const lockBadge = allLocked
            ? '<span class="screen-group-lock-badge" title="Locked">🔒</span>' : '';
        wrap.innerHTML = `
            <div class="screen-group-row" title="One screen built from ${memberCount} layers">
                <div class="layer-header">
                    <div class="screen-group-title">
                        <button class="screen-group-toggle" aria-expanded="${expanded ? 'true' : 'false'}"
                                title="${expanded ? 'Hide the screens this group is built from' : 'Show the screens this group is built from'}">${expanded ? '▾' : '▸'}</button>
                        <input class="screen-group-name-input" type="text" value="${this._escapeAttr(group.name || 'Group')}" readonly>
                        ${lockBadge}
                    </div>
                    <div class="layer-controls">
                        <div class="layer-arrows">
                            <button class="layer-btn screen-group-move-up" title="Move group up within canvas"${order.atTop ? ' disabled' : ''}>▲</button>
                            <button class="layer-btn screen-group-move-down" title="Move group down within canvas"${order.atBottom ? ' disabled' : ''}>▼</button>
                        </div>
                        <button class="layer-btn screen-group-vis-btn ${allHidden ? 'is-hidden' : ''}" title="${allHidden ? 'Hidden, click to show the group' : 'Visible, click to hide the group'}">${allHidden ? '🚫' : '👁'}</button>
                        <button class="layer-btn screen-group-menu-btn" title="Group actions">⋮</button>
                    </div>
                </div>
                <div class="layer-info screen-group-info">
                    ${allHidden ? '<span class="layer-hidden-badge">HIDDEN</span> ' : ''}${this._escapeAttr(this.formatGroupTotalsLine(group))}
                </div>
            </div>
            <div class="screen-group-body"></div>
        `;
        this._wireScreenGroupEl(wrap, group);
        return wrap;
    }

    _wireScreenGroupEl(wrap, group) {
        const row = wrap.querySelector('.screen-group-row');
        const toggle = wrap.querySelector('.screen-group-toggle');
        const nameInput = wrap.querySelector('.screen-group-name-input');
        const visBtn = wrap.querySelector('.screen-group-vis-btn');
        const menuBtn = wrap.querySelector('.screen-group-menu-btn');
        const upBtn = wrap.querySelector('.screen-group-move-up');
        const downBtn = wrap.querySelector('.screen-group-move-down');

        // Click the row anywhere except a control => select the whole wall,
        // which is what every downstream edit then acts on.
        row.addEventListener('click', (e) => {
            if (e.target.closest('button') || e.target.closest('input')) return;
            const ids = this.getGroupMembers(group).map(l => l.id);
            if (ids.length) this.setSelectedLayersByIds(ids, ids[0]);
        });

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            this.setGroupExpanded(group.id, !this.isGroupExpanded(group.id));
        });

        // Double-click to rename inline, same convention as canvas and layer
        // names. The edit cue is the `.editing` CLASS, never an inline style -
        // theme.css sets the field background/border with !important, so an
        // inline cue is painted over and the field never looks editable.
        nameInput.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            nameInput.readOnly = false;
            nameInput.classList.add('editing');
            nameInput.focus();
            nameInput.select();
        });
        const commitName = () => {
            if (nameInput.readOnly) return;
            nameInput.readOnly = true;
            nameInput.classList.remove('editing');
            const newName = nameInput.value.trim();
            if (newName && newName !== group.name) {
                this.renameGroup(group.id, newName);
            } else {
                nameInput.value = group.name || '';
            }
        };
        nameInput.addEventListener('blur', commitName);
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
            else if (e.key === 'Escape') {
                nameInput.value = group.name || '';
                nameInput.readOnly = true;
                nameInput.classList.remove('editing');
                nameInput.blur();
            }
            if (!nameInput.readOnly) e.stopPropagation();
        });

        visBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleGroupVisibility(group.id);
        });

        upBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (upBtn.disabled) return;
            this.moveGroupWithinCanvas(group.id, -1);
        });
        downBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (downBtn.disabled) return;
            this.moveGroupWithinCanvas(group.id, 1);
        });

        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openScreenGroupMenu(group, menuBtn);
        });
    }

    openScreenGroupMenu(group, anchor) {
        document.querySelectorAll('.canvas-menu-popup, .canvas-add-popup, .canvas-color-popup')
            .forEach(el => el.remove());
        const selected = this.getSelectedScreenLayers();
        const members = this.getGroupMembers(group);
        const canAdd = selected.some(l => l.group_id !== group.id);
        const canRemove = selected.some(l => l.group_id === group.id);
        const locked = members.length > 0 && members.every(m => m.locked);
        // The check reads the STORED state even on a group that cannot cross:
        // disabled says "no choice here", the mark says what is remembered.
        const routesAsOne = group.routeDataAsOne !== false;
        const canRouteAsOne = this._groupCanRouteDataAsOne(group);
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup screen-group-menu-popup';
        menu.innerHTML = `
            <button data-action="rename">Rename</button>
            <button data-action="duplicate">Duplicate Group</button>
            <button data-action="lock">${locked ? 'Unlock Group' : 'Lock Group'}</button>
            <button data-action="route-as-one"${canRouteAsOne ? '' : ' disabled'} title="${canRouteAsOne
                ? 'Off: each screen cables on its own'
                : 'These screens never route as one - the cabinets differ, or a member is hand-wired'}">${routesAsOne ? '✓ ' : ''}Route data as one screen</button>
            <button data-action="add"${canAdd ? '' : ' disabled'}>Add Selected Screens</button>
            <button data-action="remove"${canRemove ? '' : ' disabled'}>Remove Selected Screens</button>
            <button data-action="ungroup">Ungroup</button>
            <button data-action="delete" class="danger">Delete Group</button>
        `;
        document.body.appendChild(menu);
        const r = anchor.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = `${r.bottom + 4}px`;
        menu.style.left = `${Math.max(8, r.right - 190)}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        // Defer so the click that opened us doesn't immediately close it.
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (btn.disabled) return;
                const action = btn.dataset.action;
                close();
                this._handleScreenGroupMenuAction(group, action);
            });
        });
    }

    _handleScreenGroupMenuAction(group, action) {
        if (action === 'rename') {
            const input = document.querySelector(
                `.screen-group[data-group-id="${group.id}"] .screen-group-name-input`);
            if (input) {
                input.readOnly = false;
                input.classList.add('editing');
                input.focus();
                input.select();
            }
        } else if (action === 'duplicate') {
            this.duplicateGroup(group.id);
        } else if (action === 'lock') {
            this.toggleGroupLock(group.id);
        } else if (action === 'route-as-one') {
            this.toggleGroupRouteDataAsOne(group.id);
        } else if (action === 'add') {
            this.addSelectedToGroup(group.id);
        } else if (action === 'remove') {
            // Scoped to THIS group: the menu item is enabled by this group's
            // own members (canRemove above), so it has to act on them only.
            this.removeSelectedFromGroup(group.id);
        } else if (action === 'ungroup') {
            this.ungroupSelectedLayers(group.id);
        } else if (action === 'delete') {
            const count = this.getGroupMembers(group).length;
            const msg = `Delete "${group.name}" and the ${count} screens `
                + `it is built from?`;
            if (window.confirm(msg)) this.deleteGroup(group.id);
        }
    }
}

for (const k of Object.getOwnPropertyNames(_ScreenGroups.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ScreenGroups.prototype, k));
    }
}
