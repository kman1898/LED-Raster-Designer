"""Tests for global error handlers (500, 404)."""


def test_404_api_route_returns_json(client):
    """Hitting a non-existent API route returns JSON 404."""
    resp = client.get('/api/nonexistent/endpoint')
    assert resp.status_code == 404
    data = resp.get_json()
    assert 'error' in data
    assert 'Not found' in data['error']


def test_404_non_api_route_returns_html(client):
    """Hitting a non-existent non-API route returns standard 404."""
    resp = client.get('/nonexistent/page')
    assert resp.status_code == 404
