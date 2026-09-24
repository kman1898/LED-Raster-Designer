"""One screen's layer PUTs reach the server in the order they were made
(2026-09-24). Each PUT carries the whole layer as it stood when it was made,
and the threaded server can finish two of them out of order, so an older copy
could land last and undo a newer edit. `_putLayer` now chains a screen's PUTs;
these pin that the server sees them in order even when the first is slow, and
that two different screens are not held up by each other."""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


ORDER_JS = """async () => {
    const app = window.app;
    const layer = app.project.layers[0];
    const id = layer.id;
    // Hold the FIRST PUT for this screen back 400 ms at the network level;
    // without the chain the second (newer) PUT lands first and the held,
    // older one overwrites it.
    const realFetch = window.fetch;
    let held = false;
    const seen = [];
    window.fetch = (url, opts) => {
        const u = String(url);
        if (u.startsWith(`/api/layer/${id}`) && opts && opts.method === 'PUT') {
            const name = JSON.parse(opts.body).name;
            seen.push('sent:' + name);
            if (!held) {
                held = true;
                return new Promise(r => setTimeout(r, 400))
                    .then(() => realFetch(url, opts));
            }
        }
        return realFetch(url, opts);
    };
    try {
        const a = app._putLayer(id, Object.assign({}, layer, { name: 'ORDER-OLD' }));
        const b = app._putLayer(id, Object.assign({}, layer, { name: 'ORDER-NEW' }));
        await Promise.all([a, b]);
    } finally {
        window.fetch = realFetch;
    }
    const served = await (await fetch('/api/project')).json();
    return { seen, served: served.layers.find(l => l.id === id).name };
}"""


def test_a_screens_puts_land_in_the_order_they_were_made(page):
    out = page.evaluate(ORDER_JS)
    # the second PUT is not even sent until the first has answered
    assert out['seen'] == ['sent:ORDER-OLD', 'sent:ORDER-NEW'], out
    assert out['served'] == 'ORDER-NEW', out


PARALLEL_JS = """async () => {
    const app = window.app;
    if (app.project.layers.length < 2) {
        await fetch('/api/layer/add', { method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'ORDER-B', columns: 2, rows: 2 }) });
        app.project = await (await fetch('/api/project')).json();
    }
    const [x, y] = app.project.layers;
    const realFetch = window.fetch;
    const started = [];
    window.fetch = (url, opts) => {
        const u = String(url);
        if (opts && opts.method === 'PUT' && u.startsWith('/api/layer/')) {
            started.push(u.split('?')[0]);
            if (u.startsWith(`/api/layer/${x.id}`)) {
                return new Promise(r => setTimeout(r, 400)).then(() => realFetch(url, opts));
            }
        }
        return realFetch(url, opts);
    };
    let yDoneAt = null, xDoneAt = null;
    const t0 = performance.now();
    try {
        const px = app._putLayer(x.id, x).then(() => { xDoneAt = performance.now() - t0; });
        const py = app._putLayer(y.id, y).then(() => { yDoneAt = performance.now() - t0; });
        await Promise.all([px, py]);
    } finally {
        window.fetch = realFetch;
    }
    return { started, xDoneAt, yDoneAt };
}"""


def test_two_screens_are_not_held_up_by_each_other(page):
    out = page.evaluate(PARALLEL_JS)
    assert len(out['started']) == 2, out
    # the other screen's PUT finished while the first was still held
    assert out['yDoneAt'] < out['xDoneAt'], out
