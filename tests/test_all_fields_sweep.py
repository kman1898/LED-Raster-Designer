"""Every editable field in the sidebar, driven the way a user drives it.

Two defects keep turning up one field at a time, and both are invisible until
someone happens to reload the app:

A. THE EDIT DOES NOT STICK. `PUT /api/layer/<id>` copies a FIXED list of keys
   onto the layer (routes_layers.py) and drops everything else on the floor -
   no error, no log line, and it echoes the layer back without the field. The
   client papers over the echo with its own `preservedKeys` list in
   updateLayers() (app-screen-info.js), so the browser looks right while the
   server quietly holds the pre-edit value. The next GET /api/project - a page
   reload - serves the stale copy. `/api/layer/add` has its own separate
   `optional_fields` list, which is how duplicate/paste lost the gradient
   block in v0.11.0.

B. FOCUS DIES MID-EDIT. You type, press Tab, the change handler PUTs, and the
   response (or the socket `layer_updated` echo) rebuilds that part of the UI
   with `innerHTML = ''`. The field Tab had just moved into is destroyed and
   focus falls to <body>, so the next keystroke goes nowhere. Fixed for the
   dock's keyed chip editors via _preserveEditorFocus(); see
   tests/test_label_editor_focus.py.

So this file does not test a hand-written list of fields - a list goes stale
the moment someone adds a control, which is exactly how both bugs survived.
It parses src/templates/index.html, takes EVERY <input>/<select>/<textarea>
inside the sidebar's editing panels, and for each one asserts:

    A1  the edit reached the layer object at all
    A2  the same value is on the SERVER (read back from /api/project)
    A3  the value survives undo-then-redo
    B   after Tab, focus is still in a real field, not <body>
        (typed fields only - a checkbox/select edit involves no Tab)

One test per field, so a failure names the field and the checks it failed
instead of stopping the sweep at the first bad one.

Run locally:
    python3 -m pytest tests/test_all_fields_sweep.py -v --browser chromium
"""

import json
import os
import re
import sys
from html.parser import HTMLParser

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(flask_project_guard):
    """Leave the shared project globals exactly as this module found them.
    The flask variant on purpose: this module runs its OWN e2e server on
    another port (below), so conftest's server_project_guard would spin up -
    and snapshot after - the wrong server. autouse puts the snapshot before
    this module's server fixture resets the globals."""

TEMPLATE = os.path.join(os.path.dirname(__file__), '..', 'src', 'templates',
                        'index.html')

# HTML void elements: they never close, so they must not go on the tag stack
# or every later end-tag would pop the wrong element and the panel a field
# sits in would be mis-attributed.
_VOID = {'input', 'br', 'img', 'hr', 'meta', 'link', 'source', 'area', 'col'}


# ── 1. Enumerate the fields from the template, not from memory ────────────

class _Field:
    """One editable control, plus everything needed to reach and drive it."""

    def __init__(self, key, selector, tag, itype, tab, kind, attrs, options):
        self.key = key            # test id, e.g. "power-line-width"
        self.selector = selector  # CSS selector that resolves to the element
        self.tag = tag            # input | select | textarea
        self.itype = itype        # text | number | checkbox | color | ...
        self.tab = tab            # view tab whose panel holds it
        self.kind = kind          # screen-only | image-only | text-only | any
        self.attrs = attrs        # min / max / step / value / placeholder
        self.options = options    # <select> option values

    def __repr__(self):
        return f'<Field {self.key}>'


class _PanelScanner(HTMLParser):
    """Collect the form controls that live inside the sidebar edit panels.

    The panels are `div.panel.tab-panel[data-tab=...]` plus `#text-layer-panel`
    (shared across tabs). Anything outside them - the toolbar, the export
    modal, Preferences, the log viewer - is project/app state, not layer state,
    and is deliberately out of scope.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack = []
        self._panels = []     # (stack_depth, panel_info)
        self._select = None
        self.fields = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in _VOID:
            self._stack.append(tag)
            classes = (a.get('class') or '').split()
            is_panel = ('tab-panel' in classes) or a.get('id') == 'text-layer-panel'
            if is_panel:
                only = [c for c in ('screen-only', 'image-only', 'text-only')
                        if c in classes]
                self._panels.append((len(self._stack), {
                    # The text panel has no data-tab; it is shown on every tab,
                    # so Pixel Map is as good a place to drive it as any.
                    'tab': a.get('data-tab') or 'pixel-map',
                    'kind': only[0] if only else 'any',
                }))
        if tag in ('input', 'select', 'textarea') and self._panels:
            panel = self._panels[-1][1]
            itype = a.get('type', 'text' if tag == 'input' else tag)
            if itype == 'radio':
                key = f"radio:{a.get('name', '?')}={a.get('value', '?')}"
                selector = (f'input[type="radio"][name="{a.get("name")}"]'
                            f'[value="{a.get("value")}"]')
            elif a.get('id'):
                key = a['id']
                selector = f'#{a["id"]}'
            else:
                # No id and not a radio - nothing stable to address it by.
                return
            field = _Field(key, selector, tag, itype, panel['tab'],
                           panel['kind'],
                           {k: a.get(k) for k in
                            ('min', 'max', 'step', 'value', 'placeholder')},
                           [])
            self.fields.append(field)
            if tag == 'select':
                self._select = field
        elif tag == 'select':
            self._select = None   # a select outside the panels: ignore its options
        if tag == 'option' and self._select is not None:
            self._select.options.append(a.get('value'))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        # Tolerate unclosed tags: unwind to the matching one rather than
        # trusting the stack top.
        while self._stack and self._stack[-1] != tag:
            self._stack.pop()
        if self._stack:
            self._stack.pop()
        while self._panels and self._panels[-1][0] > len(self._stack):
            self._panels.pop()
        if tag == 'select':
            self._select = None


def _discover_fields():
    scanner = _PanelScanner()
    with open(TEMPLATE, encoding='utf-8') as fh:
        scanner.feed(fh.read())
    return scanner.fields


# Fields that are inside an edit panel but are NOT layer state. Each one is
# listed with the reason, and the reasons are asserted below so a control that
# later starts writing to the layer cannot stay quietly excluded.
SKIP = {
    'port-label-bulk-primary':
        'staging box for the Apply button (which stamps every port of the '
        'current screen); typing in it is not meant to change anything '
        'until the button is pressed',
    'port-label-bulk-return':
        'staging box for the Apply button',
    'power-label-bulk':
        'staging box for the Apply button (which stamps every circuit of '
        'the current screen)',
    # The circuit-colour trio is the same shape, and app-core.js proves it:
    # the preset <select> handler only copies its value into the two sibling
    # boxes, and the picker is wired with setupColorPickerWithHex(..., () => {})
    # - an EMPTY callback. Nothing touches powerCircuitColors until "Apply to
    # selected circuits" is clicked, which is a button, not a field.
    'power-circuit-color-preset':
        'fills the custom colour boxes; the Apply button is what writes '
        'powerCircuitColors (app-core.js: the picker callback is empty)',
    'power-circuit-color-custom':
        'staging colour for the Apply button; its picker callback is empty',
    'power-circuit-color-custom-hex':
        'staging colour for the Apply button; its picker callback is empty',
    # Group state, not layer state: the handler writes group.routeDataAsOne
    # through the group commit funnel (PUT /api/project), so the sweep's
    # layer-diff and /api/layer PUT log would both come up empty by design.
    # The sweep project has no groups, so the row is hidden anyway - it only
    # exists while the shown screen belongs to a group.
    'route-group-as-one':
        'writes group.routeDataAsOne on the project, not the layer; driven '
        'end-to-end by tests/test_audit_cross_member.py',
}

ALL_FIELDS = _discover_fields()
FIELDS = [f for f in ALL_FIELDS if f.key not in SKIP]


def test_the_sweep_found_the_panels_at_all():
    """Guard the premise: if the template markup changes shape and the scanner
    silently finds nothing, every parametrized test below would vanish from the
    run and the sweep would report a clean bill of health for zero fields."""
    assert len(ALL_FIELDS) > 100, (
        f'only {len(ALL_FIELDS)} fields found in {TEMPLATE} - the panel '
        'selector (div.tab-panel / #text-layer-panel) no longer matches')
    tabs = {f.tab for f in ALL_FIELDS}
    assert {'pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power'} <= tabs, (
        f'a whole tab is missing from the sweep: found {sorted(tabs)}')


def test_the_mode_toggles_the_sweep_relies_on_still_exist():
    """_MODE_TOGGLE names the checkbox a gated field needs ticked first. A
    renamed toggle would silently stop being clicked, and the field it gates
    would fail A1 for a reason that has nothing to do with the app."""
    keys = {f.key for f in ALL_FIELDS}
    for field_key, toggle in _MODE_TOGGLE.items():
        assert field_key in keys, f'_MODE_TOGGLE gates a field that is gone: {field_key}'
        assert toggle.lstrip('#') in keys, (
            f'the toggle for {field_key} is gone: {toggle}')
    for field_key in _PREPARE_JS:
        assert field_key in keys, (
            f'_PREPARE_JS prepares a field that is gone: {field_key}')


def test_every_skipped_field_still_exists():
    """A skip whose field is gone is a stale exemption - and would hide the
    next control that inherits the id."""
    keys = {f.key for f in ALL_FIELDS}
    missing = sorted(set(SKIP) - keys)
    assert not missing, f'SKIP names fields that no longer exist: {missing}'


# ── 2. A project built here, through the real endpoints ───────────────────

# Built once, then PUT back before every single test. Two "passes alone, fails
# in a full run" incidents in this repo came from inheriting whatever project
# the previous test file left on the shared server, and this file is far more
# destructive than most - it sets columns, cabinet size and half-tiles.
#
# 4x4 of the default 200W cabinet on the default 15A/110V circuit gives the
# power plan two circuits and the data side several ports, so the dock has
# chips to build. Bigger is not safer: a screen too wide to fit one circuit
# has an empty plan and no occupied circuit chips at all.
BUILD_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'SweepScreen',
            columns: 4, rows: 4, cabinet_width: 128, cabinet_height: 128,
        }),
    });
    // A real 1x1 PNG, not a placeholder string: canvas.js throws
    // InvalidStateError out of drawImage the moment an image layer's data URI
    // fails to decode, which takes down render() and every selectLayer() with
    // it. The image layer only has to exist so the image-only controls (scale,
    // drop shadow) become reachable.
    const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAA'
              + 'CQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC';
    await fetch('/api/layer/add-image', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'SweepImage', imageData: PNG,
            imageWidth: 400, imageHeight: 300, offset_x: 900, offset_y: 0,
        }),
    });
    await fetch('/api/layer/add-text', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'SweepText', textContent: 'sweep',
            offset_x: 0, offset_y: 700, textWidth: 400, textHeight: 100,
        }),
    });
    const built = await (await fetch('/api/project')).json();
    window.__sweepPristine = built;
    const byType = (t) => (built.layers || []).find(
        l => (l.type || 'screen') === t);
    return {
        screen: byType('screen').id,
        image: byType('image').id,
        text: byType('text').id,
    };
}"""

# Put the pristine project back and re-seed every derived display the editors
# read. _portsRequired / _powerCircuitsRequired are computed client-side, so a
# layer straight off the server carries neither and the power plan (which the
# dock's circuit chips are built from) comes up empty.
RESET_JS = """async () => {
    const app = window.app;
    const pristine = window.__sweepPristine;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(JSON.parse(JSON.stringify(pristine))),
    });
    app.project = JSON.parse(JSON.stringify(pristine));
    app.dedupeProjectLayers('all_fields_sweep_reset');
    const screen = app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    app.selectLayer(screen);
    app.renderLayers();
    app.updatePortCapacityDisplay();
    app.updatePowerCapacityDisplay();
    app.updatePowerCircuitColorEditor();
    if (window.canvasRenderer) window.canvasRenderer.render();
    // A clean baseline for the undo/redo check: index 0 is this state, so the
    // edit under test is the only thing an undo can step back over.
    app.resetHistory('Sweep Reset');
    return app.project.layers.length;
}"""

SELECT_JS = """(layerId) => {
    const app = window.app;
    const layer = app.project.layers.find(l => l.id === layerId);
    if (!layer) return false;
    app.selectLayer(layer);
    return true;
}"""

# Everything except the two things that make a diff unreadable: `panels` is
# hundreds of objects that any geometry edit rewrites wholesale, and the
# underscore keys are client-side scratch (_portsRequired, _powerTotalAmps1)
# that no route ever persists.
SNAPSHOT_JS = """(layerId) => {
    const app = window.app;
    const layer = (app.project.layers || []).find(l => l.id === layerId);
    if (!layer) return null;
    const out = {};
    Object.keys(layer).forEach(k => {
        if (k === 'panels' || k.charAt(0) === '_') return;
        out[k] = layer[k];
    });
    return JSON.parse(JSON.stringify(out));
}"""

SERVED_JS = """async (layerId) => {
    const p = await (await fetch('/api/project')).json();
    const layer = (p.layers || []).find(l => l.id === layerId);
    if (!layer) return null;
    const out = {};
    Object.keys(layer).forEach(k => {
        if (k === 'panels' || k.charAt(0) === '_') return;
        out[k] = layer[k];
    });
    return JSON.parse(JSON.stringify(out));
}"""

PROBE_JS = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return {found: false};
    return {
        found: true,
        visible: el.offsetParent !== null || el.getClientRects().length > 0,
        disabled: !!el.disabled,
        tag: el.tagName.toLowerCase(),
        type: (el.type || '').toLowerCase(),
        value: el.value,
        checked: !!el.checked,
        // Disabled options are left out: a person cannot pick one, so the
        // sweep may not either (the breakout select disables entries the
        // screen's voltage rules out, and select_option hangs on them).
        options: el.tagName === 'SELECT'
            ? [...el.options].filter(o => !o.disabled).map(o => o.value) : null,
    };
}"""

# Some controls are behind a disclosure their own enabling toggle owns: the
# gradient rows appear only once Gradient is ticked, the custom voltage box
# only once "Custom" is picked, the circuit colour list only in colour-coded
# view. Driving the enabling toggle instead would mean testing that toggle
# twice and this field never, so the container is unhidden directly. The change
# handler does not read visibility, so the edit path under test is unchanged -
# only the reachability is.
REVEAL_JS = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return [];
    const opened = [];
    let node = el;
    while (node && node !== document.body) {
        const style = window.getComputedStyle(node);
        if (style.display === 'none') {
            node.style.display = 'block';
            opened.push(node.id || node.className || node.tagName);
        }
        node = node.parentElement;
    }
    return opened;
}"""

FOCUS_JS = """() => {
    const a = document.activeElement;
    return {
        tag: a ? a.tagName : null,
        id: a ? a.id : null,
        isBody: a === document.body,
        isNull: !a,
    };
}"""

SET_AND_FIRE_JS = """([selector, value]) => {
    const el = document.querySelector(selector);
    if (!el) return false;
    el.value = value;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
}"""

# Record what the client actually PUTs for a layer. The alternative - reading
# the layer object again the instant the handler returns - races the response
# on localhost and gives a different answer run to run. The request body is the
# client's own account of the layer at the moment it saved, so comparing it
# with the layer AFTER the response lands separates the two failures that look
# identical from outside: a control wired to nothing, and a value the client
# sent and the server's key allow-list threw away.
INSTALL_PUT_LOG_JS = """() => {
    if (window.__sweepHooked) return true;
    window.__sweepHooked = true;
    window.__sweepPuts = [];
    const original = window.fetch.bind(window);
    window.fetch = (input, init) => {
        try {
            const url = typeof input === 'string' ? input
                : (input && input.url) || '';
            const method = ((init && init.method)
                || (input && input.method) || 'GET').toUpperCase();
            if (method === 'PUT' && /\\/api\\/layer\\/\\d+$/.test(url)
                    && init && typeof init.body === 'string') {
                window.__sweepPuts.push({url: url, body: init.body});
                if (window.__sweepPuts.length > 40) window.__sweepPuts.shift();
            }
        } catch (e) { /* logging must never break the app under test */ }
        return original(input, init);
    };
    return true;
}"""

CLEAR_PUT_LOG_JS = "() => { window.__sweepPuts = []; return true; }"

LAST_PUT_JS = """(layerId) => {
    const puts = (window.__sweepPuts || []).filter(
        p => p.url.replace(/[?#].*$/, '').endsWith('/api/layer/' + layerId));
    if (!puts.length) return null;
    let body;
    try { body = JSON.parse(puts[puts.length - 1].body); } catch (e) { return null; }
    const out = {};
    Object.keys(body).forEach(k => {
        if (k === 'panels' || k.charAt(0) === '_') return;
        out[k] = body[k];
    });
    return JSON.parse(JSON.stringify(out));
}"""

FOCUS_AND_SELECT_JS = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return false;
    el.focus();
    try { el.select(); } catch (e) { /* number inputs on some engines */ }
    return document.activeElement === el;
}"""


@pytest.fixture(scope="module")
def e2e_server():
    """A live server of this file's own, deliberately NOT conftest's.

    conftest's session server is on a fixed port shared by every browser test
    file (and by any other checkout of this app running its tests at the same
    time). This sweep resets the whole project before each of ~180 fields, so
    sharing a server means either inheriting someone else's project - the
    "passes alone, fails in a full run" failure this repo has already had twice
    - or trampling theirs. Its own port is the only way both stay true.
    """
    import threading
    import time
    import urllib.error
    import urllib.request

    import app as app_module
    from app import app as flask_app, socketio, _build_initial_project

    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1
    flask_app.config['TESTING'] = True

    port = 15794
    threading.Thread(
        target=lambda: socketio.run(flask_app, host='127.0.0.1', port=port,
                                    allow_unsafe_werkzeug=True,
                                    log_output=False),
        daemon=True,
    ).start()

    base = f'http://127.0.0.1:{port}'
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f'{base}/api/project', timeout=1).read()
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    else:
        # Without this the port collision surfaces much later as an opaque
        # "TypeError: Failed to fetch" from inside a page.evaluate.
        pytest.fail(f'the sweep server never came up on {base} - port taken?')
    yield base


@pytest.fixture(scope="module")
def sweep(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = context.new_page()
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_timeout(2000)   # socket connect + app init
    assert page.evaluate(INSTALL_PUT_LOG_JS)
    ids = page.evaluate(BUILD_JS)
    assert ids and ids.get('screen'), f'test project was not built: {ids}'
    page.wait_for_timeout(600)
    yield page, ids
    context.close()


@pytest.fixture()
def fresh(sweep):
    """Put the pristine project back before every field. Each field's edit is
    then the only change in the project and the only entry in history."""
    page, ids = sweep
    count = page.evaluate(RESET_JS)
    assert count == 3, f'reset did not restore the three layers: {count}'
    page.wait_for_timeout(350)
    return page, ids


# ── 3. Reaching a field, and choosing a value to put in it ────────────────

# Which layer types to try, in order, for a field in a panel with this class.
# The class is only a hint: several controls sit in an unclassed panel but
# inside a screen-only or image-only section, so visibility decides.
_KIND_ORDER = {
    'screen-only': ['screen'],
    'image-only': ['image'],
    'text-only': ['text'],
    'any': ['screen', 'image', 'text'],
}

_NUMERIC = re.compile(r'^-?\d+(\.\d+)?$')
_HEX = re.compile(r'^#?[0-9a-fA-F]{6}$')


def _open_tab(page, tab):
    page.locator(f'[data-mode="{tab}"]').click()
    page.wait_for_timeout(250)


# Fields that need app-side work done before they can be probed and planned.
# power-breakout-type is an EMPTY <select> in the markup: refreshSocaRuns()
# fills its options from getPowerBreakoutTypes at runtime, and on this sweep's
# own page nothing may have run it before the field's turn comes - _plan()
# would then find a select with nothing to change to and blame the field.
# The screen is put at 208V first: at 110V the eligibility rule (110V screens
# take Edison only) disables every alternative, and a select with one pickable
# option has nothing for the round-trip to change to.
_PREPARE_JS = {
    'power-breakout-type': """() => {
        const v = document.getElementById('power-voltage-select');
        if (v && v.value !== '208') {
            v.value = '208';
            v.dispatchEvent(new Event('change', { bubbles: true }));
        }
        window.app.refreshSocaRuns();
    }""",
}


def _reach(page, ids, field):
    """Select a layer and open the tab that makes this field reachable.

    Returns (layer_type, layer_id, forced) where `forced` means the field was
    still hidden and its container had to be unhidden.
    """
    prep = _PREPARE_JS.get(field.key)
    for kind in _KIND_ORDER[field.kind]:
        assert page.evaluate(SELECT_JS, ids[kind]), f'no {kind} layer'
        _open_tab(page, field.tab)
        if prep:
            page.evaluate(prep)
        probe = page.evaluate(PROBE_JS, field.selector)
        if probe['found'] and probe['visible']:
            return kind, ids[kind], False
    kind = _KIND_ORDER[field.kind][0]
    page.evaluate(SELECT_JS, ids[kind])
    _open_tab(page, field.tab)
    if prep:
        page.evaluate(prep)
    page.evaluate(REVEAL_JS, field.selector)
    page.wait_for_timeout(100)
    return kind, ids[kind], True


def _number(field, current):
    """A different number, inside the control's own min/max."""
    step = float(field.attrs.get('step') or 1)
    lo = field.attrs.get('min')
    hi = field.attrs.get('max')
    lo = float(lo) if lo not in (None, '') else None
    hi = float(hi) if hi not in (None, '') else None
    base = float(current) if _NUMERIC.match(str(current or '')) else (lo or 0)
    target = base + step * 3
    if hi is not None and target > hi:
        target = base - step * 3
    if lo is not None and target < lo:
        target = lo
    if hi is not None and target > hi:
        target = hi
    if abs(target - base) < 1e-9:                 # already pinned at a bound
        target = base + step if (hi is None or base + step <= hi) else base - step
    return str(int(target)) if float(target).is_integer() and step >= 1 \
        else f'{target:g}'


def _plan(field, probe):
    """(mode, value) - what to put in the field and how to put it there."""
    if probe['tag'] == 'select':
        options = probe['options'] or field.options
        other = [o for o in options if o != probe['value']]
        assert other, f'{field.key}: single-option select, nothing to change to'
        return 'select', other[0]
    if probe['type'] == 'checkbox':
        return 'check', not probe['checked']
    if probe['type'] == 'radio':
        return 'radio', True
    if probe['type'] == 'color':
        # A colour input cannot be typed into; the OS picker is out of reach of
        # a headless browser, so its value is set and its own two listeners
        # (input, change) are fired - the exact pair a real pick fires.
        return 'fire', '#3d7a1f' if probe['value'] != '#3d7a1f' else '#7a1f3d'
    if probe['type'] == 'range':
        # Same reason: a slider drag ends in input+change on the element.
        return 'fire', _number(field, probe['value'])
    current = probe['value'] or ''
    hint = current or (field.attrs.get('placeholder') or '')
    if _HEX.match(hint):
        return 'type', '#3D7A1F' if current.lower() != '#3d7a1f' else '#7A1F3D'
    if hint == '' or _NUMERIC.match(hint):
        return 'type', _number(field, current)
    return 'type', 'SWEEP7'


def _apply(page, field, mode, value):
    locator = page.locator(field.selector)
    if mode == 'select':
        locator.select_option(value)
    elif mode == 'check':
        locator.click()
    elif mode == 'radio':
        locator.click()
    elif mode == 'fire':
        assert page.evaluate(SET_AND_FIRE_JS, [field.selector, value])
    elif mode == 'type':
        assert page.evaluate(FOCUS_AND_SELECT_JS, field.selector), \
            f'{field.key}: could not focus the field'
        page.keyboard.type(str(value))
        # Tab is the commit AND the whole of check B: it fires `change`, and it
        # moves focus into whatever the round-trip is about to rebuild.
        page.keyboard.press('Tab')
    else:
        raise AssertionError(f'unknown mode {mode}')


# A few controls are inert until their own mode is switched on - not merely
# hidden, but read past by the handler. Unhiding the container is not enough:
# updateLayerFromInputs() ignores target-width unless layer.sizeByDimensions is
# true, and the custom port/circuit boxes only mean anything in custom mode.
# This maps a field to the mode toggle a user would have to tick first, and it
# is about gating relationships, not about which fields exist - the field list
# is still the one scanned out of the template.
_MODE_TOGGLE = {
    'target-width': '#size-by-dimensions',
    'target-height': '#size-by-dimensions',
    'target-unit': '#size-by-dimensions',
    'custom-active-port-input': '#custom-flow-toggle',
    'power-custom-active': '#power-custom-toggle',
}


def _prepare(page, field, mode):
    """Work the field needs BEFORE the before-snapshot is taken.

    Timing is the whole point of doing it here. Two of the five radios
    (cabinet-id-style=column-row, cabinet-id-position=center) are the value a
    fresh layer already carries, so clicking them fires no `change` at all -
    the group has to be moved elsewhere first, and if that move happened after
    the snapshot the two clicks would net out to no change and the field would
    be reported as failing A1 with nothing wrong with it. The mode toggles are
    the same: ticking one is a change of its own, and it must not land inside
    the diff attributed to the field under test.
    """
    toggle = _MODE_TOGGLE.get(field.key)
    if toggle and not page.evaluate(PROBE_JS, toggle)['checked']:
        page.locator(toggle).click()
        page.wait_for_timeout(900)
    if mode != 'radio':
        return
    if not page.evaluate(PROBE_JS, field.selector)['checked']:
        return
    name = field.selector.split('name="')[1].split('"')[0]
    page.locator(
        f'input[type="radio"][name="{name}"]:not({field.selector})'
    ).first.click()
    page.wait_for_timeout(600)


# Keys the app fills in from another field when they are missing, rather than
# reading as "not set". applyServerLayer materialises the Show Look position
# from the processor position (app-core.js), and the renderer applies the same
# fallback every frame (canvas.js: `showOffsetX != null ? showOffsetX : procX`).
#
# So when an unrelated edit's round-trip stamps these onto a layer that never
# carried them, a redo that restores a snapshot from BEFORE the stamp is not a
# lost edit: the layer draws in exactly the same place either way. Excluded
# only when the layer did not already carry the key - a Show Look position the
# user actually moved is a real value and must round-trip like any other.
_REDERIVED_KEYS = {'showOffsetX', 'showOffsetY'}


def _diff(before, after):
    keys = set(before) | set(after)
    return {k: (before.get(k), after.get(k)) for k in sorted(keys)
            if before.get(k) != after.get(k)}


def _wait_for_server(page, layer_id, expected, timeout_ms=4000):
    """Poll /api/project until the server agrees, or give up.

    Polled rather than read once: the PUT is in flight when the change handler
    returns, and a race would be a flaky test, not a bug. A field that never
    arrives inside four seconds is not arriving - it was dropped by the route's
    key allow-list.
    """
    waited = 0
    served = None
    while waited <= timeout_ms:
        served = page.evaluate(SERVED_JS, layer_id)
        if served is not None and all(
                served.get(k) == v for k, v in expected.items()):
            return True, served
        page.wait_for_timeout(250)
        waited += 250
    return False, served


# ── 4. The sweep ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('field', FIELDS, ids=lambda f: f.key)
def test_field_round_trip(fresh, field):
    page, ids = fresh
    kind, layer_id, forced = _reach(page, ids, field)
    probe = page.evaluate(PROBE_JS, field.selector)
    assert probe['found'], f'{field.key}: not in the DOM at all'
    assert not probe['disabled'], f'{field.key}: disabled on the {kind} layer'

    mode, value = _plan(field, probe)
    _prepare(page, field, mode)
    if forced and page.evaluate(PROBE_JS, field.selector)['visible']:
        # Its mode toggle opened the section for real; the note would otherwise
        # blame an unhiding that no longer happened.
        forced = False

    before = page.evaluate(SNAPSHOT_JS, layer_id)
    assert before is not None, f'{field.key}: {kind} layer vanished before the edit'

    page.evaluate(CLEAR_PUT_LOG_JS)
    _apply(page, field, mode, value)
    page.wait_for_timeout(1200)   # PUT + response merge + socket echo + rebuild
    sent = page.evaluate(LAST_PUT_JS, layer_id)

    failures = []
    notes = [f'layer={kind} tab={field.tab} mode={mode} value={value!r}'
             + (' (container unhidden)' if forced else '')]

    # ── B: the field Tab moved into must have survived the rebuild ────────
    if mode == 'type':
        focus = page.evaluate(FOCUS_JS)
        if focus['isBody'] or focus['isNull']:
            failures.append(
                f'B: after Tab and the round-trip rebuild, focus is on '
                f'<body> - the next keystroke goes nowhere ({focus})')

    # ── A1: did anything reach the layer object, and did it stay? ────────
    after = page.evaluate(SNAPSHOT_JS, layer_id)
    changed = _diff(before, after)
    # What the client itself said the layer was when it saved. Keys in here
    # that are NOT in `changed` were written, sent, and then put back to their
    # pre-edit value by the response - which only the route's key allow-list
    # can do.
    if sent is None:
        notes.append('no PUT /api/layer/%s fired for this edit' % layer_id)
        wiped = {}
    else:
        wiped = {k: (before.get(k), v) for k, v in sent.items()
                 if before.get(k) != v and k not in changed
                 # A key the layer never carried, stamped with a falsy default
                 # by the save path itself, is not this field's edit - every
                 # Screen Info control PUTs sizeByDimensions:false whether you
                 # touched it or not. It IS dropped by the same allow-list, but
                 # attributing it to twenty unrelated fields buries the one
                 # field that really did set it.
                 and not (k not in before and not v)}
    if wiped:
        failures.append(
            'A1: the client PUT '
            + ', '.join(f'{k}={v[1]!r}' for k, v in wiped.items())
            + ' and the response put the layer straight back to '
            + ', '.join(f'{k}={v[0]!r}' for k, v in wiped.items())
            + ' - the key is absent from the PUT allow-list in '
              'routes_layers.py, so the route echoed a layer without it and '
              'preservedKeys in app-screen-info.js does not cover it either')
    if not changed:
        failures.append(
            'A1: the edit left no property changed on the layer object'
            + (' (see the wipe above)' if wiped else
               ' - the control is not wired to anything that writes the layer'))
    else:
        notes.append('layer keys touched: '
                     + ', '.join(f'{k}={v[1]!r}' for k, v in changed.items()))

        # ── A2: did it reach the server? ─────────────────────────────────
        expected = {k: v[1] for k, v in changed.items()}
        ok, served = _wait_for_server(page, layer_id, expected)
        if not ok:
            if served is None:
                failures.append('A2: the layer is not on the server at all')
            else:
                lost = {k: (v, served.get(k)) for k, v in expected.items()
                        if served.get(k) != v}
                failures.append(
                    'A2: the server never took '
                    + ', '.join(f'{k} (sent {s!r}, server holds {g!r})'
                                for k, (s, g) in lost.items())
                    + ' - reloading the page would lose this edit')

        # ── A3: does it survive undo then redo? ──────────────────────────
        page.evaluate('() => window.app.undo()')
        page.wait_for_timeout(800)
        undone = page.evaluate(SNAPSHOT_JS, layer_id)
        page.evaluate('() => window.app.redo()')
        page.wait_for_timeout(800)
        redone = page.evaluate(SNAPSHOT_JS, layer_id)
        if redone is None:
            failures.append('A3: the layer is gone after undo/redo')
        else:
            lost = {k: (v, redone.get(k)) for k, v in expected.items()
                    if redone.get(k) != v
                    and not (k in _REDERIVED_KEYS and k not in before)}
            if lost:
                reverted = undone is not None and any(
                    undone.get(k) == before.get(k) for k in expected)
                failures.append(
                    'A3: undo-then-redo did not bring the edit back: '
                    + ', '.join(f'{k} (edited to {s!r}, now {g!r})'
                                for k, (s, g) in lost.items())
                    + ('' if reverted else
                       ' - and undo never reverted it either, so this edit is '
                       'outside the history system'))

    assert not failures, (
        f'{field.key}\n  ' + '\n  '.join(notes) + '\n  '
        + '\n  '.join(failures))


# ── 5. The editors that build their own fields ────────────────────────────
#
# Two surfaces still build their controls at runtime rather than in
# index.html: the hardware dock (app-dock.js draws a port chip per card port,
# each holding a keyed Name/Return editor, and wipes #hardware-dock-body with
# `innerHTML = ''` on every render) and the circuit colour list. Those wipes
# are the source of defect B, so the checks run over whatever rows the live
# page has built. The container ids ARE in the template, which is what keeps
# this from being a hand-written list of field names.

_EDITOR_ANCHORS = ['hardware-dock-body', 'power-circuit-color-list']


def test_the_editor_containers_are_still_in_the_template():
    """The ids above are the anchors the dynamic sweep hangs off. If one is
    renamed, its editor drops out of the run silently."""
    with open(TEMPLATE, encoding='utf-8') as fh:
        markup = fh.read()
    missing = [i for i in _EDITOR_ANCHORS if f'id="{i}"' not in markup]
    assert not missing, f'editor containers gone from the template: {missing}'

EDITOR_FIELDS_JS = """(listId) => {
    const list = document.getElementById(listId);
    if (!list) return null;
    return {
        // Every control in the list, and separately the ones carrying the
        // stable key _preserveEditorFocus() restores focus by. A list full of
        // controls with no keys is not an empty editor - it is an editor some
        // OTHER renderer built over the top of the keyed one.
        controls: list.querySelectorAll('input, select, textarea').length,
        keyed: [...list.querySelectorAll('[data-lrd-field]')].map(el => ({
            key: el.dataset.lrdField,
            type: (el.type || '').toLowerCase(),
        })),
    };
}"""


def test_power_circuit_color_list_rows_carry_keys(fresh):
    """The colour list is genuinely checkboxes and colour swatches - the
    colour itself is set by the picker above the list and applied to
    whichever circuits are ticked. So there is no text to type and no caret
    to lose, and every-row-carries-a-key is the whole contract here: it is
    what makes _preserveEditorFocus() able to work over this list if an
    editable field is ever added to a row."""
    page, ids = fresh
    assert page.evaluate(SELECT_JS, ids['screen'])
    _open_tab(page, 'power')
    # The colour list only exists in colour-coded view, and that toggle is
    # itself swept above - here it is just the way in.
    page.locator('#power-color-coded-view').click()
    page.wait_for_timeout(600)

    built = page.evaluate(EDITOR_FIELDS_JS, 'power-circuit-color-list')
    assert built is not None, 'power-circuit-color-list is not in the DOM'
    rows = built['keyed']
    assert rows, (
        f'power-circuit-color-list holds {built["controls"]} controls but '
        'not one carries a data-lrd-field key. Focus cannot be restored into '
        'a field that has no key, so _preserveEditorFocus() is inert over '
        'this list and defect B is live here')
    text_rows = [r for r in rows if r['type'] == 'text']
    assert not text_rows, (
        f'power-circuit-color-list grew an editable field: {text_rows}. '
        'Drive it through the checks the dock editor test runs instead of '
        'returning here.')


# Seed one processor through the real endpoint so the dock has port chips to
# edit, then rebase history so the undo under test steps back over the rename
# only - not over the seeding.
SEED_PROC_JS = """async () => {
    await fetch('/api/processors', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-mx20', name: 'MX'}),
    });
    await window.app.refreshProcessors();
    window.app.resetHistory('Sweep Dock Seed');
    const proc = window.app._processorsResolved[0];
    const card = proc && proc.slots.map(s => s.card).find(Boolean);
    return card ? card.id : null;
}"""

DOCK_FIELDS_JS = """() => {
    const body = document.getElementById('hardware-dock-body');
    if (!body) return null;
    return {
        controls: body.querySelectorAll('input, select, textarea').length,
        keyed: [...body.querySelectorAll('[data-lrd-field]')]
            .filter(el => /^processor-port-(name|return)-/
                .test(el.dataset.lrdField))
            .map(el => ({
                key: el.dataset.lrdField,
                type: (el.type || '').toLowerCase(),
            })),
    };
}"""

# The chip editors are hidden until the chip opens; go in through the face's
# own click (the user's gesture) rather than unhiding by hand.
OPEN_TILE_JS = """(key) => {
    const el = document.querySelector('[data-lrd-field="' + key + '"]');
    const tile = el && el.closest('.lrd-tile');
    if (!tile) return false;
    if (!tile.classList.contains('lrd-tile-open')) {
        const face = tile.querySelector(':scope > .lrd-tile-face');
        if (face) face.click();
    }
    return tile.classList.contains('lrd-tile-open');
}"""

PORT_NAMES_JS = """async () => {
    const d = await (await fetch('/api/processors')).json();
    const card = (((d.processors || [])[0] || {}).slots || [])
        .map(s => s.card).find(Boolean);
    return card ? {names: card.portNames || {},
                   returns: card.returnPortNames || {}} : null;
}"""


def _served_port_name(page, which, port):
    served = page.evaluate(PORT_NAMES_JS)
    return (served or {}).get(which, {}).get(port)


def _wait_for_port_name(page, which, port, want, timeout_ms=4000):
    """Poll GET /api/processors until the card holds `want` for this port
    (None = until the entry is gone), or give up."""
    waited = 0
    got = None
    while waited <= timeout_ms:
        got = _served_port_name(page, which, port)
        if got == want:
            return True, got
        page.wait_for_timeout(250)
        waited += 250
    return False, got


def test_dock_port_editor_fields_round_trip(fresh):
    """The dock's generated port editors, driven the way a user drives them.

    The A1/A2/A3 layer-state checks do not apply here: these fields write
    PROCESSOR state through PUT /api/processors/.../ports/<n>, not the layer.
    So the dock sweep asserts the same outcomes in the processor's terms -
    focus survives the rebuild (B), the value round-trips to
    GET /api/processors, and one undo walks it back off the card."""
    page, ids = fresh
    card_id = page.evaluate(SEED_PROC_JS)
    assert card_id, 'the seeded processor resolved no card'
    assert page.evaluate(SELECT_JS, ids['screen'])
    _open_tab(page, 'data-flow')
    page.wait_for_timeout(400)

    built = page.evaluate(DOCK_FIELDS_JS)
    assert built is not None, 'hardware-dock-body is not in the DOM'
    rows = [r for r in built['keyed'] if r['type'] == 'text']
    assert rows, (
        f'the dock holds {built["controls"]} controls but no keyed '
        'processor-port-name-*/processor-port-return-* text field. Focus '
        'cannot be restored into a field that has no key, so '
        '_preserveEditorFocus() is inert over the dock and defect B is '
        'live here')

    failures = []
    for row in rows[:2]:     # first two fields: a Name and its Return
        key = row['key']
        selector = f'[data-lrd-field="{key}"]'
        is_name = key.startswith('processor-port-name-')
        which = 'names' if is_name else 'returns'
        port = key.rsplit('-', 1)[1]
        value = ('SWN-' if is_name else 'SWR-') + port

        assert page.evaluate(OPEN_TILE_JS, key), f'{key}: chip did not open'
        page.wait_for_timeout(200)
        assert page.evaluate(FOCUS_AND_SELECT_JS, selector), \
            f'{key}: could not focus the field'
        page.keyboard.type(value)
        page.keyboard.press('Tab')
        page.wait_for_timeout(1200)

        focus = page.evaluate(FOCUS_JS)
        if focus['isBody'] or focus['isNull']:
            failures.append(f'{key} B: focus fell to <body> after the dock '
                            f'rebuilt ({focus})')

        ok, served = _wait_for_port_name(page, which, port, value)
        if not ok:
            failures.append(
                f'{key} A2: GET /api/processors holds {served!r} for port '
                f'{port} (sent {value!r}) - reloading would lose this edit')
            continue

        page.evaluate('() => window.app.undo()')
        page.wait_for_timeout(800)
        ok, served = _wait_for_port_name(page, which, port, None)
        if not ok:
            failures.append(
                f'{key} A3: one undo did not walk the rename back - the '
                f'server still holds {served!r} for port {port}')

    assert not failures, 'hardware-dock-body\n  ' + '\n  '.join(failures)
