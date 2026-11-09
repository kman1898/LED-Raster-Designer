"""Every socket message is a snapshot of what it carries (app._emit_snapshot).

A route emits the live project, and Socket.IO walks it in Python before
encoding it; a layer save on another request thread changed a dict during
that walk and the route answered 500 ("dictionary changed size during
iteration", 1.7.0 CI, a pin release raced by the screen's save). These tests
hold the walk open and change the project under it."""
import threading

import socketio.packet as sio_packet

import app as app_module


def test_an_emit_never_hands_socketio_the_live_project():
    seen = []
    real = app_module._socketio_emit
    app_module._socketio_emit = lambda event, *args, **kw: seen.append(args[0])
    try:
        project = {'layers': [{'id': 1, 'name': 'A', 'panels': [{'x': 0}]}]}
        app_module.socketio.emit('project_updated', project)
    finally:
        app_module._socketio_emit = real
    assert seen and seen[0] == project
    assert seen[0] is not project
    assert seen[0]['layers'][0] is not project['layers'][0]


def test_a_save_landing_mid_emit_does_not_fail_the_emit(monkeypatch):
    """A save lands while Socket.IO walks the message: the walk itself
    changes the live layer the moment it reaches the layer's panels, the
    way the screen's save did on another thread. The walk goes over the
    snapshot, so the emit goes out."""
    project = {'layers': [{'id': 1, 'name': 'A', 'panels': [{'x': i} for i in range(4)]}]}
    live_layer = project['layers'][0]
    real_walk = sio_packet.Packet.data_is_binary.__func__
    landed = []

    def walk(cls, data):
        if isinstance(data, list) and data and isinstance(data[0], dict) and 'x' in data[0]:
            live_layer[f'saved{len(landed)}'] = True   # the save lands here
            landed.append(1)
        return real_walk(cls, data)

    # a screen connected, or Socket.IO has no one to build the packet for
    client = app_module.socketio.test_client(app_module.app)
    try:
        monkeypatch.setattr(sio_packet.Packet, 'data_is_binary', classmethod(walk))
        app_module.socketio.emit('project_updated', project)
    finally:
        client.disconnect()
    assert landed, 'the walk never reached the panels'


def test_a_request_refused_on_purpose_keeps_its_status():
    """A 405 (wrong method) or 415 (not JSON) answered as itself, not as a
    500 that reads as the server breaking."""
    client = app_module.app.test_client()
    r = client.get('/api/port-assignments/remap')
    assert r.status_code == 405, r.status_code
    assert 'error' in r.get_json()
    r = client.post('/api/port-assignments/remap', data='x', content_type='text/plain')
    assert r.status_code in (400, 415), r.status_code
