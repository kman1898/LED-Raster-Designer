#!/usr/bin/env python3
"""Build src/static/data/tour_snapshots.json: every tour step's entry snapshot.

The guided tours (src/static/js/quickstart.js) run real gestures on a
scratch show, and the callout's Go to box jumps to a step. A jump BACK is
one restore of that step's entry snapshot; a jump AHEAD used to apply every
step between, which took many seconds. This file makes a jump ahead the
same one restore: for each tour it holds the scratch show exactly as each
step finds it, so QuickStart.jumpTo(n) restores entry snapshot n and plays
step n (Matt, 2026-09-16: "an instant skip to step, not any waiting").

How it is built: a FRESH server (every id counter at 1) on a free port, a
headless Chromium at 1600x950, and for each tour: startTour, Next through
every step at a fast pace (each must end 'done', or this stops and names
the step), then QuickStart.snaps() - the very snapshots Back restores -
written out. Two runs give the same bytes: nothing in the show is
timestamped or random, and the file is written sorted and without
whitespace. Each tour carries its signature (QuickStart.signature: app
version + step keys and titles), so a tour that changed since the file was
built is never restored from it - the app falls back to applying the steps.

Regenerate whenever a step changes what the show looks like, a step is
added, removed, renamed or reordered, or the app version bumps:

    python3 scripts/build_tour_snapshots.py

tests/test_tour_snapshots.py compares the shipped file against the live
tours (signature) and re-derives the Quick tour byte-for-byte.
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
FIXTURE = os.path.join(SRC, 'static', 'data', 'tour_snapshots.json')

TOURS = ('quick', 'whatsNew', 'advanced')
VIEWPORT = {'width': 1600, 'height': 950}
# The pace the steps are driven at while collecting (QuickStart.setSpeed):
# the shipped gestures, six times faster. Zero-pace application would be
# quicker, but every step's note is read here, so a step that stopped
# taking is named rather than buried under the shade.
DRIVE_SPEED = 6

STATE_JS = """() => {
    const c = document.getElementById('qs-callout');
    const r = c && c.querySelector('.qs-result');
    const st = window.QuickStart.state();
    return {
        state: c ? c.getAttribute('data-qs-state') : null,
        title: c && c.querySelector('h3') ? c.querySelector('h3').textContent : '',
        note: r ? r.textContent : '',
        fail: !!(r && r.classList.contains('qs-result-fail')),
        index: st.index, running: st.running, visible: st.visible,
    };
}"""


def strip_volatile(project):
    """The snapshot with everything that may differ between two identical
    runs removed. Today nothing in the scratch show is volatile (no
    timestamps, no random ids - every counter starts at 1 on a fresh
    server); this is where a field would be dropped if one appeared, and
    the comparison test strips through the same function."""
    return project


def canonical(obj):
    """One byte string per project: keys sorted, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def wait_step(page, index, timeout=120):
    deadline = time.time() + timeout
    st = None
    while time.time() < deadline:
        st = page.evaluate(STATE_JS)
        if st['index'] == index and not st['running'] \
                and st['state'] in ('done', 'failed', 'idle'):
            return st
        time.sleep(0.05)
    return st


def collect_tour(page, name, speed=DRIVE_SPEED, log=None):
    """Drive tour `name` from its first step to its last on `page` and
    return {'signature', 'steps': [entry snapshot per step]}. Every step
    with an act must settle 'done'; the first that does not raises
    RuntimeError naming it."""
    log = log or (lambda s: None)
    n = page.evaluate("(n) => window.QuickStart.tours()[n].length", name)
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", speed)
    page.evaluate("(n) => { window.QuickStart.startTour(n); }", name)
    st = wait_step(page, 0)
    if not st or st['index'] != 0:
        raise RuntimeError(f'{name}: the tour never settled on step 1 ({st})')
    for i in range(n):
        if i > 0:
            page.locator('#qs-next').click()
        st = wait_step(page, i)
        where = f"{name} step {i + 1} ({st['title'] if st else '?'!r})"
        if not st or st['index'] != i:
            raise RuntimeError(f'{where}: the engine never settled on this step ({st})')
        if st['state'] == 'failed' or st['fail']:
            raise RuntimeError(f"{where}: its act did not take - {st['note']!r}")
        if st['state'] == 'done' and not st['note'].strip():
            raise RuntimeError(f'{where}: done, but no result note')
        log(f"  {name} {i + 1:2d}/{n} {st['state']:5s} {st['title']!r}: {st['note']!r}")
    snaps = page.evaluate("() => window.QuickStart.snaps()")
    signature = page.evaluate("(n) => window.QuickStart.signature(n)", name)
    page.evaluate("() => window.QuickStart.end()")
    page.wait_for_timeout(400)
    if len(snaps) != n or any(not isinstance(s, dict) for s in snaps):
        raise RuntimeError(f'{name}: {len(snaps)} snapshots for {n} steps')
    return {'signature': signature, 'steps': [strip_volatile(s) for s in snaps]}


def encode_tour(collected):
    """The file's shape for one tour: `steps` is an integer per step into
    `unique`, where identical projects (a run of steps that only look, or a
    step whose act changes nothing the snapshot sees) are stored once."""
    unique, index, steps = [], {}, []
    for snap in collected['steps']:
        key = canonical(snap)
        if key not in index:
            index[key] = len(unique)
            unique.append(snap)
        steps.append(index[key])
    return {'signature': collected['signature'], 'steps': steps, 'unique': unique}


def decode_tour(entry):
    """The per-step snapshots back out of a tour entry (the JS reader does
    the same: an integer indexes `unique`, an object is the project)."""
    out = []
    for e in entry['steps']:
        out.append(entry['unique'][e] if isinstance(e, int) else e)
    return out


def write_fixture(version, tours, path=FIXTURE):
    data = {'version': version, 'tours': tours}
    text = canonical(data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return len(text.encode('utf-8'))


# ── a fresh server, the way the tests start one ──────────────────────────

def start_server():
    sys.path.insert(0, SRC)
    import app as app_module
    from app import app, socketio, _build_initial_project

    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1
    app_module.server_preferences = {}
    app.config['TESTING'] = True
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    failures = []

    def serve():
        try:
            socketio.run(app, host='127.0.0.1', port=port,
                         allow_unsafe_werkzeug=True, log_output=False)
        except BaseException as e:      # the bind, above all
            failures.append(e)

    threading.Thread(target=serve, daemon=True).start()
    url = f'http://127.0.0.1:{port}'
    deadline = time.time() + 20
    while time.time() < deadline:
        if failures:
            raise SystemExit(f'the server could not start on {port}: {failures[0]!r}')
        try:
            with urllib.request.urlopen(url + '/api/project', timeout=2) as r:
                if r.status == 200:
                    return url
        except Exception:
            time.sleep(0.1)
    raise SystemExit('the server did not come up in 20 s')


def new_page(browser, url):
    context = browser.new_context(viewport=VIEWPORT)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = context.new_page()
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    page.wait_for_timeout(1500)
    return context, page


def build(url, browser, tours=TOURS, speed=DRIVE_SPEED, log=print):
    """Collect every tour in `tours` on a fresh page each, encoded for the file."""
    out = {}
    for name in tours:
        context, page = new_page(browser, url)
        try:
            log(f'{name}:')
            out[name] = encode_tour(collect_tour(page, name, speed=speed, log=log))
        finally:
            context.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--tours', nargs='+', default=list(TOURS), choices=TOURS)
    ap.add_argument('--out', default=FIXTURE)
    ap.add_argument('--speed', type=float, default=DRIVE_SPEED)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    url = start_server()
    log = (lambda s: None) if args.quiet else print
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context, page = new_page(browser, url)
            version = page.evaluate(
                "() => (/\\bv(\\d+(?:\\.\\d+)+)/.exec(document.title) || [])[1] || null")
            context.close()
            tours = build(url, browser, args.tours, args.speed, log)
        finally:
            browser.close()
    if args.tours != list(TOURS) and os.path.isfile(args.out):
        with open(args.out, encoding='utf-8') as f:
            kept = json.load(f).get('tours', {})
        kept.update(tours)
        tours = kept
    size = write_fixture(version, tours, args.out)
    for name, t in tours.items():
        print(f'{name}: {len(t["steps"])} steps, {len(t["unique"])} unique snapshots, {t["signature"]}')
    print(f'wrote {args.out} ({size:,} bytes)')


if __name__ == '__main__':
    main()
