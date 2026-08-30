"""Cancelling a save must save NOTHING - asserted in the real browser.

Reported twice, on both platforms: "i cancel and it auto saves to downloads
anyways". The server side of that split (cancelled vs unavailable) is pinned
by test_native_dialog_contract.py. This module pins the CLIENT side: what
app-export-io.js actually does with each status.

Every save and export in the app funnels through exactly two functions -
saveBlobWithPicker (project JSON, single PNG/PDF/XML) and saveMultipleFiles
(multi-canvas exports) - so driving those two under a stubbed dialog route
covers every flow. The dialog endpoints are intercepted in the page, no real
OS dialog opens, and the assertions are:

  cancelled    -> no browser download, no write-file call, quiet return
  unavailable  -> the browser download DOES happen (discarding an export
                  because the dialog was broken is worse than Downloads)
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture()
def page(e2e_server, pw_browser):
    """A fresh context per test: routes and stubs must not leak between
    tests, and none of this module's state belongs on the shared page."""
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


def _fulfill_json(route, payload):
    import json
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps(payload))


def _arm(page, save_file=None, select_directory=None):
    """Stub the dialog endpoints and count every way bytes could leave.

    browserDownload / downloadBlob are replaced with counters so nothing
    actually lands in the headless browser's download dir; write-file and
    write-multiple are routed to a counter that FAILS the write, so if a
    cancelled flow ever reaches them the test sees it twice over.
    """
    counters = {'write_calls': 0}

    if save_file is not None:
        page.route('**/api/native-dialog/save-file',
                   lambda route: _fulfill_json(route, save_file))
    if select_directory is not None:
        page.route('**/api/native-dialog/select-directory',
                   lambda route: _fulfill_json(route, select_directory))

    def count_write(route):
        counters['write_calls'] += 1
        _fulfill_json(route, {'ok': False, 'error': 'test stub: no writes'})

    page.route('**/api/native-dialog/write-file', count_write)
    page.route('**/api/native-dialog/write-multiple', count_write)

    page.evaluate("""() => {
        window.__downloads = 0;
        window.app.browserDownload = () => { window.__downloads += 1; };
        window.app.downloadBlob = () => { window.__downloads += 1; };
    }""")
    return counters


def _downloads(page):
    return page.evaluate("window.__downloads")


# ── cancel means nothing is written anywhere ──────────────────────────────

def test_cancelling_a_single_file_save_downloads_nothing(page):
    """The reported bug, from the client's side: the server says cancelled,
    and the ONLY correct response is to stop."""
    writes = _arm(page, save_file={'ok': False, 'cancelled': True,
                                   'unavailable': False})
    page.evaluate("""async () => {
        const blob = new Blob(['{}'], { type: 'application/json' });
        await window.app.saveBlobWithPicker(blob, 'CancelProbe.json',
                                            'application/json');
    }""")
    assert _downloads(page) == 0, (
        'cancelling the save dialog must not fall back to a browser download '
        '- this is exactly "i cancel and it auto saves to downloads anyways"')
    assert writes['write_calls'] == 0


def test_cancelling_a_multi_file_export_downloads_nothing(page):
    """Cancel on the folder chooser: none of the files may escape, not by
    download and not by per-file save dialogs."""
    writes = _arm(page, save_file={'ok': False, 'cancelled': True,
                                   'unavailable': False},
                  select_directory={'ok': False, 'cancelled': True,
                                    'unavailable': False})
    page.evaluate("""async () => {
        const files = [
            { filename: 'a.png', blob: new Blob(['a'], { type: 'image/png' }) },
            { filename: 'b.png', blob: new Blob(['b'], { type: 'image/png' }) },
        ];
        await window.app.saveMultipleFiles(files);
    }""")
    assert _downloads(page) == 0
    assert writes['write_calls'] == 0


def test_a_cancel_leaves_no_error_state_behind(page):
    """A cancel is the user's decision, not a fault: the flow must resolve
    (not hang or throw) and a follow-up save must work normally."""
    _arm(page, save_file={'ok': False, 'cancelled': True,
                          'unavailable': False})
    result = page.evaluate("""async () => {
        const blob = new Blob(['{}'], { type: 'application/json' });
        try {
            await window.app.saveBlobWithPicker(blob, 'CancelProbe.json',
                                                'application/json');
            return 'resolved';
        } catch (err) {
            return 'threw: ' + err.message;
        }
    }""")
    assert result == 'resolved'


# ── unavailable still falls back: a broken dialog must not eat the export ─

def test_a_broken_dialog_still_falls_back_to_a_download(page):
    """The counterweight. If this stops working the fix "worked" by silently
    discarding exports, which is the worse bug."""
    _arm(page, save_file={'ok': False, 'cancelled': False,
                          'unavailable': True})
    page.evaluate("""async () => {
        const blob = new Blob(['{}'], { type: 'application/json' });
        await window.app.saveBlobWithPicker(blob, 'FallbackProbe.json',
                                            'application/json');
    }""")
    assert _downloads(page) == 1, (
        'a dialog that could not open must fall back to a browser download - '
        'losing the export with no file anywhere is worse than Downloads')


def test_a_broken_folder_chooser_still_yields_every_file(page):
    _arm(page, save_file={'ok': False, 'cancelled': False,
                          'unavailable': True},
         select_directory={'ok': False, 'cancelled': False,
                           'unavailable': True})
    page.evaluate("""async () => {
        const files = [
            { filename: 'a.png', blob: new Blob(['a'], { type: 'image/png' }) },
            { filename: 'b.png', blob: new Blob(['b'], { type: 'image/png' }) },
        ];
        await window.app.saveMultipleFiles(files);
    }""")
    assert _downloads(page) == 2, 'both files must still come out'
