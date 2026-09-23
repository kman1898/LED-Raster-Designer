"""Screen groups - the v0.11.0 audit fixes, as permanent guards.

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


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


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
    (app-port-routing.js) are twins. If one grows a rate the other has to."""
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


# ---------------------------------------------------------------------------
# Clearing hand-drawn runs on a grouped screen (2026-09-22). A run a member
# owns may sit on a peer's cabinets; Clear Circuit / Clear Port and Clear All
# on the peer used to leave it there with no way to remove it from that screen
# (the Orlando file: SL's circuit 1 was 13 cabinets of SR).
# ---------------------------------------------------------------------------

_RUN_KEYS = {
    'power': dict(paths='powerCustomPaths', index='powerCustomIndex',
                  overrides='powerCustomOverrides', runs='circuits',
                  pattern='powerFlowPattern', flag='powerCustomPath',
                  clear_one='power-custom-clear-circuit', clear_all='power-custom-clear-all'),
    'data': dict(paths='customPortPaths', index='customPortIndex',
                 overrides='customPortOverrides', runs='ports',
                 pattern='flowPattern', flag=None,
                 clear_one='custom-clear-port', clear_all='custom-clear-all'),
}


def _grouped_pair_with_peer_run(page, kind, peer_locked=False, peer_auto=False,
                                current_locked=False, current_empty=False):
    """Two grouped screens; the SECOND owns run 1 made only of the FIRST's
    cabinets, and run 2 of its own. The first is current. Returns the ids.

    peer_auto: the second keeps its automatic pattern and holds run 1 as an
    OVERRIDE (its override list names 1). peer_locked / current_locked: that
    screen's lock is on. current_empty: the first keeps its automatic pattern
    and holds no runs, overrides or index at all."""
    k = _RUN_KEYS[kind]
    custom = {k['pattern']: 'custom'}
    if k['flag']:
        custom[k['flag']] = True
    if current_empty:
        props = {'1': dict(custom)}
    else:
        props = {'0': dict(custom)} if peer_auto else {'all': dict(custom)}
    return page.evaluate(r"""async ([props, paths, index, overrides, peerLocked, peerAuto, currentLocked, currentEmpty]) => {
      const ids = await window.__gi.fresh(2, props);
      window.__gi.select([ids[0], ids[1]]);
      await window.app.groupSelectedLayers();
      await window.__gi.settle();
      const a = window.__gi.layer(ids[0]), b = window.__gi.layer(ids[1]);
      b[paths] = { 1: [{ row: 0, col: 0, layerId: ids[0] }, { row: 0, col: 1, layerId: ids[0] }],
                   2: [{ row: 1, col: 1 }] };
      b[index] = 1;
      if (peerAuto) b[overrides] = [1];
      if (peerLocked) b.locked = true;
      if (!currentEmpty) {
        a[paths] = { 1: [{ row: 1, col: 0 }] };
        a[index] = 1;
      }
      if (currentLocked) a.locked = true;
      await window.app.updateLayers([a, b]);
      await window.__gi.settle();
      window.__gi.select([ids[0]]);
      return ids;
    }""", [props, k['paths'], k['index'], k['overrides'],
           bool(peer_locked), bool(peer_auto), bool(current_locked), bool(current_empty)])


def _toasts(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#app-toast-host div')].map(d => d.textContent)")


def _clear_toasts(page):
    page.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_on_a_member_takes_its_cabinets_out_of_a_peers_run(page, kind):
    """Clear Circuit / Clear Port on screen A clears A's run 1 AND removes A's
    cabinets from B's run 1 (emptied, so it goes); B's run 2 is untouched."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind)
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    out = page.evaluate(r"""async ([ids, paths]) => {
      const a = window.__gi.layer(ids[0]), b = window.__gi.layer(ids[1]);
      const srv = await window.__gi.serverProject();
      const sb = srv.layers.find(l => l.id === ids[1]);
      return { a: a[paths], b: b[paths], serverB: sb[paths] };
    }""", [ids, k['paths']])
    assert out['a'].get('1', []) == [], out
    assert '1' not in out['b'], 'the peer run drawn across this screen survived: %r' % out
    assert out['b'].get('2') == [{'row': 1, 'col': 1}], out
    assert '1' not in (out['serverB'] or {}), 'the server still holds the peer run: %r' % out


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_all_on_a_member_clears_the_whole_wall(page, kind):
    """Clear All on a grouped screen clears every member's runs, on the client
    and on the server, in one undo step; an ungrouped screen keeps its own."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind)
    # A third, ungrouped screen with a run of its own must be left alone.
    page.evaluate(r"""async ([paths]) => {
      await fetch('/api/layer/add', { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: 'Loose', columns: 2, rows: 2, cabinet_width: 128,
                               cabinet_height: 128, offset_x: 900, offset_y: 0 }) });
      window.app.project = await window.__gi.serverProject();
      const loose = window.app.project.layers[window.app.project.layers.length - 1];
      loose[paths] = { 1: [{ row: 0, col: 0 }] };
      await window.app.updateLayers([loose]);
      await window.__gi.settle();
      window.__gi.select([window.app.project.layers[0].id]);
    }""", [k['paths']])
    n0 = page.evaluate("() => window.app.history.length")
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_all'])
    page.wait_for_timeout(1200)
    out = page.evaluate(r"""async ([ids, paths, index]) => {
      const srv = await window.__gi.serverProject();
      const pick = (l) => ({ paths: l[paths] || {}, index: l[index] });
      const loose = window.app.project.layers[window.app.project.layers.length - 1];
      return {
        a: pick(window.__gi.layer(ids[0])), b: pick(window.__gi.layer(ids[1])),
        sa: pick(srv.layers.find(l => l.id === ids[0])), sb: pick(srv.layers.find(l => l.id === ids[1])),
        loose: pick(loose), sloose: pick(srv.layers.find(l => l.id === loose.id)),
        steps: window.app.history.length,
      };
    }""", [ids, k['paths'], k['index']])
    for who in ('a', 'b', 'sa', 'sb'):
        assert out[who]['paths'] == {}, '%s still has runs: %r' % (who, out)
        assert out[who]['index'] == 1, out
    assert out['loose']['paths'] == {'1': [{'row': 0, 'col': 0}]}, out
    assert out['sloose']['paths'] == {'1': [{'row': 0, 'col': 0}]}, out
    assert out['steps'] - n0 == 1, 'Clear All took %d undo steps' % (out['steps'] - n0)


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_removes_the_emptied_key_on_this_screen_and_the_peer(page, kind):
    """One shape: an emptied run has no key, on the clicked screen as on the
    peer (the clicked screen used to keep `num: []` while the peer's key was
    deleted). Every reader takes `paths[num] || []`, so nothing tells them
    apart - and undo snapshots and the wire now carry one form."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind)
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    out = page.evaluate(r"""async ([ids, paths]) => {
      const srv = await window.__gi.serverProject();
      return { a: window.__gi.layer(ids[0])[paths], b: window.__gi.layer(ids[1])[paths],
               sa: srv.layers.find(l => l.id === ids[0])[paths] };
    }""", [ids, k['paths']])
    assert '1' not in out['a'], out
    assert '1' not in out['b'], out
    assert '1' not in (out['sa'] or {}), out
    assert out['b'].get('2') == [{'row': 1, 'col': 1}], out


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_on_a_peer_lets_go_of_the_members_emptied_override(page, kind):
    """B is automatic and holds run 1 as an override made of A's cabinets.
    Clear on A empties that run: B's override list must let 1 go and any
    override edit of it must end, the way returnRunToAuto does - otherwise B
    keeps 1 reserved with nothing drawn, an invisible gap in its automatic
    numbering with no route back except Clear All."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind, peer_auto=True)
    before = page.evaluate("([id, ovr]) => window.__gi.layer(id)[ovr]", [ids[1], k['overrides']])
    assert before == [1], before
    page.evaluate("([kind, id]) => { window.app._overrideEditing = { kind, layerId: id, num: 1 }; }",
                  [kind, ids[1]])
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    out = page.evaluate(r"""async ([ids, paths, ovr]) => {
      const b = window.__gi.layer(ids[1]);
      const srv = await window.__gi.serverProject();
      const sb = srv.layers.find(l => l.id === ids[1]);
      return { overrides: b[ovr], paths: b[paths], editing: window.app._overrideEditing,
               serverOverrides: sb[ovr] };
    }""", [ids, k['paths'], k['overrides']])
    assert out['overrides'] == [], out
    assert '1' not in out['paths'], out
    assert out['editing'] is None, out
    assert not out['serverOverrides'], out


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_leaves_a_locked_peers_run_alone_and_says_so(page, kind):
    """B is locked: Clear on A clears A's own run but B's run 1 keeps A's
    cabinets, B is not written, and one toast says it was left alone."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind, peer_locked=True)
    _clear_toasts(page)
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    toasts = _toasts(page)
    out = page.evaluate(r"""async ([ids, paths]) => {
      const srv = await window.__gi.serverProject();
      return { a: window.__gi.layer(ids[0])[paths], b: window.__gi.layer(ids[1])[paths],
               sb: srv.layers.find(l => l.id === ids[1])[paths] };
    }""", [ids, k['paths']])
    assert '1' not in out['a'], out
    assert out['b'].get('1') == [{'row': 0, 'col': 0, 'layerId': ids[0]},
                                 {'row': 0, 'col': 1, 'layerId': ids[0]}], out
    assert out['sb'].get('1') == out['b'].get('1'), out
    peer = page.evaluate("(id) => window.__gi.layer(id).name", ids[1])
    assert toasts == ['%s is locked — its %s were left alone.' % (peer, k['runs'])], toasts


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_all_leaves_a_locked_member_alone_and_says_so(page, kind):
    """Clear All on A with B locked: A goes back to automatic, B keeps its
    runs, index and overrides on the client and the server, one toast."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind, peer_locked=True)
    page.evaluate("([id, ovr, index]) => { const b = window.__gi.layer(id); b[ovr] = [2]; b[index] = 2; }",
                  [ids[1], k['overrides'], k['index']])
    _clear_toasts(page)
    n0 = page.evaluate("() => window.app.history.length")
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_all'])
    page.wait_for_timeout(1200)
    toasts = _toasts(page)
    out = page.evaluate(r"""async ([ids, paths, index, ovr]) => {
      const srv = await window.__gi.serverProject();
      const pick = (l) => ({ paths: l[paths] || {}, index: l[index], overrides: l[ovr] || [] });
      return { a: pick(window.__gi.layer(ids[0])), b: pick(window.__gi.layer(ids[1])),
               sb: pick(srv.layers.find(l => l.id === ids[1])),
               steps: window.app.history.length };
    }""", [ids, k['paths'], k['index'], k['overrides']])
    assert out['a']['paths'] == {} and out['a']['index'] == 1, out
    expected_b = {'1': [{'row': 0, 'col': 0, 'layerId': ids[0]}, {'row': 0, 'col': 1, 'layerId': ids[0]}],
                  '2': [{'row': 1, 'col': 1}]}
    assert out['b'] == {'paths': expected_b, 'index': 2, 'overrides': [2]}, out
    assert out['sb']['paths'] == expected_b, out
    assert out['steps'] - n0 == 1, out
    peer = page.evaluate("(id) => window.__gi.layer(id).name", ids[1])
    assert toasts == ['%s is locked — its %s were left alone.' % (peer, k['runs'])], toasts


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_on_a_locked_current_screen_still_clears(page, kind):
    """A lock guards position only, everywhere else in the app (drag, offset
    fields, Center, Move to Canvas); every other edit on a locked screen goes
    through, so Clear on the locked CURRENT screen does too, and reaches its
    unlocked peer. No toast: nothing was left alone."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind, current_locked=True)
    _clear_toasts(page)
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    out = page.evaluate(r"""([ids, paths]) => ({
      a: window.__gi.layer(ids[0])[paths], b: window.__gi.layer(ids[1])[paths],
      locked: window.__gi.layer(ids[0]).locked })""", [ids, k['paths']])
    assert out['locked'] is True, out
    assert '1' not in out['a'] and '1' not in out['b'], out
    assert _toasts(page) == [], _toasts(page)


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_all_that_clears_nothing_takes_no_step_and_makes_no_put(page, kind):
    """A is automatic with no runs, grouped with locked B that owns a run.
    Clear All on A finds nothing it may clear: the toast says B was left
    alone, and nothing else happens - no history entry and no PUT to A.
    clearAllCustomRuns used to run ensure* and write `{}` / 1 / `[]` onto A,
    which saveState's serialized compare read as a change."""
    k = _RUN_KEYS[kind]
    ids = _grouped_pair_with_peer_run(page, kind, peer_locked=True, current_empty=True)
    _clear_toasts(page)
    n0 = page.evaluate("() => window.app.history.length")
    # A's run fields as they stand (a new screen carries the power pair as
    # server defaults, `{}` and 1; the data pair is absent) - Clear All must
    # leave them byte-identical.
    before = page.evaluate(r"""([id, paths, index, ovr]) => {
      const a = window.__gi.layer(id);
      return JSON.stringify({ paths: a[paths], index: a[index], overrides: a[ovr] });
    }""", [ids[0], k['paths'], k['index'], k['overrides']])
    page.evaluate(r"""() => {
      window.__gi.puts = [];
      const real = window.fetch;
      window.__gi._realFetch = real;
      window.fetch = (url, opts) => {
        if (opts && String(opts.method || '').toUpperCase() === 'PUT') window.__gi.puts.push(String(url));
        return real(url, opts);
      };
    }""")
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_all'])
    page.wait_for_timeout(1200)
    toasts = _toasts(page)
    out = page.evaluate(r"""async ([ids, paths, index, ovr]) => {
      window.fetch = window.__gi._realFetch;
      const a = window.__gi.layer(ids[0]);
      const srv = await window.__gi.serverProject();
      const sb = srv.layers.find(l => l.id === ids[1]);
      return { puts: window.__gi.puts, steps: window.app.history.length,
               a: JSON.stringify({ paths: a[paths], index: a[index], overrides: a[ovr] }),
               sbPaths: sb[paths] };
    }""", [ids, k['paths'], k['index'], k['overrides']])
    peer = page.evaluate("(id) => window.__gi.layer(id).name", ids[1])
    assert toasts == ['%s is locked — its %s were left alone.' % (peer, k['runs'])], toasts
    assert out['steps'] == n0, 'Clear All that cleared nothing took %d undo steps' % (out['steps'] - n0)
    layer_puts = [u for u in out['puts'] if u.endswith('/api/layer/%d' % ids[0])]
    assert layer_puts == [], out['puts']
    assert out['a'] == before, (before, out['a'])
    assert '1' in out['sbPaths'] and '2' in out['sbPaths'], out
