"""A window two guide steps share stays up from one to the next.

Owner report (Matt, 2026-11-04, the What's New list from 1.5.2): steps 11
and 12 (A name for each jumper, Panels on the pull sheet) both work in the
Export dialog on the pull sheet, and each step "collapses the window and
then reopens the exact same window". The runner's rule (quickstart.js
windowsOf / sharedWindows / S.keep): a step names the windows it works in
(`window`), and on Next or Back a window both steps name is never closed,
never opened again, and a restore between the steps refills it in place.
A step jumped to, replayed or run alone still sets its window up itself.

The proofs here are an element identity check and a MutationObserver on
the window: a close and a reopen, however quick, leaves a style record
whose old value is display:none, and fails. A window the step's own act
closes (Edit rows hides the Export dialog under the pull sheet editor) is
the act's business and is told apart by the engine's phase.

Run locally:
    python -m pytest tests/test_guide_windows.py -n 4 --dist loadfile
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_tour_anchors import STATE_JS, _wait_step  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The guides mutate the shared server project and its preferences;
    leave both as this module found them."""


def _no_dialogs(route):
    route.fulfill(status=200, content_type='application/json',
                  body='{"ok": false, "cancelled": true}')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    # The snapshot builder's viewport, so the steps play on the walls the
    # shipped snapshots frame.
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real save or open dialog may come up on the desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _no_dialogs)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


@pytest.fixture(autouse=True)
def _guide_closed(page):
    yield
    page.evaluate("() => window.QuickStart.end()")
    page.wait_for_function(
        "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
        timeout=60000)


SPEED = 3

# ── the inventory ────────────────────────────────────────────────────────
# Every run of consecutive steps that share a window, per guide. A step
# added beside one of these, or a new shared window, changes the list and
# fails test_shared_window_runs_are_the_known_ones until it is named here
# (and so covered by the drives below).
ADVANCED_RUNS = [
    ['sameAsLast', 'avgPower'],                              # picker:add
    ['redundancy', 'backupProcessor', 'processorIp'],        # gear:proc
    ['distroPhase', 'distroRating', 'distroMain',
     'distroPreset', 'distroRows'],                          # gear:distro
    ['jumperNames', 'pullPanels'],                           # export:pull-sheet
    ['cableStock', 'cableStockPerKind'],                     # prefs:stock
    ['outputOpen', 'outputChoices'],                         # output
    ['exportBinder', 'screenOrder', 'wiringTick', 'riggingSheet',
     'fiberPage', 'titleBlock'],                             # export:binder
]
QUICK_RUNS = []
# The What's New lists for every 1.5 version a person can come from.
# Cable stock (1.5.3) and A list for each kind of cable (1.6.0) sit side by
# side in Preferences on Cable stock (owner, 2026-11-04), so every list from
# before 1.5.3 holds Preferences open between them; from 1.5.3 Cable stock
# is not new and A list for each kind of cable runs alone.
WHATS_NEW_RUNS = {
    '1.5.0': [['sameAsLast', 'avgPower'], ['jumperNames', 'pullPanels'],
              ['cableStock', 'cableStockPerKind'], ['outputOpen', 'outputChoices'],
              ['riggingSheet', 'fiberPage']],
    '1.5.1': [['sameAsLast', 'avgPower'], ['jumperNames', 'pullPanels'],
              ['cableStock', 'cableStockPerKind'], ['outputOpen', 'outputChoices'],
              ['riggingSheet', 'fiberPage']],
    '1.5.2': [['sameAsLast', 'avgPower'], ['jumperNames', 'pullPanels'],
              ['cableStock', 'cableStockPerKind'], ['outputOpen', 'outputChoices'],
              ['riggingSheet', 'fiberPage']],
    '1.5.3': [['sameAsLast', 'avgPower'], ['jumperNames', 'pullPanels'],
              ['outputOpen', 'outputChoices'], ['riggingSheet', 'fiberPage']],
}

# Each step's declared windows as a token the page can compare without
# the show: a key, or the name of the function that makes one.
TOKENS_JS = """(keys) => {
    const S = window.QuickStart.steps();
    return keys.map(k => {
        let w = S[k] && S[k].window;
        if (!w) return [];
        if (typeof w === 'function') return ['fn:' + (w.name || '?')];
        return Array.isArray(w) ? w : [w];
    });
}"""


def _runs(page, keys):
    toks = page.evaluate(TOKENS_JS, keys)
    runs, cur = [], None
    for i in range(1, len(keys)):
        if set(toks[i - 1]) & set(toks[i]):
            if cur is None:
                cur = [keys[i - 1]]
                runs.append(cur)
            cur.append(keys[i])
        else:
            cur = None
    return runs


def _tour_keys(page, name):
    return page.evaluate(
        "(n) => { const S = window.QuickStart.steps(); const list = window.QuickStart.tours()[n];"
        " return list.map(s => Object.keys(S).find(k => S[k] === s)); }", name)


def test_shared_window_runs_are_the_known_ones(page):
    """The runs, per guide: Advanced, Quick Start, and What's New from every
    1.5 version. The owner's two reports are among them: What's New from
    1.5.2 steps 11 and 12 share the Export dialog on the pull sheet (15
    and 16 since Quick Palettes and IP addresses, both 1.7.0 steps, and
    Single mode or multimode and Every box in one list, both 1.6.0 steps,
    came in before them)."""
    assert _runs(page, _tour_keys(page, 'advanced')) == ADVANCED_RUNS
    assert _runs(page, _tour_keys(page, 'quick')) == QUICK_RUNS
    for after, want in WHATS_NEW_RUNS.items():
        keys = page.evaluate("(v) => window.QuickStart.newSteps(v, null)", after)
        assert _runs(page, keys) == want, after
    keys = page.evaluate("() => window.QuickStart.newSteps('1.5.2', null)")
    # the owner's steps 11 and 12, four places on since Quick Palettes and
    # IP addresses (1.7.0), Single mode or multimode and Every box in one
    # list (both 1.6.0) came in ahead of them
    assert keys[14:16] == ['jumperNames', 'pullPanels'], keys
    assert 'fiberMode' in keys[:14] and 'procCableList' in keys[:14], keys
    assert 'quickPalettes' in keys[:14] and 'processorIp' in keys[:14], keys
    assert page.evaluate("() => window.QuickStart.windowsOf('jumperNames')") == ['export:pull-sheet']
    # Cable stock, then A list for each kind of cable, then the stock
    # pieces typed into the tray (owner, 2026-11-04)
    i = keys.index('cableStock')
    assert keys[i:i + 3] == ['cableStock', 'cableStockPerKind', 'cableStockPieces'], keys
    for k in ('cableStock', 'cableStockPerKind'):
        assert page.evaluate("(k) => window.QuickStart.windowsOf(k)", k) == ['prefs:stock'], k
    assert page.evaluate("() => window.QuickStart.windowsOf('cableStockPieces')") == []


# ── watching a window across a step change ───────────────────────────────
# The windows step `a` and step `b` both name, as they read now.
SHARED_JS = """([a, b]) => {
    const Q = window.QuickStart, B = Q.windowsOf(b);
    return Q.windowsOf(a).filter(k => B.includes(k));
}"""

# Watch every shared window that is up right now: its element, and every
# style record and removal on it, with the engine's phase when it landed.
WATCH_JS = """(keys) => {
    const a = window.app;
    const id = k => k.startsWith('export:') ? 'export-modal'
        : k.startsWith('prefs:') ? 'preferences-modal'
        : k === 'pull-sheet' ? 'pull-sheet-modal'
        : k.startsWith('gear:') ? 'hw-gear-popover'
        : k.startsWith('picker:') ? 'preset-picker-modal'
        : k === 'output' ? 'output-display-modal' : null;
    const isOpen = (k, el) => {
        if (!el || !el.isConnected || el.style.display !== 'block') return false;
        if (k.startsWith('gear:')) return !!(a._hwPopover && 'gear:' + a._hwPopover.id === k);
        if (k.startsWith('export:')) return document.getElementById('export-format').value === k.slice(7);
        if (k.startsWith('prefs:')) return a._prefsTab === k.slice(6);
        return true;
    };
    const w = {keys: [], els: {}, events: []};
    keys.forEach(k => {
        const el = document.getElementById(id(k));
        if (isOpen(k, el)) { w.keys.push(k); w.els[k] = el; }
    });
    const phase = () => window.QuickStart.state().phase;
    const index = () => window.QuickStart.state().index;
    w.check = () => {
        w.keys.forEach(k => {
            if (!isOpen(k, w.els[k])) w.events.push({k, what: 'closed', phase: phase(), index: index()});
        });
    };
    w.obs = new MutationObserver(recs => {
        const ph = phase(), ix = index();
        recs.forEach(r => {
            w.keys.forEach(k => {
                const el = w.els[k];
                if (r.target === el && r.type === 'attributes'
                        && /display:\\s*none/.test(r.oldValue || '')) {
                    w.events.push({k, what: 'hidden', phase: ph, index: ix});
                }
                if (r.type === 'childList' && !el.isConnected) {
                    w.events.push({k, what: 'detached', phase: ph, index: ix});
                }
            });
        });
        w.check();
    });
    w.obs.observe(document.body, {attributes: true, attributeOldValue: true,
                                  attributeFilter: ['style'], subtree: true, childList: true});
    window.__qsWatch = w;
    return w.keys;
}"""

# Stop watching: the events, and whether each element is still the one
# that was watched, in the page and up.
UNWATCH_JS = """() => {
    const w = window.__qsWatch;
    if (!w) return null;
    w.obs.disconnect();
    window.__qsWatch = null;
    const ids = {'export': 'export-modal', 'prefs': 'preferences-modal', 'pull-sheet': 'pull-sheet-modal',
                 'gear': 'hw-gear-popover', 'picker': 'preset-picker-modal',
                 'output': 'output-display-modal'};
    const same = {};
    w.keys.forEach(k => {
        const el = document.getElementById(ids[k.split(':')[0]]);
        same[k] = el === w.els[k] && el.isConnected;
    });
    return {keys: w.keys, events: w.events, same};
}"""

# Until the step at `index` has started its act (the window the change
# held is then the act's), or settled when it has none.
WAIT_ACT_JS = """(i) => {
    const s = window.QuickStart.state();
    return s.index === i && (s.phase === 'act' || s.phase === 'settled');
}"""


def _step_change(page, button, frm, to, keys, where):
    """Press Next or Back from step `frm` to step `to` while every window
    the two steps share is watched; returns the problems found."""
    problems = []
    shared = page.evaluate(SHARED_JS, [keys[frm], keys[to]])
    watched = page.evaluate(WATCH_JS, shared) if shared else []
    page.locator(button).click()
    if shared:
        page.wait_for_function(WAIT_ACT_JS, arg=to, timeout=120000)
        # The window held through the change is up as the act starts.
        page.evaluate("() => window.__qsWatch && window.__qsWatch.check()")
        res = page.evaluate(UNWATCH_JS)
        bad = [e for e in res['events'] if e['phase'] != 'act']
        if bad:
            problems.append(f"{where}: {keys[frm]} -> {keys[to]} closed a shared window: {bad}")
        for k, ok in res['same'].items():
            if not ok:
                problems.append(f"{where}: {keys[frm]} -> {keys[to]}: {k} is not the element it was")
    st = _wait_step(page, to, timeout=120)
    if not st or st['qs']['index'] != to or st['state'] not in ('done', 'idle') or st['fail']:
        problems.append(f"{where}: step {to + 1} ({keys[to]}) did not take: {st}")
    return problems, shared, watched


def _start_advanced(page):
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", SPEED)
    page.evaluate("() => { window.QuickStart.startAdvanced(); }")
    return _wait_step(page, 0)


def _jump(page, n):
    """Go to step n (1-based) through the Go to box's own path."""
    page.evaluate("(n) => { window.QuickStart.jumpTo(n); }", n)
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=n - 1, timeout=240000)
    return _wait_step(page, n - 1, timeout=120)


def _run_pairs(runs):
    return {(r[j], r[j + 1]) for r in runs for j in range(len(r) - 1)}


def test_advanced_guide_keeps_shared_windows_up(page):
    """The whole Advanced Guide by Next: every step takes, and at every
    change inside a run the shared window is never closed or replaced
    before the next step's act starts. Every pair in ADVANCED_RUNS is seen
    with its window up as Next is pressed."""
    keys = _tour_keys(page, 'advanced')
    st = _start_advanced(page)
    problems, held = [], set()
    if st['state'] not in ('done', 'idle'):
        problems.append(f"step 1 did not take: {st}")
    for i in range(len(keys) - 1):
        p, shared, watched = _step_change(page, '#qs-next', i, i + 1, keys, 'advanced')
        problems += p
        if watched:
            held.add((keys[i], keys[i + 1]))
    missing = _run_pairs(ADVANCED_RUNS) - held
    assert not missing, f"no window was up to hold for {sorted(missing)}"
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize('after', ['1.5.2', '1.5.3'])
def test_whats_new_keeps_shared_windows_up(page, after):
    """What's New from 1.5.2 and from 1.5.3, every step by Next, each from
    its own entry snapshot: every step takes, and the shared windows stay
    up through the snapshot restore between the steps. The acceptance
    cases, from 1.5.2: steps 11 and 12 keep the Export dialog on the pull
    sheet up, the same element, never hidden; and Cable stock and A list
    for each kind of cable keep Preferences on Cable stock up the same way
    (owner, 2026-11-04), closed before the stock pieces step types into
    the tray."""
    keys = page.evaluate("(v) => window.QuickStart.newSteps(v, null)", after)
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", SPEED)
    page.evaluate("(k) => { window.QuickStart.startSteps(k); }", keys)
    st = _wait_step(page, 0, timeout=120)
    problems, held = [], set()
    if st['state'] not in ('done', 'idle') or st['fail']:
        problems.append(f"step 1 did not take: {st}")
    for i in range(len(keys) - 1):
        p, shared, watched = _step_change(page, '#qs-next', i, i + 1, keys, f"what's new from {after}")
        problems += p
        if watched:
            held.add((keys[i], keys[i + 1]))
        if keys[i + 1] == 'cableStockPieces' and page.evaluate(
                "() => document.getElementById('preferences-modal').style.display === 'block'"):
            problems.append('Preferences was still up over the tray in A run made of stock pieces')
        qs = page.evaluate("window.QuickStart.state()")
        if qs['jumpedVia'] != 'snapshot':
            problems.append(f"step {i + 2} ({keys[i + 1]}) did not start from its snapshot: {qs}")
    missing = _run_pairs(WHATS_NEW_RUNS[after]) - held
    assert not missing, f"no window was up to hold for {sorted(missing)}"
    if after == '1.5.2':
        assert ('jumperNames', 'pullPanels') in held and keys.index('jumperNames') == 14
        assert ('cableStock', 'cableStockPerKind') in held, sorted(held)
        assert keys.index('cableStockPerKind') == keys.index('cableStock') + 1, keys
        assert keys.index('cableStockPieces') == keys.index('cableStockPerKind') + 1, keys
    assert not problems, "\n".join(problems)


def test_back_through_each_run_keeps_its_window_up(page):
    """Back inside every Advanced run: the step before is restored and
    played again in the window still up. (Back from Panels on the pull
    sheet finds the Export dialog under the editor its act opened; the
    editor is not the earlier step's, so it goes and the dialog comes back
    from under it.)"""
    keys = _tour_keys(page, 'advanced')
    problems = []
    _start_advanced(page)
    for run in ADVANCED_RUNS:
        last = keys.index(run[-1])
        st = _jump(page, last + 1)
        if st['state'] not in ('done', 'idle') or st['fail']:
            problems.append(f"jump to {run[-1]} did not take: {st}")
            continue
        for j in range(last, last - len(run) + 1, -1):
            p, shared, watched = _step_change(page, '#qs-back', j, j - 1, keys, 'back')
            problems += p
            if not watched and (keys[j], keys[j - 1]) != ('pullPanels', 'jumperNames'):
                problems.append(f"back {keys[j]} -> {keys[j - 1]}: no shared window was up")
    assert not problems, "\n".join(problems)


def test_each_step_of_a_run_sets_its_window_up_alone(page):
    """A step of a shared run, jumped to from a step that does not share
    its window or run on its own as What's New, opens its window itself
    and takes."""
    keys = _tour_keys(page, 'advanced')
    problems = []
    _start_advanced(page)
    run_keys = [k for r in ADVANCED_RUNS for k in r]
    for k in run_keys:
        # From the guide's first step: nothing shared is up.
        _jump(page, 1)
        st = _jump(page, keys.index(k) + 1)
        if st['state'] not in ('done', 'idle') or st['fail']:
            problems.append(f"Go to {k}: {st}")
    page.evaluate("() => window.QuickStart.end()")
    page.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                           timeout=60000)
    for k in run_keys:
        page.evaluate("(k) => { window.QuickStart.startSteps([k]); }", k)
        st = _wait_step(page, 0, timeout=120)
        if st['state'] not in ('done', 'idle') or st['fail']:
            problems.append(f"{k} alone: {st}")
        page.evaluate("() => window.QuickStart.end()")
        page.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                               timeout=60000)
    assert not problems, "\n".join(problems)


def test_a_jump_inside_a_run_sets_the_window_up_from_scratch(page):
    """Go to is not Next: from Screen order straight to Border and title
    block the Export dialog is closed and opened again by the step itself,
    as before the rule, and the step takes."""
    keys = _tour_keys(page, 'advanced')
    _start_advanced(page)
    _jump(page, keys.index('screenOrder') + 1)
    page.evaluate(WATCH_JS, ['export:binder'])
    st = _jump(page, keys.index('titleBlock') + 1)
    res = page.evaluate(UNWATCH_JS)
    assert st['state'] == 'done' and not st['fail'], st
    assert any(e['phase'] == 'enter' for e in res['events']), res
    assert page.evaluate("() => document.getElementById('export-modal').style.display") == 'block'
