"""The not all attached list follows every card release (owner, 2026-11-04).

"I have released all processors and yet the pins still show attached in the
not attached area": the flag's rows kept a released port attached until the
next release cleared it.

A card's Release Ports is a chain of unpins, one per port. A released socket
that had a port cable typed on it brings the processor tree back with the
reply, and applying the tree re-resolves the assignment
(app-processors _applyProcessorState -> refreshPortAssignment) while the
chain's next unpin is already on its way. That resolve reads the pins before
the next unpin lands; answered after the chain's last reply, it put the older
resolution and the older pins back on the page, and the flag's rows read the
port as attached. Nothing re-resolved until the next release.

The server now numbers every reply before it reads the pins
(routes_port_assignment _stamps) and the page drops a reply older than the
newest it has applied (_assignmentReplyFresh), the processor tree's own rule
(test_processor_state_order.py).

Here, real right-click releases on a scratch show: three screens on three
cards of one processor and a fourth screen on no card, so the flag is red
and its rows are open before the first release. Each screen's sockets carry
a port cable on every port but the last, so the resolve the last cabled
release sends goes out beside the chain's final unpin. The test answers
those resolves from the server the moment they are sent and hands them to
the page only after the chain's last reply: the late delivery a loaded
machine produces. Cards 1 and 2 are released one after another and the flag
is read after each, with no extra gesture; card 3 stays pinned.

Run locally:
    python -m pytest tests/test_attach_flag_after_release.py -v -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Three screens for three cards, a fourth for none. H cards take the Armor
# platform.
SEED_JS = """async () => {
    const j = async (method, url, body) => (await fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    for (let i = 0; i < 4; i++) {
        await j('POST', '/api/layer/add', {name: `S${i + 1}`, columns: 8,
            rows: 4, cabinet_width: 500, cabinet_height: 500,
            offset_x: i * 4400, processorType: 'novastar-armor'});
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    for (let s = 0; s < 3; s++) {
        st = await j('PUT', `/api/processors/${pid}/slots/${s * 2}`,
                     {deviceId: 'novastar-card-h-20xrj45'});
    }
    return {pid, cards: st.processors[0].slots.map(s => s.card)
        .filter(Boolean).map(c => c.id)};
}"""

# S1-S3 onto cards 1-3, then a port cable on every socket each screen holds
# but its last. One undo base.
ATTACH_JS = """async (ids) => {
    const app = window.app;
    const layers = app.project.layers;
    for (let i = 0; i < ids.cards.length; i++) {
        await app._assignmentRequest('/api/port-assignments/place-overflow',
            'POST', {layerId: String(layers[i].id), cardId: ids.cards[i]},
            null, 'Place');
    }
    const held = {};
    (app._assignment.screens || []).forEach(scr => (scr.ports || [])
        .forEach(p => {
            if (p.cardId) (held[p.cardId] = held[p.cardId] || []).push(p.port);
        }));
    for (const cid of ids.cards) {
        const sockets = (held[cid] || []).sort((a, b) => a - b);
        const cables = {};
        sockets.slice(0, -1).forEach(n => { cables[n] = {ft: 50}; });
        await fetch(`/api/processors/${ids.pid}/cards/${cid}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({portCables: cables})});
    }
    await app.refreshProcessors();
    app.resetHistory('Seed');
    return Object.fromEntries(Object.entries(held)
        .map(([k, v]) => [k, v.length]));
}"""

# What the flag shows, what it computes, and the server's truth for the
# same screens.
FLAG_JS = """async () => {
    const app = window.app;
    const flag = document.getElementById('hw-dock-flag');
    const rows = document.getElementById('hw-dock-attach');
    const badge = flag && flag.querySelector('.hw-dock-flag-n');
    const st = app._dockFlagState('data-flow');
    const srv = await (await fetch('/api/port-assignments/resolve', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({screens: app._assignmentScreens()})})).json();
    return {
        red: !!flag && !flag.classList.contains('hw-dock-flag-ok'),
        count: badge ? badge.textContent : null,
        rows: rows ? Array.from(rows.querySelectorAll('.hw-dock-attach-row'))
            .map(r => ({
                name: r.querySelector('.hw-dock-attach-name').textContent,
                cnt: r.querySelector('.hw-dock-attach-cnt').textContent,
            })) : [],
        state: st ? st.screens.map(s => [s.name, s.numbers.length, s.total])
            : null,
        truth: (srv.resolution.screens || [])
            .filter(s => (s.unplaced || []).length)
            .map(s => [s.name, s.unplaced.length, s.required]),
        pins: ((app.project.port_assignments || {}).pins || []).length,
        truthPins: (srv.state.pins || []).length,
    };
}"""

# Counts the page's fetches until each reply's body is read (the idiom of
# test_hardware_dock.py): quiet is none in flight and no snapshot pending,
# for two polls running.
FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""

HIST_LEN_JS = "() => window.app.history.length"


def landed(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


@pytest.fixture(scope="module")
def flag_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    # No real save or open dialog may pop on the desktop.
    for ep in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{ep}',
                 lambda route: route.fulfill(status=403, body=''))
    ready = ("() => window.app && window.app._initialLoadComplete === true"
             " && window.app._socketConnects >= 1")
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(ready)
    ids = pg.evaluate(SEED_JS)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function(ready)
    landed(pg)
    yield pg, ids
    context.close()


# While armed, every resolve goes to the server the moment the page sends it,
# but its reply reaches the page only when released. An unpin sent while one
# of those resolves is still with the server waits for it to be answered: the
# resolve sent just before an unpin reads the older pins, the order the
# server takes them in on the owner's machine when the reply comes back late.
LATE_JS = """(() => {
    const orig = window.fetch;
    const late = window.__late = {armed: false, held: [], asked: []};
    window.fetch = function (url) {
        const u = String(url);
        if (late.armed && u.endsWith('/api/port-assignments/resolve')) {
            const sent = orig.apply(this, arguments);
            late.asked.push(sent.catch(() => null));
            return new Promise(ok => late.held.push(() => ok(sent)));
        }
        if (late.armed && u.endsWith('/api/port-assignments/unpin')) {
            const args = arguments;
            return Promise.all(late.asked).then(() => orig.apply(this, args));
        }
        return orig.apply(this, arguments);
    };
})()"""

RELEASE_LATE_JS = """() => {
    const late = window.__late;
    late.armed = false;
    late.asked = [];
    const held = late.held.splice(0);
    held.forEach(hand => hand());
    return held.length;
}"""


def release_card(page, card_id):
    """The tray's Release Ports: right-click the card, take the clear."""
    key = f'card-{card_id}'
    page.evaluate(
        """(key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (el) el.scrollIntoView({ block: 'nearest' });
        }""", key)
    box = page.locator(f'[data-hwdock="{key}"]').bounding_box()
    assert box, f'no dock card {key}'
    page.mouse.click(box['x'] + box['width'] / 2,
                     box['y'] + box['height'] / 2, button='right')
    item = page.locator('#context-menu [data-action="hw-clear"]')
    assert item.is_visible(), 'the card menu has no clear'
    assert (item.text_content() or '').strip().startswith('Clear ')
    item.click()


def test_each_card_release_shows_at_once_in_the_not_all_attached_list(
        flag_page):
    page, ids = flag_page
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_function(
        "() => window.canvasRenderer.viewMode === 'data-flow'")
    landed(page)
    held = page.evaluate(ATTACH_JS, ids)
    landed(page)
    ports = [held[c] for c in ids['cards']]
    assert all(n > 1 for n in ports), held

    st = page.evaluate(FLAG_JS)
    assert st['red'] and st['count'] == '1', st
    assert st['state'] == st['truth'] == [['S4', ports[0], ports[0]]], st
    # The list is open while the cards are released, the way it was.
    page.locator('#hw-dock-flag').click()
    landed(page)
    assert page.evaluate("() => window.app._dockFlagOpen") is True

    page.evaluate(LATE_JS)
    for k, card in enumerate(ids['cards'][:2]):
        before = page.evaluate(HIST_LEN_JS)
        page.evaluate("() => { window.__late.armed = true; }")
        release_card(page, card)
        # the chain's last unpin has landed when its one step is taken
        page.wait_for_function("(n) => window.app.history.length > n",
                               arg=before, timeout=30000)
        assert page.evaluate(
            "() => window.app.history.slice(-1)[0].action") \
            == 'Release Ports'
        assert page.evaluate(RELEASE_LATE_JS) > 0, (
            'no resolve went out beside the release chain: the cable '
            'set-up did not take')
        landed(page)

        st = page.evaluate(FLAG_JS)
        released = [[f'S{i + 1}', ports[i], ports[i]]
                    for i in range(k + 1)]
        want = released + [['S4', ports[0], ports[0]]]
        assert st['truth'] == want, f'release {k + 1}: server {st}'
        assert st['state'] == want, (
            f'release {k + 1}: the flag reads an older resolution than '
            f'the server holds: {st}')
        assert st['pins'] == st['truthPins'], (
            f'release {k + 1}: the page holds older pins: {st}')
        assert st['red'] and st['count'] == str(len(want)), st
        assert st['rows'] == [
            {'name': name, 'cnt': f'{n} of {total} ports'}
            for name, n, total in want], (
            f'release {k + 1}: the rows show a released port as '
            f'attached: {st}')

    # Card 3 was never released: S3 stays attached and off the list.
    assert 'S3' not in [r['name'] for r in page.evaluate(FLAG_JS)['rows']]
