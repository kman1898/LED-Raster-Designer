"""Clear Circuit / Clear Port on a grouped wall removes the WHOLE run.

Matt's ruling (2026-09-23), on the Quantico file: "a group is one screen and
a circuit is one circuit". There Screen3 owned 16 custom circuits, each 7
cabinets of Screen2 then 7 of its own. Clear Circuit on Screen2 for circuit 1
left Screen3's run 1 at 7 entries instead of none - clearCustomRun only
filtered OUT the steps that landed on the clicked screen, so one physical
cable turned into a stub nobody drew.

The rule now: the clicked screen's run `num` goes, and every peer's run `num`
with a step on the clicked screen goes whole (its override for `num` let go
with it). The 2026-09-22 lock rule is unchanged: a locked peer is skipped
whole and named in one toast; nothing else happens when nothing else may
happen (no history entry, no PUT).

This module builds exactly the Quantico shape - two 7x8 members, the SECOND
owning runs 1 and 2 that each run 7 cabinets across the FIRST then 7 of its
own - and clears from the FIRST, which owns nothing itself. Both sides
(powerCustomPaths / customPortPaths) are parametrized.

Run alone (the live server is shared with the other browser test files):
    python3 -m pytest tests/test_clear_run_whole_circuit.py -v --browser chromium
"""

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
window.__q = {
  async fresh(props) {
    await this.drain();
    await fetch('/api/project/new', { method: 'POST' });
    for (let i = 0; i < 2; i++) {
      await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: 'Screen' + (i + 2), columns: 7, rows: 8,
          cabinet_width: 128, cabinet_height: 128,
          offset_x: i * 1000, offset_y: 0,
        }),
      });
    }
    const p = await (await fetch('/api/project')).json();
    window.app.project = p;
    p.layers.filter(l => (l.type || 'screen') === 'screen').forEach(l => {
      Object.keys(props || {}).forEach(k => { l[k] = props[k]; });
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
  async serverProject() { return await (await fetch('/api/project')).json(); },
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
  // The Quantico run `num`: row (num - 1), 7 cabinets on `first` then 7 on
  // the owner itself.
  run(num, firstId) {
    const row = num - 1;
    const out = [];
    for (let c = 0; c < 7; c++) out.push({ row, col: c, layerId: firstId });
    for (let c = 0; c < 7; c++) out.push({ row, col: c });
    return out;
  },
  trapPuts() {
    this.puts = [];
    const real = window.fetch;
    this._realFetch = real;
    window.fetch = (url, opts) => {
      if (opts && String(opts.method || '').toUpperCase() === 'PUT') this.puts.push(String(url));
      return real(url, opts);
    };
  },
  releasePuts() {
    if (this._realFetch) window.fetch = this._realFetch;
    this._realFetch = null;
    return this.puts || [];
  },
};
"""

_RUN_KEYS = {
    'power': dict(paths='powerCustomPaths', index='powerCustomIndex',
                  overrides='powerCustomOverrides', runs='circuits',
                  pattern='powerFlowPattern', flag='powerCustomPath',
                  clear_one='power-custom-clear-circuit'),
    'data': dict(paths='customPortPaths', index='customPortIndex',
                 overrides='customPortOverrides', runs='ports',
                 pattern='flowPattern', flag=None,
                 clear_one='custom-clear-port'),
}


def _quantico_pair(page, kind):
    """Two grouped 7x8 screens in custom mode. The SECOND owns runs 1 and 2,
    each 7 cabinets across the FIRST then 7 of its own. The FIRST owns
    nothing and is current. Returns [first_id, second_id]."""
    k = _RUN_KEYS[kind]
    props = {k['pattern']: 'custom'}
    if k['flag']:
        props[k['flag']] = True
    return page.evaluate(r"""async ([props, paths, index]) => {
      const ids = await window.__q.fresh(props);
      window.__q.select([ids[0], ids[1]]);
      await window.app.groupSelectedLayers();
      await window.__q.settle();
      const a = window.__q.layer(ids[0]), b = window.__q.layer(ids[1]);
      b[paths] = { 1: window.__q.run(1, ids[0]), 2: window.__q.run(2, ids[0]) };
      b[index] = 1;
      await window.app.updateLayers([a, b]);
      await window.__q.settle();
      window.__q.select([ids[0]]);
      window.__q.layer(ids[0])[index] = 1;
      return ids;
    }""", [props, k['paths'], k['index']])


def _toasts(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#app-toast-host div')].map(d => d.textContent)")


def _clear_toasts(page):
    page.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


def _state(page, ids, kind):
    k = _RUN_KEYS[kind]
    return page.evaluate(r"""async ([ids, paths]) => {
      const srv = await window.__q.serverProject();
      const pick = (l) => (l && l[paths]) || {};
      return {
        a: pick(window.__q.layer(ids[0])), b: pick(window.__q.layer(ids[1])),
        sa: pick(srv.layers.find(l => l.id === ids[0])),
        sb: pick(srv.layers.find(l => l.id === ids[1])),
        steps: window.app.history.length,
      };
    }""", [ids, k['paths']])


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_from_the_member_that_owns_nothing_removes_the_owners_whole_run(page, kind):
    """The Quantico shape. Clear Circuit / Clear Port for run 1 on the FIRST
    screen removes the SECOND's run 1 whole - the 7 steps on the first AND the
    7 on the second - on the client and the server; run 2 keeps all 14; one
    history entry."""
    k = _RUN_KEYS[kind]
    ids = _quantico_pair(page, kind)
    before = _state(page, ids, kind)
    assert len(before['b'].get('1', [])) == 14 and len(before['b'].get('2', [])) == 14, before
    assert before['a'] == {}, before
    _clear_toasts(page)
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    out = _state(page, ids, kind)
    assert '1' not in out['b'], (
        'the owner kept its part of the circuit after Clear on its peer: %d steps' % len(out['b'].get('1', [])))
    assert '1' not in out['sb'], 'the server still holds run 1: %r' % out['sb'].get('1')
    assert '1' not in out['a'] and '1' not in out['sa'], out
    expected_2 = [{'row': 1, 'col': c, 'layerId': ids[0]} for c in range(7)] \
        + [{'row': 1, 'col': c} for c in range(7)]
    assert out['b'].get('2') == expected_2, 'run 2 was touched: %r' % out['b'].get('2')
    assert out['sb'].get('2') == expected_2, out['sb'].get('2')
    assert out['steps'] - before['steps'] == 1, (
        'Clear took %d undo steps' % (out['steps'] - before['steps']))
    assert _toasts(page) == [], _toasts(page)


@pytest.mark.parametrize('kind', ['power', 'data'])
def test_clear_run_with_the_owner_locked_removes_nothing_and_says_so(page, kind):
    """Same shape, then the owner is locked and run 2 is cleared from the
    first screen: the owner is skipped whole - all 14 steps of run 2 stay,
    on the client and the server - the locked toast names it, and with
    nothing else to clear there is no history entry and no PUT."""
    k = _RUN_KEYS[kind]
    ids = _quantico_pair(page, kind)
    page.evaluate("""([ids, index]) => {
      window.__q.layer(ids[1]).locked = true;
      window.__q.layer(ids[0])[index] = 2;
    }""", [ids, k['index']])
    before = _state(page, ids, kind)
    _clear_toasts(page)
    page.evaluate("() => window.__q.trapPuts()")
    page.evaluate("(id) => document.getElementById(id).click()", k['clear_one'])
    page.wait_for_timeout(1200)
    puts = page.evaluate("() => window.__q.releasePuts()")
    toasts = _toasts(page)
    out = _state(page, ids, kind)
    assert out['b'] == before['b'], 'a locked owner lost part of a run: %r' % out['b']
    assert out['sb'] == before['sb'], out['sb']
    assert len(out['b'].get('2', [])) == 14, out['b'].get('2')
    assert out['steps'] == before['steps'], (
        'Clear that cleared nothing took %d undo steps' % (out['steps'] - before['steps']))
    layer_puts = [u for u in puts if '/api/layer/' in u or u.endswith('/api/project')]
    assert layer_puts == [], puts
    owner = page.evaluate("(id) => window.__q.layer(id).name", ids[1])
    assert toasts == ['%s is locked — its %s were left alone.' % (owner, k['runs'])], toasts
