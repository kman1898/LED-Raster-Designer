"""Every line a page writes to the app log names its browser plainly.

Owner, 2026-11-10: the logs should say what browser is used. A Mac report
read "Version/27.2 Safari/605.1.15" and left open whether the page was
Safari or the app's own window.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

import routes_logs  # noqa: E402
from routes_logs import browser_name  # noqa: E402

SAFARI_MAC = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
              '(KHTML, like Gecko) Version/27.2 Safari/605.1.15')


@pytest.mark.parametrize('ua, want', [
    (SAFARI_MAC, 'Safari 27.2'),
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
     'Chrome/131.0.0.0 Safari/537.36', 'Chrome 131'),
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
     'Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.70', 'Edge 131'),
    # an automated Chrome (CI's test browser) says HeadlessChrome
    ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
     'HeadlessChrome/158.0.8127.18 Safari/537.36', 'Chrome 158'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0',
     'Firefox 133.0'),
    ('Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
     'CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1', 'Chrome 131'),
    ('Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
     'Version/18.1 Mobile/15E148 Safari/604.1', 'Safari 18.1'),
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
     'Chrome/124.0.0.0 Safari/537.36 OPR/110.0.0.0', 'Opera 110'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)',
     'App window (WebKit)'),
    ('', 'Unknown browser'),
    (None, 'Unknown browser'),
])
def test_the_browser_is_named_plainly(ua, want):
    assert browser_name(ua) == want


def test_each_page_log_line_carries_its_browser(client, monkeypatch):
    seen = []
    monkeypatch.setattr(routes_logs, 'log_event', lambda a, d, **k: seen.append((a, d, k)))
    r = client.post('/api/log', data=json.dumps({'action': 'client_ready', 'details': {'ua': SAFARI_MAC}}),
                    content_type='application/json', headers={'User-Agent': SAFARI_MAC})
    assert r.status_code == 200
    (action, details, kw), = seen
    assert action == 'client_ready' and kw.get('source') == 'client'
    assert details['browser'] == 'Safari 27.2'
    assert details['ua'] == SAFARI_MAC


def test_a_page_that_names_its_own_browser_keeps_it(client, monkeypatch):
    seen = []
    monkeypatch.setattr(routes_logs, 'log_event', lambda a, d, **k: seen.append(d))
    client.post('/api/log', data=json.dumps({'action': 'x', 'details': {'browser': 'App output window'}}),
                content_type='application/json', headers={'User-Agent': SAFARI_MAC})
    assert seen[0]['browser'] == 'App output window'
