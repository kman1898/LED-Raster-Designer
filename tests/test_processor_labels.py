"""Where a port label on the DRAWING comes from, now that a processor can say.

Until this shipped, every port label on the canvas came from the screen it was
drawn on: portLabelTemplatePrimary / Return plus a per-port override, typed
into the Data sidebar screen by screen. The processor tree existed alongside it
and reached nothing. The goal asked for was "to not really need labeling
anymore, it will be autolabeled by default", and the rule that gets there is:

    A PORT THAT IS ASSIGNED TO A SENDING-CARD PORT TAKES THAT PORT'S NAME,
    AND NOTHING ON THE SCREEN OVERRIDES IT.

Everything below is that rule and the two things it must not break:

* A PORT THAT IS NOT ASSIGNED KEEPS THE OLD BEHAVIOUR, EXACTLY. So does every
  port of a project with no processor, and so does a port on a card nobody has
  named. Drawings have been issued off those labels; a release that blanked
  them would be wrong on paper that is already in a truck.
* AN ASSIGNED PORT IS STILL NAMEABLE. The screen's override no longer reaches
  it, so the name moves to the port itself, on the card, where a socket's name
  belongs - it survives the wall in front of it being renumbered or deleted.
* THE RETURN END IS STILL TELLABLE FROM THE PRIMARY. Both ends of a redundant
  loop are the same socket, but they print at opposite corners of the wall and
  the drawing is the only thing saying which is which. The return is the
  primary with an R after it - SR-1 out, SR-1R back - which is what P1 / R1
  said before a processor was naming anything.

The label rules themselves live in processor_catalog.py and are asserted here
through the API, never as they were sent: this codebase drops unlisted fields
silently in more than one place and a test that only checks its own request
body passes straight through that.

Run locally:
    python3 -m pytest tests/test_processor_labels.py -q
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

JS_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')


# ── helpers ───────────────────────────────────────────────────────────────

def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def only(state):
    assert len(state['resolved']) == 1, state['resolved']
    return state['resolved'][0]


def first_card(proc):
    for slot in proc['slots']:
        if slot['card']:
            return slot['card']
    raise AssertionError(f'no card in {proc["id"]}')


def set_card(client, proc_id, slot, device_id):
    resp = client.put(f'/api/processors/{proc_id}/slots/{slot}',
                      json={'deviceId': device_id})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def name_card(client, proc_id, card_id, name):
    resp = client.put(f'/api/processors/{proc_id}/cards/{card_id}',
                      json={'name': name})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def name_port(client, proc_id, card_id, number, name):
    return client.put(
        f'/api/processors/{proc_id}/cards/{card_id}/ports/{number}',
        json={'name': name})


def name_return(client, proc_id, card_id, number, name):
    return client.put(
        f'/api/processors/{proc_id}/cards/{card_id}/ports/{number}',
        json={'returnName': name})


def add_cvt(client, proc_id, card_id, device_id):
    resp = client.post(f'/api/processors/{proc_id}/cards/{card_id}/cvts',
                       json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def screens(*pairs):
    """(name, ports) in the order they are to be allocated - project layer
    order, which is what the client sends."""
    return [{'layerId': name, 'name': name, 'ports': count}
            for name, count in pairs]


def resolve(client, *pairs):
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': screens(*pairs)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def labels(resolution, name):
    """The label each of one screen's own ports carries, in its own order.
    None where the port takes none - which is the client's cue to fall back to
    the screen's template."""
    scr = next(s for s in resolution['screens'] if s['layerId'] == name)
    return [p['label'] for p in scr['ports']]


def return_labels(resolution, name):
    """The other end of the same sockets: what the return bubbles print."""
    scr = next(s for s in resolution['screens'] if s['layerId'] == name)
    return [p['returnLabel'] for p in scr['ports']]


def occupants(resolution, card_id, port):
    return resolution['occupancy'].get(card_id, {}).get(str(port), [])


def js(filename):
    with open(os.path.join(JS_DIR, filename), encoding='utf-8') as fh:
        return fh.read()


def function_body(source, signature):
    """One method out of a mixin class, from its signature to the closing brace
    at method indentation. Crude, and it only has to be good enough to prove
    that two branches are in the order this file says they are."""
    start = source.index(signature)
    end = source.index('\n    }', start)
    return source[start:end]


# ── 1. The label comes off the processor ──────────────────────────────────

def test_an_assigned_port_takes_its_label_from_the_card(client):
    """Naming a card is the whole of it: a screen assigned to that card stops
    reading P1, P2 and starts reading SR-1, SR-2 with nothing typed on the
    screen at all. This is the label reaching the drawing - the resolution the
    canvas reads is what carries it."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')

    res = resolve(client, ('Main', 4))
    assert labels(res, 'Main') == ['SR-1', 'SR-2', 'SR-3', 'SR-4']


def test_a_box_in_front_of_the_card_names_the_port_instead(client):
    """A fiber card's ports physically arrive at a CVT, so the box is what a
    tech is standing in front of and its name is what is silkscreened by the
    socket. Its numbering is the box's own, restarting at 1 per box, which is
    the number actually printed on it."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    state = add_cvt(client, pid, card_id, 'novastar-cvt10')
    cvt_id = first_card(only(state))['cvts'][0]['id']
    resp = client.put(f'/api/processors/{pid}/cvts/{cvt_id}',
                      json={'name': 'BOX-A'})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    res = resolve(client, ('Main', 3))
    assert labels(res, 'Main') == ['BOX-A-1', 'BOX-A-2', 'BOX-A-3'], (
        'the card outranked the box the ports actually come out of')


def test_an_all_in_one_labels_its_ports_off_its_own_name(client):
    """A processor with fixed outputs has no card to name. Naming the machine
    has to be enough, or the commonest device in the catalog is the one this
    feature does nothing for."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    assert client.put(f'/api/processors/{pid}',
                      json={'name': 'FOH'}).status_code == 200

    res = resolve(client, ('Main', 2))
    assert labels(res, 'Main') == ['FOH-1', 'FOH-2']


# ── 2. One port, named by hand ────────────────────────────────────────────

def test_a_name_typed_on_one_port_beats_the_generated_one(client):
    """The one port that is not like its neighbours - the spare patched across
    the room, the port the house rig already calls something else. It used to
    be handled by overriding the label on the screen, and a screen's override
    no longer reaches an assigned port, so this is the override now."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')

    resp = name_port(client, pid, card_id, 3, 'HOUSE-LEFT')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = first_card(only(resp.get_json()))
    assert card['ports'][2]['label'] == 'HOUSE-LEFT'
    assert card['ports'][2]['labelSource'] == 'manual'
    assert card['ports'][3]['label'] == 'SR-4', (
        'naming one port renamed its neighbours')

    res = resolve(client, ('Main', 4))
    assert labels(res, 'Main') == ['SR-1', 'SR-2', 'HOUSE-LEFT', 'SR-4']


def test_a_hand_named_port_beats_the_box_in_front_of_it_too(client):
    """The manual name is on the CARD's port, which is the port. A box is where
    it comes out, not a second port, so a name typed on port 3 wins whatever is
    hanging off the trunk that delivers it."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    state = add_cvt(client, pid, card_id, 'novastar-cvt10')
    cvt_id = first_card(only(state))['cvts'][0]['id']
    client.put(f'/api/processors/{pid}/cvts/{cvt_id}', json={'name': 'BOX-A'})
    assert name_port(client, pid, card_id, 2, 'SPARE').status_code == 200

    res = resolve(client, ('Main', 3))
    assert labels(res, 'Main') == ['BOX-A-1', 'SPARE', 'BOX-A-3']


def test_clearing_a_port_name_hands_it_back_to_the_template(client):
    """And leaves nothing behind in the file. A port with no name is the normal
    state of every port; a card carrying forty empty strings would be in the
    saved project of anyone who typed a name and thought better of it."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    assert name_port(client, pid, card_id, 2, 'SPARE').status_code == 200

    resp = name_port(client, pid, card_id, 2, '  ')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = first_card(only(resp.get_json()))
    assert card['ports'][1]['label'] == 'SR-2'
    assert card['ports'][1]['labelSource'] == 'card'
    assert card['portNames'] == {}

    stored = client.get('/api/project').get_json()['processors'][0]
    stored_card = stored['slots'][0]['card']
    assert 'portNames' not in stored_card, (
        f'a cleared name left something in the project: {stored_card}')


def test_a_port_name_survives_save_and_reload(client):
    """The only override an assigned port has. If it does not come back off
    disk it is not an override, it is a session-long accident."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    assert name_port(client, pid, card_id, 5, 'HOUSE-LEFT').status_code == 200

    saved = client.get('/api/project').get_json()
    assert client.post('/api/project', json=saved).status_code == 200
    assert client.put('/api/project', json=saved).status_code == 200

    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['portNames'] == {'5': 'HOUSE-LEFT'}
    assert card['ports'][4]['label'] == 'HOUSE-LEFT'


def test_a_port_name_is_refused_where_there_is_nothing_to_name(client):
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    assert name_port(client, 'nope', card_id, 1, 'X').status_code == 404
    assert name_port(client, pid, 'nope', 1, 'X').status_code == 404
    assert name_port(client, pid, card_id, 0, 'X').status_code == 400
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}/ports/1',
                      json={})
    assert resp.status_code == 400, 'a PUT with no name silently did nothing'


# ── 3. The fallback, which is the regression bar ──────────────────────────

def test_a_port_with_nowhere_to_go_takes_no_processor_label(client):
    """Seven ports onto a four-port machine. The three that did not fit carry
    no label at all, which is the client's cue to fall back to the screen's own
    template - the same template it printed before any of this existed."""
    state = add_processor(client, 'novastar-vx400')
    pid = only(state)['id']
    assert client.put(f'/api/processors/{pid}',
                      json={'name': 'FOH'}).status_code == 200

    res = resolve(client, ('Main', 7))
    assert labels(res, 'Main') == ['FOH-1', 'FOH-2', 'FOH-3', 'FOH-4',
                                   None, None, None]


def test_an_assigned_port_on_a_card_nobody_named_takes_no_label(client):
    """A processor added and nothing named is the state every processor is in
    for the first minute of its life. Ports are assigned, and no name exists
    anywhere upstream to build a label out of, so the screen's own template is
    still doing the work and the drawing does not change."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    set_card(client, pid, 0, 'novastar-card-h-20xrj45')

    res = resolve(client, ('Main', 3))
    assert labels(res, 'Main') == [None, None, None]
    assert res['configured'] is True, 'the card is there; only its name is not'


def test_a_project_with_no_processors_offers_no_labels_at_all(client):
    """The regression bar, stated as data: with no processor there is nothing
    for a label to come from, no port is assigned, and the occupancy map the
    Processors panel reads is empty rather than absent."""
    res = resolve(client, ('Main', 4))
    assert res['configured'] is False
    assert labels(res, 'Main') == [None, None, None, None]
    assert res['occupancy'] == {}
    assert 'processors' not in client.get('/api/project').get_json(), (
        'resolving an assignment stamped the key onto a project with none')


def test_the_per_screen_templates_still_round_trip(client_with_layer):
    """The fallback is not just unread, it is unchanged. Same PUT the port
    label editor makes, same fields back."""
    layer_id = client_with_layer.get('/api/project').get_json()['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'portLabelTemplatePrimary': 'SR-#',
        'portLabelTemplateReturn': 'SRB-#',
        'portLabelOverridesPrimary': {'2': 'SPARE'},
    })
    assert resp.status_code == 200
    layer = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert layer['portLabelTemplatePrimary'] == 'SR-#'
    assert layer['portLabelTemplateReturn'] == 'SRB-#'
    assert layer['portLabelOverridesPrimary'] == {'2': 'SPARE'}


# ── 4. What is on the port ────────────────────────────────────────────────

def test_a_port_row_names_the_screen_on_it_and_reads_free_when_empty(client):
    """The panel used to list "1 unnamed, 2 unnamed" and never say which screen
    was on any of them, which reads as though no screen were on the machine
    even with six of them assigned. Every claimed port names its screen and its
    port within that screen; a genuinely free one is simply absent, so the row
    can say free without having to work out what free looks like."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']

    res = resolve(client, ('Upstage', 2), ('Downstage', 3))
    assert [o['name'] for o in occupants(res, card_id, 1)] == ['Upstage']
    assert occupants(res, card_id, 1)[0]['number'] == 1
    assert occupants(res, card_id, 2)[0]['number'] == 2
    # Six ports take 1-6 in screen order, so Downstage starts at 3 and its own
    # port 1 is the card's port 3. Both numbers have to be on the row: one is
    # what is on the drawing, the other is what is on the machine.
    assert occupants(res, card_id, 3)[0]['name'] == 'Downstage'
    assert occupants(res, card_id, 3)[0]['number'] == 1
    assert occupants(res, card_id, 5)[0]['number'] == 3
    assert occupants(res, card_id, 6) == [], 'port 6 is free and did not say so'
    assert occupants(res, card_id, 20) == []


def test_a_contested_port_names_every_screen_claiming_it(client):
    """Two pins on one port both stay - this module reports a clash and refuses
    to fix it. A row that named one of the two would hide half of exactly the
    thing that needs looking at."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']

    for layer_id in ('Upstage', 'Downstage'):
        resp = client.post('/api/port-assignments/pin', json={
            'layerId': layer_id, 'index': 0, 'cardId': card_id, 'port': 4,
            'screens': screens(('Upstage', 2), ('Downstage', 2)),
        })
        assert resp.status_code == 200, resp.get_data(as_text=True)

    res = resolve(client, ('Upstage', 2), ('Downstage', 2))
    here = occupants(res, card_id, 4)
    assert [o['name'] for o in here] == ['Upstage', 'Downstage'], here
    assert all(o['overlap'] for o in here)
    assert all(o['source'] == 'pin' for o in here)


def test_occupancy_follows_a_pin_rather_than_the_screen_order(client):
    """A pinned port is somebody's decision and the panel has to show where it
    actually is, not where auto would have put it."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']

    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 0, 'cardId': card_id, 'port': 9,
        'screens': screens(('Main', 2)),
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    res = resolve(client, ('Main', 2))
    assert occupants(res, card_id, 9)[0]['name'] == 'Main'
    assert occupants(res, card_id, 9)[0]['number'] == 1
    assert occupants(res, card_id, 9)[0]['source'] == 'pin'
    # The screen's other port is still auto and still packs from the front, so
    # this screen's run is split across 1 and 9 and both rows say so. Showing
    # the pinned port back at 1 as well - where auto would have put it - is the
    # failure this asserts against.
    assert occupants(res, card_id, 1)[0]['number'] == 2
    assert occupants(res, card_id, 1)[0]['source'] == 'auto'
    assert occupants(res, card_id, 2) == []


# ── 5. One label path, and a cheap one ────────────────────────────────────

def test_the_processor_is_consulted_before_any_per_layer_override():
    """The order inside getPortLabelText IS the rule. Read the other way round
    a stale override typed on a screen months ago would quietly outrank the
    machine now driving it, and the port would print one thing on the wall and
    another on the card."""
    body = function_body(js('app-power.js'),
                         'getPortLabelText(layer, portNum, type) {')
    processor = body.index('getProcessorPortLabel')
    returned = body.index('return assigned;')
    override = body.index('portLabelOverridesPrimary')
    template = body.index('portLabelTemplatePrimary')
    assert processor < returned < template, (
        'getPortLabelText reads the layer template before the processor')
    assert returned < override, (
        'a per-layer override is read before the processor has answered')
    # And the return end asks its own index before deriving <primary>R, so a
    # name typed on the return end is not flattened back into the suffix rule.
    assert body.index('getProcessorPortReturnLabel') \
        < body.index('${assigned}R'), (
        'the return end derives before consulting its typed name')


def test_the_layer_template_is_still_the_fallback():
    """The half of getPortLabelText that must never be deleted. Every project
    with no processor, every port with no card and every card with no name
    arrives here, including drawings already issued."""
    body = function_body(js('app-power.js'),
                         'getPortLabelText(layer, portNum, type) {')
    assert "layer.portLabelTemplateReturn || 'R#'" in body
    assert "layer.portLabelTemplatePrimary || 'P#'" in body
    assert 'if (overrides && overrides[portNum]) return overrides[portNum];' in body
    assert "return template.replace('#', portNum);" in body


def test_the_label_lookup_never_resolves_anything_itself():
    """It runs for every port of every screen on every frame. A fetch, or a
    walk of the resolution, would put the network or an O(screens x ports)
    scan inside the render loop."""
    for signature in ('getPortLabelText(layer, portNum, type) {',
                      'getProcessorPortLabel(layer, portNum) {',
                      'getProcessorPortReturnLabel(layer, portNum) {'):
        body = function_body(js('app-power.js'), signature)
        for banned in ('fetch(', 'refreshPortAssignment', 'getLayerPortsRequired',
                       '.forEach(', '.filter(', '.find('):
            assert banned not in body, (
                f'{signature.split("(")[0]} does {banned} on every frame')


def test_the_lookup_is_built_once_when_the_assignment_changes():
    """The map is prepared where the resolution lands, not where it is read."""
    source = js('app-port-assignment.js')
    assert '_indexAssignmentLabels()' in source
    assert '_processorPortLabels = map;' in source
    # The return ends ride the same pass over the same resolution - a second
    # walk, or a second request, would be a second chance to disagree.
    assert '_processorPortReturnLabels = returnMap;' in source
    assert '_applyAssignmentResolution()' in source
    # Every path that stores a resolution has to go through the one that
    # rebuilds the map, or the canvas draws last week's labels.
    assert source.count('this._assignment = data.resolution') == 1
    body = function_body(source,
                         '_assignmentRequest(url, method, body, onRefused) {')
    assert 'this._applyAssignmentResolution();' in body


def test_a_processor_edit_re_resolves_so_the_drawing_follows():
    """Naming a card has to reach the canvas. The assignment is what carries
    the label, so a processor edit that did not re-resolve would rename a
    sidebar and nothing else - which is the whole bug this replaces."""
    body = function_body(js('app-processors.js'), '_applyProcessorState(data) {')
    assert 'this.refreshPortAssignment();' in body


def test_the_port_row_is_an_input_keyed_for_the_focus_guard():
    """The panel is rebuilt wholesale on every change, so a field with no
    data-lrd-field key is destroyed under the user's fingers - the same bug the
    port label editor had, fixed by the same _preserveEditorFocus."""
    source = js('app-processors.js')
    assert 'processor-port-name-${card.id}-${port.number}' in source
    assert '/ports/${port.number}' in source
    assert "who.textContent = 'free';" in source


# ── 6. The return end of the same socket ──────────────────────────────────
#
# A redundant loop leaves a socket and comes back to it, so both ends carry the
# same port's name - but they print at opposite corners of the wall and the
# drawing is the only thing that says which end is which. Two labels reading
# SR-1 make a backup run impossible to trace, which is the one job the return
# label has.

NODE = shutil.which('node')


def run_labels(assigned, layer, ports, returns=None):
    """The real getPortLabelText, lifted out of the file and run.

    There is no second implementation of the rule to assert against - the point
    of that method is that there is exactly one - and reading the source only
    proves the branch is there, not what it prints. So the three methods are
    taken verbatim, hung on a bare object with the same two fields they read,
    and asked. Anything that drifts inside them fails here.

    `returns` is the return-end index, shaped exactly like `assigned`. Left
    off, it is the empty map every project without a typed return name has.
    """
    source = js('app-power.js')
    methods = '\n'.join(
        function_body(source, signature) + '\n    }'
        for signature in ('getProcessorPortLabel(layer, portNum) {',
                          'getProcessorPortReturnLabel(layer, portNum) {',
                          'getPortLabelText(layer, portNum, type) {'))
    script = (
        'class Probe {\n' + methods + '\n}\n'
        'const probe = new Probe();\n'
        f'probe._processorPortLabels = {json.dumps(assigned)};\n'
        f'probe._processorPortReturnLabels = {json.dumps(returns or {})};\n'
        f'const layer = {json.dumps(layer)};\n'
        f'const out = {json.dumps(ports)}.map(n => ['
        "probe.getPortLabelText(layer, n, 'primary'), "
        "probe.getPortLabelText(layer, n, 'return')]);\n"
        'console.log(JSON.stringify(out));\n')
    done = subprocess.run([NODE, '-e', script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_return_label_is_derived_inside_the_assigned_branch():
    """Source-level, so it runs everywhere: the R belongs to the processor's
    label and must not reach a port the processor never named - that port's
    return is the layer's own R# template and always has been."""
    body = function_body(js('app-power.js'),
                         'getPortLabelText(layer, portNum, type) {')
    assert body.index('${assigned}R') \
        < body.index("layer.portLabelTemplateReturn || 'R#'"), (
        'the return suffix escaped the assigned branch')


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_an_assigned_ports_return_label_is_not_its_primary():
    """The bug this fixes: both ends printed SR-1, so a backup run could not be
    traced on the drawing that was meant to trace it."""
    out = run_labels({'7': {'1': 'SR-1', '2': 'HOUSE-LEFT'}}, {'id': 7}, [1, 2])
    assert out == [['SR-1', 'SR-1R'], ['HOUSE-LEFT', 'HOUSE-LEFTR']]
    for primary, backup in out:
        assert primary != backup


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_an_unassigned_port_still_takes_the_layers_own_return_template():
    """One screen, one port on the processor and one not. The port with no
    socket behind it prints exactly what it printed before any of this existed,
    which is the regression bar stated one port at a time."""
    out = run_labels({'7': {'1': 'SR-1'}}, {'id': 7}, [1, 3])
    assert out == [['SR-1', 'SR-1R'], ['P3', 'R3']]


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_a_project_with_no_processor_prints_p_and_r_exactly_as_before():
    out = run_labels({}, {'id': 7}, [1, 2])
    assert out == [['P1', 'R1'], ['P2', 'R2']]


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_templates_and_overrides_still_reach_a_port_with_no_socket():
    """Drawings have been issued off these. The processor naming its own ports
    added a branch in front of them and took nothing away."""
    out = run_labels({}, {
        'id': 7,
        'portLabelTemplatePrimary': 'SR-#',
        'portLabelTemplateReturn': 'SRB-#',
        'portLabelOverridesReturn': {'2': 'SPARE'},
    }, [1, 2])
    assert out == [['SR-1', 'SRB-1'], ['SR-2', 'SPARE']]


@pytest.mark.parametrize('number,stored', [(1, 'SR-A'), ('2', 'SR-B')])
def test_port_names_are_read_whichever_way_the_key_arrives(number, stored):
    """Keys come back as strings from a JSON round-trip and as ints from any
    Python that set one. A port whose name only worked before the file was
    saved would be worse than no override at all."""
    card = catalog.new_card('novastar-card-h-20xrj45', 1, name='SR')
    card['portNames'] = {number: stored}
    assert catalog.port_name(card, int(number)) == stored
    resolved = catalog.resolve_card(card, {'id': 'p1', 'name': ''})
    assert resolved['ports'][int(number) - 1]['label'] == stored


# ── 7. Naming the return end itself ───────────────────────────────────────
#
# The derived <primary>R is right until the house's backup loom is labelled
# off its own series - BU-1 back for SR-1 out - and then it is exactly wrong.
# So the return end is nameable the way the primary is: typed on the port, on
# the card, in the Processors panel. The ladder for an assigned port's return
# is: the typed return name, else <primary>R, and the layer's own R# template
# only ever reaches a port the processor is not naming - unchanged from
# before this existed.

def test_a_typed_return_name_reaches_the_resolution_the_canvas_reads(client):
    """BU-1 back for SR-1 out. The primary is untouched, the neighbours keep
    deriving, and it is the RESOLUTION that carries all of it - which is what
    the canvas indexes, so this is the string the drawing prints."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    assert name_return(client, pid, card_id, 1, 'BU-1').status_code == 200

    res = resolve(client, ('Main', 3))
    assert labels(res, 'Main') == ['SR-1', 'SR-2', 'SR-3']
    assert return_labels(res, 'Main') == ['BU-1', 'SR-2R', 'SR-3R']


def test_an_untyped_return_end_is_still_the_primary_with_an_r(client):
    """Today's default, unchanged: nothing typed means SR-1 out, SR-1R back -
    including when the primary itself was named by hand."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    assert name_port(client, pid, card_id, 2, 'HOUSE-LEFT').status_code == 200

    res = resolve(client, ('Main', 2))
    assert return_labels(res, 'Main') == ['SR-1R', 'HOUSE-LEFTR']


def test_a_port_with_no_primary_label_offers_no_derived_return(client):
    """Seven ports onto a four-port machine: the three with no socket behind
    them carry no return label either, so the layer's own R# template is still
    the thing doing the work there - the regression bar, return-end edition."""
    state = add_processor(client, 'novastar-vx400')
    pid = only(state)['id']
    assert client.put(f'/api/processors/{pid}',
                      json={'name': 'FOH'}).status_code == 200

    res = resolve(client, ('Main', 7))
    assert return_labels(res, 'Main') == ['FOH-1R', 'FOH-2R', 'FOH-3R',
                                          'FOH-4R', None, None, None]


def test_a_return_name_round_trips_and_survives_save_and_reload(client):
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    resp = name_return(client, pid, card_id, 5, 'BU-5')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = first_card(only(resp.get_json()))
    assert card['returnPortNames'] == {'5': 'BU-5'}
    assert card['ports'][4]['returnLabel'] == 'BU-5'
    assert card['ports'][4]['returnLabelSource'] == 'manual'
    assert card['ports'][4]['label'] == 'SR-5', (
        'naming the return end renamed the primary')

    saved = client.get('/api/project').get_json()
    assert client.post('/api/project', json=saved).status_code == 200
    assert client.put('/api/project', json=saved).status_code == 200

    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['returnPortNames'] == {'5': 'BU-5'}
    assert card['ports'][4]['returnLabel'] == 'BU-5'


def test_clearing_a_return_name_leaves_nothing_behind(client):
    """Same rule as the primary: blank is the absence of a name, the derived
    label takes back over, and the saved file carries no empty map."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    assert name_return(client, pid, card_id, 2, 'BU-2').status_code == 200

    resp = name_return(client, pid, card_id, 2, '  ')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = first_card(only(resp.get_json()))
    assert card['ports'][1]['returnLabel'] == 'SR-2R'
    assert card['returnPortNames'] == {}

    stored = client.get('/api/project').get_json()['processors'][0]
    stored_card = stored['slots'][0]['card']
    assert 'returnPortNames' not in stored_card, (
        f'a cleared return name left something in the project: {stored_card}')


def test_the_ports_put_takes_either_end_and_refuses_neither(client):
    """One PUT, two fields. Either alone is a valid edit; both at once is one
    edit; neither is a request that would silently do nothing, so it is
    refused the way the bare PUT always was."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')

    url = f'/api/processors/{pid}/cards/{card_id}/ports/1'
    assert client.put(url, json={}).status_code == 400
    resp = client.put(url, json={'name': 'HL', 'returnName': 'HL-B'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    port = first_card(only(resp.get_json()))['ports'][0]
    assert (port['label'], port['returnLabel']) == ('HL', 'HL-B')
    # Clearing the primary alone leaves the typed return standing: they are
    # two names for two ends, not one name and a suffix.
    resp = name_port(client, pid, card_id, 1, '')
    port = first_card(only(resp.get_json()))['ports'][0]
    assert (port['label'], port['returnLabel']) == ('SR-1', 'HL-B')


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_a_typed_return_name_wins_on_the_canvas_index():
    """The client's half of the ladder, run for real: the return index answers
    before anything derives, so BU-1 prints where SR-1R used to."""
    out = run_labels({'7': {'1': 'SR-1', '2': 'SR-2'}}, {'id': 7}, [1, 2],
                     returns={'7': {'1': 'BU-1'}})
    assert out == [['SR-1', 'BU-1'], ['SR-2', 'SR-2R']]


@pytest.mark.skipif(NODE is None, reason='node is not on PATH')
def test_an_empty_return_index_still_derives_from_the_primary():
    """The fallback the derived branch has always been: an index built before
    return names existed, or a project with none typed, prints exactly what it
    printed before."""
    out = run_labels({'7': {'1': 'SR-1'}}, {'id': 7}, [1, 3], returns={})
    assert out == [['SR-1', 'SR-1R'], ['P3', 'R3']]


def test_the_label_editor_names_the_actual_return_label():
    """The ownedNote used to spell the return as ${fromProcessor}R by hand - a
    second statement of the derivation, and the one place that would keep
    saying SR-1R after someone typed BU-1. It asks getPortLabelText now, so it
    can never disagree with the canvas about what the return end says."""
    source = js('app-power.js')
    assert '${fromProcessor}R' not in source, (
        'the ownedNote still derives the return label by hand')
    note = source.index('and its return ')
    asks = source.index(
        "getPortLabelText(this.currentLayer, portNum, 'return')", note)
    assert asks - note < 200, (
        'the ownedNote does not read the return label from getPortLabelText')


# ── 7. The backup template - naming all the returns at once ───────────────
#
# "We need a template spot for naming all backups the same way we do for
# primary." The card and the box carry a return-side template beside the
# primary one, and the return ladder reads, top rung first:
#
#   1. a name typed on ONE port's return end;
#   2. the return template on the device naming the port;
#   3. the primary with an R after it - the default, unchanged;
#   4. nothing, leaving the screen's own R# template in charge.
#
# All of it resolves in resolve_card and rides returnLabels through the
# assignment, so every surface - the panel placeholder, the drawing, the
# exports - reads one answer.

def set_return_template(client, proc_id, card_id, template):
    resp = client.put(f'/api/processors/{proc_id}/cards/{card_id}',
                      json={'returnLabelTemplate': template})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_return_template_names_every_backup_at_once(client):
    """One field, every return end: BU-1 to BU-20 off a single edit, exactly
    the way the primary template names the outbound side."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')

    state = set_return_template(client, pid, card_id, 'BU-#')
    card = first_card(only(state))
    assert card['returnLabelTemplate'] == 'BU-#'
    assert [p['returnLabel'] for p in card['ports'][:3]] == \
        ['BU-1', 'BU-2', 'BU-3']
    assert card['ports'][-1]['returnLabel'] == 'BU-20'
    assert all(p['returnLabelSource'] == 'template' for p in card['ports'])
    # The primary side is untouched: two templates, two ends.
    assert [p['label'] for p in card['ports'][:2]] == ['SR-1', 'SR-2']


def test_the_template_takes_the_owners_name_too(client):
    """{name} in the return template is the same name the primary borrows, so
    'SRB' typed once labels the whole backup loom SR-1R style off its own
    series: card SR, template {name}B-# -> SRB-1."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    state = set_return_template(client, pid, card_id, '{name}B-#')
    card = first_card(only(state))
    assert [p['returnLabel'] for p in card['ports'][:2]] == ['SRB-1', 'SRB-2']


def test_a_typed_return_name_still_beats_the_template(client):
    """Rung 1 over rung 2: the one return end the house already calls
    something else keeps its name while the template does the other 19."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    set_return_template(client, pid, card_id, 'BU-#')
    resp = name_return(client, pid, card_id, 2, 'HOUSE-RTN')
    card = first_card(only(resp.get_json()))
    assert [p['returnLabel'] for p in card['ports'][:3]] == \
        ['BU-1', 'HOUSE-RTN', 'BU-3']
    assert card['ports'][1]['returnLabelSource'] == 'manual'
    assert card['ports'][0]['returnLabelSource'] == 'template'


def test_clearing_the_template_hands_the_returns_back_to_primary_r(client):
    """Rung 3 is the default and stays the default: blank the template and
    every untyped return end reads <primary>R again - and the cleared key
    leaves nothing behind in the saved file."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    set_return_template(client, pid, card_id, 'BU-#')

    state = set_return_template(client, pid, card_id, '')
    card = first_card(only(state))
    assert [p['returnLabel'] for p in card['ports'][:2]] == ['SR-1R', 'SR-2R']
    assert card['returnLabelTemplate'] == ''

    stored = client.get('/api/project').get_json()['processors'][0]
    stored_card = stored['slots'][0]['card']
    assert 'returnLabelTemplate' not in stored_card, (
        f'a cleared template left something in the project: {stored_card}')


def test_the_box_in_front_carries_its_own_return_template(client):
    """The template lives at the same level the primary naming lives: a named
    box owns its ports' labels, so its return template names their backups -
    and the card's template does not reach past it, exactly as the card's
    primary template does not."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    set_return_template(client, pid, card_id, 'CARD-#')
    state = add_cvt(client, pid, card_id, 'novastar-cvt10')
    cvt_id = first_card(only(state))['cvts'][0]['id']
    resp = client.put(f'/api/processors/{pid}/cvts/{cvt_id}',
                      json={'name': 'BOX-A', 'returnLabelTemplate': 'XB-#'})
    card = first_card(only(resp.get_json()))
    behind = [p for p in card['ports'] if p['cvtId'] == cvt_id]
    assert [p['returnLabel'] for p in behind[:2]] == ['XB-1', 'XB-2']
    # Ports the box does not reach still belong to the card and its template.
    direct = [p for p in card['ports'] if p['cvtId'] is None]
    assert direct[0]['returnLabel'] == 'CARD-9'


def test_an_all_in_ones_name_reaches_the_return_template(client):
    """A processor lends its name to the card's templates - return side
    included - which is what makes naming an all-in-one enough to label both
    ends of every run."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}', json={'name': 'FOH'})
    state = set_return_template(client, pid, card_id, '{name}R-#')
    card = first_card(only(state))
    assert [p['returnLabel'] for p in card['ports'][:2]] == ['FOHR-1', 'FOHR-2']


def test_a_template_on_an_unnamed_tree_labels_nothing(client):
    """Rung 4 unchanged: with nothing named upstream there is no owner to hang
    a label on, so the template sits inert and the screen's own R# template is
    still doing the work - the fallback every issued drawing depends on."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    state = set_return_template(client, pid, card_id, 'BU-#')
    card = first_card(only(state))
    assert all(p['returnLabel'] is None for p in card['ports'])


def test_the_template_reaches_the_resolution_the_canvas_reads(client):
    """returnLabels ride the assignment from the same resolve_card pass, so
    the drawing's return bubbles print the template's answer - one authority,
    every surface."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    set_return_template(client, pid, card_id, 'BU-#')
    name_return(client, pid, card_id, 2, 'HOUSE-RTN')

    res = resolve(client, ('Main', 3))
    assert labels(res, 'Main') == ['SR-1', 'SR-2', 'SR-3']
    assert return_labels(res, 'Main') == ['BU-1', 'HOUSE-RTN', 'BU-3']


def test_the_template_survives_save_and_reload(client):
    """A template that does not come back off disk is a session-long
    accident, same bar as the per-port names."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')
    set_return_template(client, pid, card_id, 'BU-#')

    saved = client.get('/api/project').get_json()
    assert client.post('/api/project', json=saved).status_code == 200
    assert client.put('/api/project', json=saved).status_code == 200

    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['returnLabelTemplate'] == 'BU-#'
    assert card['ports'][0]['returnLabel'] == 'BU-1'


def test_a_template_edit_rides_the_project_snapshot(client):
    """Undo replays whole-project snapshots through PUT /api/project, so the
    round trip the history makes is: before-blob restores SR-1R, after-blob
    restores BU-1. If either direction dropped the field, Ctrl+Z would strand
    the labels."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_card(client, pid, card_id, 'SR')

    before = client.get('/api/project').get_json()
    set_return_template(client, pid, card_id, 'BU-#')
    after = client.get('/api/project').get_json()

    assert client.put('/api/project', json=before).status_code == 200
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['ports'][0]['returnLabel'] == 'SR-1R', 'undo kept the template'

    assert client.put('/api/project', json=after).status_code == 200
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['ports'][0]['returnLabel'] == 'BU-1', 'redo lost the template'


def test_the_template_fields_are_keyed_and_named_for_history():
    """The panel's half of the contract: both template fields carry stable
    focus keys (the panel is rebuilt under the user's fingers) and both edits
    enter history under their own names, through the same post-mutation
    snapshot every processor edit takes."""
    source = js('app-processors.js')
    assert 'processor-card-return-template-${card.id}' in source
    assert 'processor-cvt-return-template-${cvt.id}' in source
    assert "'Edit Card Return Label Template'" in source
    assert "'Edit Breakout Box Return Label Template'" in source
    # The placeholder states the rung below: primary template plus R.
    assert "${card.portLabelTemplate || '{name}-#'}R" in source
