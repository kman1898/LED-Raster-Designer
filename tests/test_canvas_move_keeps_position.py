"""Moving a layer to another canvas keeps its position.

It used to land at 0,0. The route zeroed offset_x/y and showOffsetX/Y on both
the move and duplicate branches, citing "design Section 5.7", so a screen that
sat where it belonged on one canvas jumped to the top-left corner the moment it
moved and had to be dragged back by eye. Canvases share a coordinate space, so
the same x/y means the same place and there is nothing to re-anchor to.

The panel rebuild still runs. _build_panels reads the layer's offset, so
panels follow the layer to wherever it actually is - the thing that must NOT
happen is panels staying at their old absolute coordinates while the layer
claims a new position, which is what the rebuild is there to prevent.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        c.post('/api/project/new')
        yield c


def _canvas_ids(client):
    proj = client.get('/api/project').get_json()
    return [c['id'] for c in proj.get('canvases', [])]


def _layer(client, layer_id):
    proj = client.get('/api/project').get_json()
    return next(l for l in proj['layers'] if l['id'] == layer_id)


def _make_second_canvas(client):
    ids = _canvas_ids(client)
    if len(ids) < 2:
        client.post('/api/canvas', json={'name': 'Canvas 2'})
        ids = _canvas_ids(client)
    assert len(ids) >= 2, 'need two canvases for this test'
    return ids


def _add_screen(client, **kw):
    payload = {'name': 'Mover', 'columns': 3, 'rows': 2,
               'cabinet_width': 100, 'cabinet_height': 100}
    payload.update(kw)
    r = client.post('/api/layer/add', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    proj = client.get('/api/project').get_json()
    return proj['layers'][-1]['id']


@pytest.mark.parametrize('mode', ['move', 'duplicate'])
def test_position_survives_the_canvas_change(client, mode):
    ids = _make_second_canvas(client)
    layer_id = _add_screen(client, offset_x=640, offset_y=360)

    r = client.put(f'/api/layer/{layer_id}/canvas',
                   json={'canvas_id': ids[1], 'mode': mode})
    assert r.status_code == 200, r.get_data(as_text=True)

    proj = r.get_json()
    if mode == 'move':
        moved = next(l for l in proj['layers'] if l['id'] == layer_id)
        assert moved['canvas_id'] == ids[1]
    else:
        # the clone is the one on the target canvas
        moved = next(l for l in proj['layers']
                     if l['canvas_id'] == ids[1] and l['id'] != layer_id)

    assert (moved['offset_x'], moved['offset_y']) == (640, 360), (
        f"{mode} put the layer at {moved['offset_x']},{moved['offset_y']} - it "
        'should stay where it was. Landing at 0,0 was the old behaviour and '
        'meant dragging every moved screen back into place by eye.')


def test_the_show_look_position_survives_too(client):
    """Show Look is a second position for the same layer, and it was zeroed by
    the same lines. Losing it silently rearranges the Data and Power views,
    which are drawn from Show Look."""
    ids = _make_second_canvas(client)
    layer_id = _add_screen(client, offset_x=100, offset_y=200)
    client.put(f'/api/layer/{layer_id}',
               json={'showOffsetX': 1500, 'showOffsetY': 900})

    client.put(f'/api/layer/{layer_id}/canvas',
               json={'canvas_id': ids[1], 'mode': 'move'})

    moved = _layer(client, layer_id)
    assert (moved['showOffsetX'], moved['showOffsetY']) == (1500, 900), (
        f"Show Look position became {moved['showOffsetX']},{moved['showOffsetY']}")


def test_panels_follow_the_layer_rather_than_staying_put(client):
    """The rebuild is the reason position CAN be preserved safely: panel x/y
    are canvas-absolute, so they have to be rebuilt against the layer's offset.
    If this ever regresses, the layer draws in one place and its cabinets in
    another."""
    ids = _make_second_canvas(client)
    layer_id = _add_screen(client, offset_x=500, offset_y=300)

    client.put(f'/api/layer/{layer_id}/canvas',
               json={'canvas_id': ids[1], 'mode': 'move'})

    moved = _layer(client, layer_id)
    first = min(moved['panels'], key=lambda p: (p['row'], p['col']))
    assert (first['x'], first['y']) == (500, 300), (
        f"top-left panel sits at {first['x']},{first['y']} but the layer is at "
        f"{moved['offset_x']},{moved['offset_y']} - panels and layer disagree")
