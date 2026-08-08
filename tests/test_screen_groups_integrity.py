"""Screen groups - the v0.10.9 audit fixes, as permanent guards.

The audit files (test_audit_*.py) are throwaway; these are the assertions worth
keeping from them, plus the ones the audit could not make because the fix did
not exist yet:

* "Remove Selected Screens" acts on the group whose menu was used, and on no
  other group the selection happens to touch.
* A group commit adopts the WHOLE repaired project the server hands back, so
  the client is never left holding state the server has already repaired -
  most visibly a duplicated group, whose panels the server re-anchors.
* The mismatch dialog cannot assemble a processor / bit depth / frame rate
  combination the processor does not have.
* Low Latency is a processor-wide mode, so it is checked at creation like bit
  depth is.
* The client's cross-member path pruner applies the SERVER's rule, and does
  nothing at all to a project that has no cross-member wiring.

Run alone (the live server is shared with the other browser test files):
    python3 -m pytest tests/test_screen_groups_integrity.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


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
    yield pg
    context.close()


BOOT_JS = r"""
window.__gi = {
  async fresh(n, props) {
    // Drain any group commit the previous test left in flight. Its adoption
    // replaces window.app.project when it lands, and a test that started
    // meanwhile would be holding layer objects the app no longer owns.
    await this.drain();
    await fetch('/api/project/new', { method: 'POST' });
    for (let i = 0; i < n; i++) {
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
    const screens = p.layers.filter(l => (l.type || 'screen') === 'screen');
    screens.forEach((l, i) => {
      const own = (props && props[i]) || (props && props.all) || null;
      if (own) Object.keys(own).forEach(k => { l[k] = own[k]; });
    });
    await fetch('/api/project', {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(window.app.project),
    });
    window.app.project = await (await fetch('/api/project')).json();
    window.app.currentLayer = window.app.project.layers[0];
    window.app.selectedLayerIds = new Set([window.app.project.layers[0].id]);
    if (window.app._flushPendingSaveState) window.app._flushPendingSaveState();
    window.app.resetHistory('Initial State');
    return window.app.project.layers.map(l => l.id);
  },
  select(ids) {
    window.app.selectedLayerIds = new Set(ids);
    window.app.currentLayer = window.app.project.layers.find(l => l.id === ids[0]);
    window.app.lastSelectedLayerId = ids[0];
  },
  layer(id) { return window.app.project.layers.find(l => l.id === id); },
  groups() {
    return (window.app.project.groups || []).map(
      g => ({ id: g.id, name: g.name, layer_ids: g.layer_ids }));
  },
  async serverProject() { return await (await fetch('/api/project')).json(); },
  dialogRows() {
    return [...document.querySelectorAll(
      '#group-settings-conflicts .group-settings-row')].map(row => ({
        field: row.dataset.field,
        options: [...row.querySelectorAll('option')].map(o => o.textContent),
      }));
  },
  pick(field, label) {
    const sel = document.querySelector(
      `#group-settings-conflicts .group-settings-select[data-field="${field}"]`);
    if (!sel) return false;
    const opt = [...sel.options].find(o => o.textContent === label);
    if (!opt) return false;
    sel.value = opt.value;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  },
  dialogOpen() {
    const m = document.getElementById('group-settings-modal');
    return !!m && getComputedStyle(m).display !== 'none';
  },
  async settle(ms) { await new Promise(r => setTimeout(r, ms || 400)); },
  async drain() {
    for (let i = 0; i < 10; i++) {
      const chain = window.app._groupCommitChain;
      if (!chain) break;
      try { await chain; } catch (e) { /* a failed commit still drains */ }
      if (chain === window.app._groupCommitChain) break;
    }
    await new Promise(r => setTimeout(r, 300));
  },
};
"""


def _cancel_dialog(page):
    page.evaluate("""() => {
      const b = document.getElementById('group-settings-cancel');
      if (b && window.__gi.dialogOpen()) b.click();
    }""")
    page.wait_for_timeout(400)


# ══════════════════════════════════════════════════════════════════════════
# 1. "Remove Selected Screens" is scoped to the group whose menu was used
# ══════════════════════════════════════════════════════════════════════════

def test_remove_selected_screens_only_touches_the_menu_group(page):
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(6);
      window.__gi.select([ids[0], ids[1], ids[2]]);
      const gA = await window.app.groupSelectedLayers();
      await window.__gi.settle();
      window.__gi.select([ids[3], ids[4], ids[5]]);
      const gB = await window.app.groupSelectedLayers();
      await window.__gi.settle();
      // one screen from EACH wall selected, group A's menu used
      window.__gi.select([ids[0], ids[3]]);
      await window.app.removeSelectedFromGroup(gA);
      await window.__gi.settle(600);
      const server = await window.__gi.serverProject();
      return {
        ids, gA, gB,
        client: window.__gi.groups().map(g => ({id: g.id, layer_ids: g.layer_ids})),
        server: (server.groups || []).map(g => ({id: g.id, layer_ids: g.layer_ids})),
        mirror: Object.fromEntries(
          server.layers.map(l => [l.id, l.group_id === undefined ? null : l.group_id])),
      };
    }""")
    ids = out['ids']
    by_id = {g['id']: g['layer_ids'] for g in out['server']}
    assert ids[3] in by_id.get(out['gB'], []), (
        "group B lost a member to group A's Remove Selected Screens: %r" % out)
    assert ids[0] not in by_id.get(out['gA'], []), out
    assert out['mirror'][str(ids[3])] == out['gB'], out
    assert out['client'] == out['server'], (
        'client and server disagree after the removal: %r' % out)


def test_remove_with_no_group_argument_still_removes_from_every_group(page):
    """The keyboard / menu-bar path has no group in hand, and must keep
    meaning "take these screens out of whatever holds them"."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(6);
      window.__gi.select([ids[0], ids[1], ids[2]]);
      await window.app.groupSelectedLayers();
      await window.__gi.settle();
      window.__gi.select([ids[3], ids[4], ids[5]]);
      await window.app.groupSelectedLayers();
      await window.__gi.settle();
      window.__gi.select([ids[0], ids[3]]);
      await window.app.removeSelectedFromGroup();
      await window.__gi.settle(600);
      return { ids, groups: window.__gi.groups() };
    }""")
    ids = out['ids']
    members = [i for g in out['groups'] for i in g['layer_ids']]
    assert ids[0] not in members, out
    assert ids[3] not in members, out


# ══════════════════════════════════════════════════════════════════════════
# 2. the commit adopts the repaired project whole
# ══════════════════════════════════════════════════════════════════════════

def test_duplicate_group_lands_where_the_server_put_it(page):
    """Panel x/y are ABSOLUTE. The clone takes a 50 px nudge on offset_x/y and
    the server re-anchors its panels to match; before the fix the client kept
    the deep-copied panels, so the copy drew exactly on top of the original and
    Duplicate Group looked like it had done nothing."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2);
      window.__gi.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__gi.settle();
      const newGid = await window.app.duplicateGroup(gid);
      await window.__gi.settle(500);
      const grp = (window.app.project.groups || []).find(g => g.id === newGid);
      const src = window.__gi.layer(ids[0]);
      const clone = window.__gi.layer(grp.layer_ids[0]);
      const server = await window.__gi.serverProject();
      const sClone = server.layers.find(l => l.id === clone.id);
      return {
        srcPanel0: [src.panels[0].x, src.panels[0].y],
        clonePanel0: [clone.panels[0].x, clone.panels[0].y],
        serverClonePanel0: [sClone.panels[0].x, sClone.panels[0].y],
        cloneOffset: [clone.offset_x, clone.offset_y],
        srcOffset: [src.offset_x, src.offset_y],
      };
    }""")
    assert out['cloneOffset'][0] == out['srcOffset'][0] + 50, out
    assert out['clonePanel0'] == out['serverClonePanel0'], (
        'the client kept its own panel geometry instead of the re-anchored '
        'one the server sent back: %r' % out)
    assert out['clonePanel0'][0] == out['srcPanel0'][0] + 50, out


def test_ungroup_leaves_client_and_server_holding_the_same_wiring(page):
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2);
      window.__gi.select(ids);
      const gid = await window.app.groupSelectedLayers();
      await window.__gi.settle();
      const a = window.__gi.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: ids[1] } ] };
      await fetch('/api/layer/' + a.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(a) });
      window.__gi.select(ids);
      await window.app.ungroupSelectedLayers(gid);
      await window.__gi.settle(500);
      const server = await window.__gi.serverProject();
      const hist = window.app.history[window.app.historyIndex].project
        .layers.find(l => l.id === ids[0]).customPortPaths;
      return {
        client: window.__gi.layer(ids[0]).customPortPaths || null,
        server: server.layers.find(l => l.id === ids[0]).customPortPaths || null,
        snapshot: hist || null,
      };
    }""")
    assert out['client'] == out['server'], (
        'client kept a cross-member step the server pruned: %r' % out)
    assert out['snapshot'] == out['server'], (
        'the undo snapshot holds the pre-repair wiring: %r' % out)


def test_two_group_commits_in_flight_both_land(page):
    """Commits are serialized, so the second one's PUT carries the first one's
    repaired state instead of racing it."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(4);
      window.__gi.select([ids[0], ids[1]]);
      const gid = await window.app.groupSelectedLayers();
      await window.__gi.settle();
      // fire two whole-group actions without awaiting the first
      const a = window.app.renameGroup(gid, 'Upstage');
      const b = window.app.toggleGroupLock(gid);
      await Promise.all([a, b]);
      await window.__gi.settle(600);
      const server = await window.__gi.serverProject();
      const g = (server.groups || [])[0];
      return {
        name: g ? g.name : null,
        locked: server.layers.filter(l => (g.layer_ids || []).includes(l.id))
          .map(l => !!l.locked),
        clientName: (window.__gi.groups()[0] || {}).name,
      };
    }""")
    assert out['name'] == 'Upstage', out
    assert out['locked'] == [True, True], out
    assert out['clientName'] == 'Upstage', out


# ══════════════════════════════════════════════════════════════════════════
# 3. the mismatch dialog cannot build a combination that does not exist
# ══════════════════════════════════════════════════════════════════════════

def test_selectable_frame_rates_match_the_sidebar_select(page):
    """getSelectableFrameRates (app-core.js) and updateFrameRateOptions
    (app-export-io.js) are twins. If one grows a rate the other has to."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(1);
      const l = window.__gi.layer(ids[0]);
      window.app.currentLayer = l;
      const processors = [...Object.keys(window.app.portCapacityTables), null];
      const rows = {};
      processors.forEach(p => {
        l.processorType = p;
        window.app.updateFrameRateOptions();
        rows[String(p)] = {
          select: [...document.getElementById('frame-rate').options]
            .map(o => Number(o.value)),
          helper: window.app.getSelectableFrameRates(p),
        };
      });
      return rows;
    }""")
    for processor, pair in out.items():
        assert pair['select'] == pair['helper'], (processor, pair)


def test_dialog_cannot_offer_a_rate_the_chosen_processor_does_not_have(page):
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2, {
        0: { processorType: 'novastar-coex-1g', bitDepth: 12, frameRate: 240 },
        1: { processorType: 'novastar-armor', bitDepth: 12, frameRate: 60 },
      });
      window.__gi.select(ids);
      window.app.groupSelectedLayers();   // not awaited: the dialog blocks it
      await window.__gi.settle(600);
      const before = window.__gi.dialogRows();
      window.__gi.pick('processorType', 'NovaStar (Legacy)');
      await window.__gi.settle(300);
      const after = window.__gi.dialogRows();
      return { ids, before, after, open: window.__gi.dialogOpen() };
    }""")
    assert out['open'], out
    fields = [r['field'] for r in out['after']]
    assert 'frameRate' in fields, out
    rates = next(r for r in out['after'] if r['field'] == 'frameRate')['options']
    assert not any('240' in o for o in rates), (
        'Armor was picked and 240 Hz is still on offer: %r' % out)
    _cancel_dialog(page)


def test_applying_the_dialog_writes_a_combination_the_processor_has(page):
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2, {
        0: { processorType: 'novastar-coex-1g', bitDepth: 12, frameRate: 240 },
        1: { processorType: 'novastar-armor', bitDepth: 12, frameRate: 60 },
      });
      window.__gi.select(ids);
      window.app.groupSelectedLayers();
      await window.__gi.settle(600);
      window.__gi.pick('processorType', 'NovaStar (Legacy)');
      await window.__gi.settle(300);
      document.getElementById('group-settings-apply').click();
      await window.__gi.settle(900);
      const server = await window.__gi.serverProject();
      const members = server.layers.filter(l => ids.includes(l.id));
      return {
        ids,
        settings: members.map(l => [l.processorType, l.bitDepth, l.frameRate]),
        legalRates: window.app.getSelectableFrameRates('novastar-armor'),
        legalDepths: window.app.getSupportedBitDepths('novastar-armor'),
        groups: (server.groups || []).length,
      };
    }""")
    assert out['groups'] == 1, out
    for processor, depth, rate in out['settings']:
        assert processor == 'novastar-armor', out
        assert rate in out['legalRates'], (
            'the group was written at %s Hz, which Armor does not have: %r'
            % (rate, out))
        assert depth in out['legalDepths'], out


def test_low_latency_disagreement_is_a_creation_time_conflict(page):
    """ULL is a processor-wide mode: two Brompton members that disagree sit at
    525,000 and 262,500 px/port, and a port drawn across the boundary is judged
    at whichever figure its owner carries."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2, {
        0: { processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: true },
        1: { processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false },
      });
      window.__gi.select(ids);
      window.app.groupSelectedLayers();
      await window.__gi.settle(600);
      const rows = window.__gi.dialogRows();
      const check = window.app.validateGroupSettings(
        ids.map(id => window.__gi.layer(id)));
      return { rows, open: window.__gi.dialogOpen(),
               conflicts: Object.keys(check.conflicts) };
    }""")
    assert out['open'], 'grouping two members that disagree on ULL asked nothing'
    assert 'lowLatency' in out['conflicts'], out
    assert 'lowLatency' in [r['field'] for r in out['rows']], out
    _cancel_dialog(page)


def test_low_latency_absent_and_off_are_the_same_answer(page):
    """A layer written before the field existed must not read as a third
    value and open a dialog over nothing."""
    ok = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2, {
        all: { processorType: 'brompton', bitDepth: 8, frameRate: 60 },
      });
      const a = window.__gi.layer(ids[0]);
      const b = window.__gi.layer(ids[1]);
      delete a.lowLatency;
      b.lowLatency = false;
      return window.app.validateGroupSettings([a, b]).ok;
    }""")
    assert ok is True


# ══════════════════════════════════════════════════════════════════════════
# 4. the path pruner: the server's rule, and nothing at all without wiring
# ══════════════════════════════════════════════════════════════════════════

def test_pruning_is_a_no_op_on_a_project_with_no_cross_member_wiring(page):
    """The one guarantee an ungrouped project needs: this pass does not touch
    it, not even to rewrite an equal value."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2);
      const a = window.__gi.layer(ids[0]);
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [{ row: 0, col: 0 }, { row: 1, col: 0 }] };
      a.powerCustomPaths = { '1': [{ row: 0, col: 1 }] };
      const before = JSON.stringify(window.app.project);
      const dropped = window.app.pruneStaleCrossLayerPaths();
      return { dropped, before, after: JSON.stringify(window.app.project) };
    }""")
    assert out['dropped'] == 0, out['dropped']
    assert json.loads(out['before']) == json.loads(out['after'])


def test_the_pruner_applies_the_servers_rule_not_the_renderers(page):
    """MEMBERSHIP is the rule, exactly as _prune_cross_layer_paths has it: a
    step is legal while it names a layer in the SAME GROUP.

    canPathReachLayer additionally demands the same canvas, and it is right to
    - it answers "may this be DRAWN", and a cable painted into another
    workspace lands at a position that means nothing. But it is the wrong rule
    for a pass that DELETES: run it on a project the server was still going to
    keep and the wiring is gone, so whether it survived came down to which pass
    ran first. The routes no longer let a group span canvases at all; this pins
    the client rule to the server's regardless of how the state got there."""
    out = page.evaluate(r"""async () => {
      const ids = await window.__gi.fresh(2);
      // The group is built directly on the client's copy: this is a test of
      // the RULE, and nothing here may await, so no in-flight adoption can
      // swap the project out from under the reads below.
      const a = window.__gi.layer(ids[0]);
      const b = window.__gi.layer(ids[1]);
      window.app.project.groups = [
        { id: 'gRule', name: 'Wall', layer_ids: [a.id, b.id] }];
      a.group_id = 'gRule';
      b.group_id = 'gRule';
      a.flowPattern = 'custom';
      a.customPortPaths = { '1': [
        { row: 0, col: 0 }, { row: 0, col: 1, layerId: b.id } ] };
      // the peer sits in another workspace, still in the wall
      b.canvas_id = 'c-somewhere-else';
      const reachable = window.app.canPathReachLayer(a, b);
      const droppedOffCanvas = window.app.pruneStaleCrossLayerPaths();
      // SNAPSHOT, not a reference: the pruner rewrites the arrays in place and
      // a live reference would read back the state after the next call.
      const afterOffCanvas = JSON.stringify(
        window.__gi.layer(ids[0]).customPortPaths || null);
      // now really dissolve the group: the step is illegal on both sides
      window.app.project.groups = [];
      window.app.project.layers.forEach(l => { l.group_id = null; });
      const droppedUngrouped = window.app.pruneStaleCrossLayerPaths();
      return { ids, reachable, droppedOffCanvas, droppedUngrouped,
               afterOffCanvas: JSON.parse(afterOffCanvas),
               afterUngroup: JSON.parse(JSON.stringify(
                 window.__gi.layer(ids[0]).customPortPaths || null)) };
    }""")
    assert out['reachable'] is False, (
        'the renderer would draw a cable onto another canvas: %r' % out)
    assert out['droppedOffCanvas'] == 0, out
    assert out['afterOffCanvas'] == {'1': [
        {'row': 0, 'col': 0},
        {'row': 0, 'col': 1, 'layerId': out['ids'][1]}]}, out
    assert out['droppedUngrouped'] == 1, out
    assert out['afterUngroup'] == {'1': [{'row': 0, 'col': 0}]}, out
