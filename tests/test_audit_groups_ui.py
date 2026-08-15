"""ADVERSARIAL AUDIT (throwaway) - screen group lifecycle in the real client.

Drives the REAL app against the REAL server (no synthetic project swap), so
every assertion is about what actually lands in window.app.project after a
round trip.

Run ALONE:
    python3 -m pytest tests/test_audit_groups_ui.py -v
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it -
    it drives the real group APIs and ends with a live group, group_id
    stamps and an extra canvas (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    pg.evaluate(BOOT_JS)
    return pg


BOOT_JS = r"""
window.__aud = {
  async freshProject(nScreens) {
    await fetch('/api/project/new', { method: 'POST' });
    for (let i = 0; i < nScreens; i++) {
      await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: 'S' + i, columns: 2, rows: 2,
          cabinet_width: 128, cabinet_height: 128,
          offset_x: i * 400, offset_y: 0,
        }),
      });
    }
    const p = await (await fetch('/api/project')).json();
    window.app.project = p;
    window.app.currentLayer = p.layers[0];
    window.app.selectedLayerIds = new Set([p.layers[0].id]);
    window.app.resetHistory('Initial State');
    return p;
  },
  select(ids) {
    window.app.selectedLayerIds = new Set(ids);
    window.app.currentLayer = window.app.project.layers.find(l => l.id === ids[0]);
    window.app.lastSelectedLayerId = ids[0];
  },
  layer(id) { return window.app.project.layers.find(l => l.id === id); },
  ids() { return window.app.project.layers.map(l => l.id); },
  model() {
    return {
      groups: (window.app.project.groups || []).map(
        g => ({ id: g.id, name: g.name, layer_ids: g.layer_ids })),
      seq: window.app.project.next_group_seq,
      mirror: window.app.project.layers.map(
        l => [l.id, l.group_id === undefined ? '<absent>' : l.group_id]),
      paths: window.app.project.layers.map(
        l => [l.id, l.customPortPaths || null, l.powerCustomPaths || null]),
    };
  },
  async serverModel() {
    const p = await (await fetch('/api/project')).json();
    return {
      groups: (p.groups || []).map(
        g => ({ id: g.id, name: g.name, layer_ids: g.layer_ids })),
      seq: p.next_group_seq,
      mirror: p.layers.map(l => [l.id, l.group_id === undefined ? '<absent>' : l.group_id]),
      paths: p.layers.map(l => [l.id, l.customPortPaths || null, l.powerCustomPaths || null]),
    };
  },
  async settle(ms) { await new Promise(r => setTimeout(r, ms || 400)); },
};
"""


def _fresh(page, n):
    return page.evaluate("n => window.__aud.freshProject(n)", n)


# ══════════════════════════════════════════════════════════════════════════
# 1. duplicateGroup: does the copy land where the model says it does?
# ══════════════════════════════════════════════════════════════════════════

def test_duplicate_group_panel_geometry(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const newGid = await window.app.duplicateGroup(gid);
      await window.__aud.settle();
      const src = window.__aud.layer(ids[0]);
      const grp = (window.app.project.groups || []).find(g => g.id === newGid);
      const clone = window.__aud.layer(grp.layer_ids[0]);
      const server = await window.__aud.serverModel();
      const sp = await (await fetch('/api/project')).json();
      const sClone = sp.layers.find(l => l.id === clone.id);
      return {
        gid, newGid,
        srcOffset: [src.offset_x, src.offset_y],
        srcPanel0: [src.panels[0].x, src.panels[0].y],
        cloneOffset: [clone.offset_x, clone.offset_y],
        clonePanel0: [clone.panels[0].x, clone.panels[0].y],
        serverClonePanel0: [sClone.panels[0].x, sClone.panels[0].y],
        serverGroups: server.groups,
      };
    }""")
    print('\nDUPLICATE GROUP:', out)
    # the copy declares itself 50px away from the source
    assert out['cloneOffset'][0] == out['srcOffset'][0] + 50
    # the server rebuilt the clone's panels to match the new offset...
    assert out['serverClonePanel0'][0] == out['srcPanel0'][0] + 50, out
    # ...and the CLIENT, which is what the canvas draws from, did not.
    assert out['clonePanel0'][0] == out['srcPanel0'][0] + 50, (
        'CLIENT clone panels not re-anchored: drawn on top of the source. %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 2. group -> wire across -> undo/redo storm -> membership + wiring survive
# ══════════════════════════════════════════════════════════════════════════

def test_undo_redo_storm_preserves_group_and_cross_paths(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();

      // hand-draw a port path that crosses onto the peer, the way the canvas
      // writer would, then persist it the way updateLayers does.
      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 },
        { row: 0, col: 1, layerId: ids[1] },
      ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a),
      });
      window.app.saveState('Draw Path');

      const before = window.__aud.model();
      for (let i = 0; i < 6; i++) {
        window.app.undo(); await window.__aud.settle(220);
        window.app.redo(); await window.__aud.settle(220);
      }
      const after = window.__aud.model();
      const server = await window.__aud.serverModel();
      return { before, after, server };
    }""")
    print('\nUNDO STORM before:', out['before'])
    print('UNDO STORM after :', out['after'])
    print('UNDO STORM server:', out['server'])
    assert out['after']['groups'] == out['before']['groups'], out
    assert out['after']['mirror'] == out['before']['mirror'], out
    assert out['after']['paths'] == out['before']['paths'], out
    assert out['server']['groups'] == out['before']['groups'], out
    assert out['server']['paths'] == out['before']['paths'], out


# ══════════════════════════════════════════════════════════════════════════
# 3. ungroup -> the client keeps wiring the server has already pruned
# ══════════════════════════════════════════════════════════════════════════

def test_ungroup_leaves_client_and_server_disagreeing_about_wiring(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });

      window.__aud.select(ids);
      await window.app.ungroupSelectedLayers(gid);
      await window.__aud.settle();
      const client = window.__aud.model();
      const server = await window.__aud.serverModel();
      // what the next undo snapshot holds
      const snap = window.app.history[window.app.historyIndex].project
        .layers.find(l => l.id === ids[0]).customPortPaths;
      return { client: client.paths, server: server.paths, snap };
    }""")
    print('\nUNGROUP client paths:', out['client'])
    print('UNGROUP server paths:', out['server'])
    print('UNGROUP snapshot    :', out['snap'])
    assert out['client'] == out['server'], (
        'client kept a cross-member step the server pruned: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 4. "Remove Selected Screens" acts on every group the selection touches
# ══════════════════════════════════════════════════════════════════════════

def test_remove_selected_from_group_leaks_into_other_groups(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(6);
      const ids = p.layers.map(l => l.id);
      window.__aud.select([ids[0], ids[1], ids[2]]);
      const gA = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      window.__aud.select([ids[3], ids[4], ids[5]]);
      const gB = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      // user selects one screen from EACH group, then opens group A's menu
      // and clicks "Remove Selected Screens".
      window.__aud.select([ids[0], ids[3]]);
      window.app._handleScreenGroupMenuAction(
        window.app.resolveGroup(gA), 'remove');
      await window.__aud.settle(600);
      return { gA, gB, ids, model: window.__aud.model() };
    }""")
    print('\nREMOVE LEAK:', out['model']['groups'])
    ids = out['ids']
    groups = {g['id']: g['layer_ids'] for g in out['model']['groups']}
    assert ids[3] in groups.get(out['gB'], []), (
        'group B lost a member from group A\'s menu: %r' % out['model']['groups'])


# ══════════════════════════════════════════════════════════════════════════
# 5. cross-canvas group: what the Screens sidebar actually renders
# ══════════════════════════════════════════════════════════════════════════

def test_cross_canvas_group_sidebar(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      // second canvas, move one member onto it
      const c = await (await fetch('/api/canvas', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'})).json();
      const c2 = c.active_canvas_id;
      const moved = await (await fetch('/api/layer/' + ids[1] + '/canvas', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ canvas_id: c2, mode: 'move' }) })).json();
      window.app.project = moved;
      window.app.renderLayers();
      await window.__aud.settle(300);
      const wrap = document.querySelector('.screen-group[data-group-id="' + gid + '"]');
      return {
        gid,
        groups: (window.app.project.groups || []).map(g => g.layer_ids),
        memberCount: wrap ? wrap.dataset.memberCount : null,
        rowsInGroupBody: wrap
          ? wrap.querySelectorAll('.screen-group-body .layer-item').length : null,
        totalsLine: wrap
          ? wrap.querySelector('.screen-group-info').textContent.trim() : null,
        looseRows: document.querySelectorAll(
          '#layers-list .layer-item:not(.grouped)').length,
      };
    }""")
    print('\nCROSS-CANVAS SIDEBAR:', out)
    assert out['memberCount'] == '2', (
        'group row claims %s members but the other one sits on another canvas: %r'
        % (out['memberCount'], out))


# ══════════════════════════════════════════════════════════════════════════
# 6. group of one via the client + reorder normalisation
# ══════════════════════════════════════════════════════════════════════════

def test_group_dissolves_to_one_and_seq_does_not_reuse(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(3);
      const ids = p.layers.map(l => l.id);
      window.__aud.select([ids[0], ids[1]]);
      const g1 = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const seqAfterCreate = window.app.project.next_group_seq;
      window.__aud.select([ids[1]]);
      await window.app.removeSelectedFromGroup();   // leaves a group of one
      await window.__aud.settle();
      const afterRemove = window.__aud.model();
      window.__aud.select([ids[0], ids[2]]);
      const g2 = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      return { g1, g2, seqAfterCreate, afterRemove, after: window.__aud.model() };
    }""")
    print('\nDISSOLVE + RE-CREATE:', out)
    assert out['afterRemove']['groups'] == [], out
    assert out['g2'] != out['g1'], 'freed group id handed straight back out: %r' % out


def test_reorder_keeps_group_members_contiguous(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(4);
      const ids = p.layers.map(l => l.id);
      window.__aud.select([ids[0], ids[2]]);      // NON-adjacent members
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const order = window.app.project.layers.map(l => l.id);
      const gidOf = window.app.project.layers.map(l => l.group_id);
      // move the group down then up again
      window.app.moveGroupWithinCanvas(gid, 1);
      await window.__aud.settle(300);
      window.app.moveGroupWithinCanvas(gid, -1);
      await window.__aud.settle(300);
      return {
        gid, order, gidOf,
        finalOrder: window.app.project.layers.map(l => l.id),
        finalGroups: (window.app.project.groups || []).map(g => g.layer_ids),
        server: (await window.__aud.serverModel()),
      };
    }""")
    print('\nREORDER:', out)
    ids_in_group = out['finalGroups'][0]
    order = out['finalOrder']
    pos = sorted(order.index(i) for i in ids_in_group)
    assert pos == list(range(pos[0], pos[0] + len(pos))), (
        'group members not contiguous after reorder: %r' % out)
    assert out['server']['groups'][0]['layer_ids'] == ids_in_group, out


# ══════════════════════════════════════════════════════════════════════════
# 7. the POST save path pushes the client's stale wiring back onto the server
# ══════════════════════════════════════════════════════════════════════════

def test_reorder_after_ungroup_resurrects_pruned_wiring_on_the_server(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });

      window.__aud.select(ids);
      await window.app.ungroupSelectedLayers(gid);
      await window.__aud.settle();
      const afterUngroup = (await window.__aud.serverModel()).paths;

      const clientBefore = window.__aud.model().paths;
      const idsBefore = window.__aud.ids();
      // any sidebar reorder -> applyDisplayOrder -> saveProject() -> POST
      window.app.moveLayerWithinCanvas(ids[ids.length - 1], 1);
      await window.__aud.settle(900);
      const afterReorder = (await window.__aud.serverModel()).paths;
      return { ids, idsBefore, clientBefore, afterUngroup, afterReorder,
               clientAfter: window.__aud.model().paths,
               idsAfter: window.__aud.ids() };
    }""")
    print('\nPOST RESURRECT after ungroup :', out['afterUngroup'])
    print('POST RESURRECT after reorder :', out['afterReorder'])
    # Keyed by layer id, not compared as an ordered list: the reorder is
    # SUPPOSED to change the layer order, and the question here is only whether
    # the wiring on each layer survived the trip through POST /api/project.
    before = {row[0]: row[1:] for row in out['afterUngroup']}
    after = {row[0]: row[1:] for row in out['afterReorder']}
    assert after == before, (
        'POST /api/project put the pruned cross-member step back on the '
        'server: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 8. full torture: rename / hide / lock / reorder / undo x N / redo x N / reload
# ══════════════════════════════════════════════════════════════════════════

def test_torture_group_lifecycle(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(3);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids.slice(0, 3));
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();

      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });
      window.app.saveState('Draw Path');

      await window.app.renameGroup(gid, 'Upstage Wall');   await window.__aud.settle();
      await window.app.toggleGroupLock(gid);               await window.__aud.settle();
      await window.app.toggleGroupVisibility(gid);         await window.__aud.settle();
      await window.app.toggleGroupVisibility(gid);         await window.__aud.settle();
      window.app.moveGroupWithinCanvas(gid, 1);            await window.__aud.settle(350);

      const peak = window.__aud.model();
      const depth = window.app.history.length;
      for (let i = 0; i < depth + 3; i++) { window.app.undo(); await window.__aud.settle(180); }
      const bottom = window.__aud.model();
      for (let i = 0; i < depth + 3; i++) { window.app.redo(); await window.__aud.settle(180); }
      const back = window.__aud.model();

      // "save to file and open it again"
      const blob = JSON.parse(JSON.stringify(window.app.project));
      const reloaded = await (await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(blob) })).json();
      return {
        peak, bottom, back, depth,
        reloadedGroups: (reloaded.groups || []).map(
          g => ({ id: g.id, name: g.name, layer_ids: g.layer_ids })),
        reloadedPaths: reloaded.layers.map(
          l => [l.id, l.customPortPaths || null]),
        reloadedMirror: reloaded.layers.map(l => [l.id, l.group_id]),
      };
    }""")
    print('\nTORTURE peak  :', out['peak'])
    print('TORTURE bottom:', out['bottom'])
    print('TORTURE back  :', out['back'])
    print('TORTURE reload:', out['reloadedGroups'], out['reloadedPaths'])
    assert out['back']['groups'] == out['peak']['groups'], out
    assert out['back']['mirror'] == out['peak']['mirror'], out
    assert out['back']['paths'] == out['peak']['paths'], out
    assert out['reloadedGroups'] == out['peak']['groups'], out
    # every layer's mirror agrees with layer_ids after the reload
    member_ids = {i for g in out['reloadedGroups'] for i in g['layer_ids']}
    for lid, gid in out['reloadedMirror']:
        assert (gid is not None) == (lid in member_ids), out


# ══════════════════════════════════════════════════════════════════════════
# 9. cross-canvas group: the group row's totals count off-canvas screens
# ══════════════════════════════════════════════════════════════════════════

def test_cross_canvas_group_totals_include_offcanvas_member(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const before = window.app.getGroupTotals(gid);
      const c = await (await fetch('/api/canvas', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'})).json();
      const moved = await (await fetch('/api/layer/' + ids[1] + '/canvas', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ canvas_id: c.active_canvas_id, mode: 'move' })
      })).json();
      window.app.project = moved;
      const after = window.app.getGroupTotals(gid);
      window.app.renderLayers();
      await window.__aud.settle(300);
      const wrap = document.querySelector('.screen-group[data-group-id="' + gid + '"]');
      return {
        beforeCab: before.cabinets, beforeKg: Math.round(before.weightKg),
        afterCab: after.cabinets, afterKg: Math.round(after.weightKg),
        afterMembers: after.memberCount,
        bodyRows: wrap ? wrap.querySelectorAll('.screen-group-body .layer-item').length : null,
        line: wrap ? wrap.querySelector('.screen-group-info').textContent.trim() : null,
      };
    }""")
    print('\nCROSS-CANVAS TOTALS:', out)
    assert out['bodyRows'] == out['afterMembers'], (
        'the group row on canvas 1 reports %s screens / %s cabinets / %s kg but '
        'only shows %s rows - the rest hang on another canvas: %r'
        % (out['afterMembers'], out['afterCab'], out['afterKg'],
           out['bodyRows'], out))


# ══════════════════════════════════════════════════════════════════════════
# 10. drop an unrelated screen into the middle of a group
# ══════════════════════════════════════════════════════════════════════════

def test_drag_unrelated_screen_into_a_group_block(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(3);
      const ids = p.layers.map(l => l.id);
      window.__aud.select([ids[0], ids[1]]);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const display = [...window.app.project.layers].reverse().map(l => l.id);
      const outsider = display.find(id => !window.app.resolveGroup(gid)
        .layer_ids.includes(id));
      const gi = display.findIndex(
        id => window.app.resolveGroup(gid).layer_ids.includes(id));
      const forced = display.filter(id => id !== outsider);
      forced.splice(gi + 1, 0, outsider);   // wedge it between two members
      window.app.applyDisplayOrder(forced, 'Reorder Layers');
      await window.__aud.settle(500);
      const finalDisplay = [...window.app.project.layers].reverse().map(l => l.id);
      const server = await window.__aud.serverModel();
      return { gid, outsider, forced, finalDisplay,
               members: window.app.resolveGroup(gid).layer_ids,
               serverOrder: server.mirror.map(m => m[0]) };
    }""")
    print('\nWEDGE:', out)
    pos = sorted(out['finalDisplay'].index(i) for i in out['members'])
    assert pos == list(range(pos[0], pos[0] + len(pos))), out
    assert sorted(out['finalDisplay']) == sorted(out['serverOrder']), (
        'a layer was dropped by the reorder: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 11. deleteGroup
# ══════════════════════════════════════════════════════════════════════════

def test_delete_group_coherent(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(3);
      const ids = p.layers.map(l => l.id);
      window.__aud.select([ids[0], ids[1]]);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const ok = await window.app.deleteGroup(gid);
      await window.__aud.settle(400);
      const server = await window.__aud.serverModel();
      return { ok, ids, client: window.__aud.model(), server,
               clientIds: window.__aud.ids(),
               serverIds: server.mirror.map(m => m[0]) };
    }""")
    print('\nDELETE GROUP:', out)
    assert out['client']['groups'] == [], out
    assert out['clientIds'] == out['serverIds'], (
        'client and server disagree about which layers exist: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 12. duplicate the same group twice - no id collisions anywhere
# ══════════════════════════════════════════════════════════════════════════

def test_duplicate_group_twice_no_collisions(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(2);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      await window.app.duplicateGroup(gid); await window.__aud.settle(400);
      await window.app.duplicateGroup(gid); await window.__aud.settle(400);
      // now add a normal layer through the server and make sure its id is free
      const added = await (await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name:'New', columns:1, rows:1,
          cabinet_width:128, cabinet_height:128}) })).json();
      const server = await window.__aud.serverModel();
      return {
        clientIds: window.__aud.ids(),
        serverIds: server.mirror.map(m => m[0]),
        groups: server.groups, addedId: added.id,
      };
    }""")
    print('\nDUP TWICE:', out)
    assert len(set(out['serverIds'])) == len(out['serverIds']), out
    gids = [g['id'] for g in out['groups']]
    assert len(set(gids)) == len(gids), out
    assert out['serverIds'].count(out['addedId']) == 1, (
        'a client-minted clone id collided with a server-minted one: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 13. ungroup -> regroup: does the wiring come back, and is that deterministic?
# ══════════════════════════════════════════════════════════════════════════

def test_ungroup_then_regroup_resurrects_wiring_only_without_a_reload(page):
    out = page.evaluate(r"""async () => {
      const run = async (reloadBetween) => {
        const p = await window.__aud.freshProject(1);   // default + 1 = 2 screens
        const ids = p.layers.map(l => l.id);
        window.__aud.select(ids);
        const gid = await window.app.groupSelectedLayers();
        await window.__aud.settle();
        const a = window.__aud.layer(ids[0]);
        a.flowPattern = 'custom';
        a.customPortPaths = { '1': [
          { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
        await fetch('/api/layer/' + a.id, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(a) });
        window.__aud.select(ids);
        await window.app.ungroupSelectedLayers(gid);
        await window.__aud.settle();
        if (reloadBetween) {
          // what File > Open / a fresh session would give the client back
          window.app.project = await (await fetch('/api/project')).json();
        }
        window.__aud.select(ids);
        await window.app.groupSelectedLayers();
        await window.__aud.settle();
        const server = await window.__aud.serverModel();
        return server.paths[0][1];
      };
      return { noReload: await run(false), withReload: await run(true) };
    }""")
    print('\nREGROUP no reload  :', out['noReload'])
    print('REGROUP with reload:', out['withReload'])
    assert out['noReload'] == out['withReload'], (
        'whether the cross-member wiring survives ungroup+regroup depends on '
        'whether the client reloaded in between: %r' % out)


# ══════════════════════════════════════════════════════════════════════════
# 14. cross-canvas group: server KEEPS the step, the client's loader DELETES it
# ══════════════════════════════════════════════════════════════════════════

def test_client_loader_destroys_wiring_the_server_kept(page):
    out = page.evaluate(r"""async () => {
      const p = await window.__aud.freshProject(1);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle();
      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });
      await window.__aud.settle(600);
      const c = await (await fetch('/api/canvas', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'})).json();
      await fetch('/api/layer/' + ids[1] + '/canvas', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ canvas_id: c.active_canvas_id, mode: 'move' }) });
      await window.__aud.settle(900);
      // "save to file, open the file": the server's copy is what gets written
      const onDisk = await (await fetch('/api/project')).json();
      const inFile = onDisk.layers.find(l => l.id === ids[0]).customPortPaths;
      // ...and this is what File > Open does to it before the PUT
      window.app.project = onDisk;
      window.app.sanitizeCrossLayerPaths(
        window.app.project.layers.find(l => l.id === ids[0]));
      const afterLoad = window.app.project.layers
        .find(l => l.id === ids[0]).customPortPaths;
      return { inFile, afterLoad };
    }""")
    print('\nCROSS-CANVAS LOAD  in file:', out['inFile'])
    print('CROSS-CANVAS LOAD after   :', out['afterLoad'])
    assert out['afterLoad'] == out['inFile'], (
        'File > Open silently deleted a cross-member step the server kept: %r'
        % out)


def test_when_exactly_does_the_cross_canvas_step_die(page):
    out = page.evaluate(r"""async () => {
      const snap = async () => (await (await fetch('/api/project')).json())
        .layers.find(l => l.id === 1).customPortPaths;
      const p = await window.__aud.freshProject(1);
      const ids = p.layers.map(l => l.id);
      window.__aud.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__aud.settle(500);
      const a = window.__aud.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });
      await window.__aud.settle(500);
      const afterDraw = await snap();
      const c = await (await fetch('/api/canvas', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'})).json();
      await window.__aud.settle(500);
      const afterNewCanvas = await snap();
      await fetch('/api/layer/' + ids[1] + '/canvas', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ canvas_id: c.active_canvas_id, mode: 'move' }) });
      const afterMoveImmediate = await snap();
      await window.__aud.settle(900);
      const afterMoveSettled = await snap();
      return { afterDraw, afterNewCanvas, afterMoveImmediate, afterMoveSettled };
    }""")
    print('\nWHEN DOES IT DIE:', out)
    # FLIPPED. It used to die at an unpredictable moment, because the step
    # outlived the move on the server while the client's loader deleted it -
    # so the answer depended on which pass ran first.
    #
    # It now dies AT THE MOVE, once, by the server's decision: a group is one
    # physical wall driven by one canvas, so moving a member off it takes the
    # member out of the wall (routes_layers._detach_from_cross_canvas_group),
    # and the step that named it goes with it. Nothing after that changes the
    # answer - which is the property this test exists to pin.
    assert out['afterDraw'] == {'1': [{'row': 0, 'col': 0},
                                      {'row': 0, 'col': 1, 'layerId': 2}]}, out
    assert out['afterNewCanvas'] == out['afterDraw'], out
    assert out['afterMoveImmediate'] == {'1': [{'row': 0, 'col': 0}]}, out
    assert out['afterMoveSettled'] == out['afterMoveImmediate'], out
