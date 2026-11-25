"""
The IDM Locator's phone page: a tech walks the wall with a phone on the same
network and drives the live highlight, marks modules and ticks off the swap
list from it.

  GET /idm-phone                  the page (templates/idm_phone.html,
                                  static/js/idm-phone.js); it loads the
                                  renderer's geometry and nothing else of the
                                  designer
  GET /api/idm-phone/address      the addresses a phone can open it at, for
                                  the QR code on the IDM Locator tab
                                  (app-idm-phone.js)
  GET /api/idm-phone/show         whether a show is open on the computer,
                                  so the page can say plainly when none is

Everything the page changes goes through the routes and the socket events
the tab uses (PUT /api/layer/<id>, PUT /api/project/idm-field, PUT
/api/project/idm-swap for Swap mode, the `idm_highlight` event), so it is
saved with the show and reaches every
device and the wall output the same way.
"""
import ipaddress
import socket

from flask import Blueprint, jsonify, make_response, render_template, request

import app as _app
from app import log_event

idm_phone_bp = Blueprint('idm_phone', __name__)

PHONE_PATH = '/idm-phone'


def _usable(ip):
    """An IPv4 address another device on the network can reach: not
    loopback, not link-local (169.254, what a cable with no network gets),
    not unspecified."""
    try:
        a = ipaddress.IPv4Address(ip)
    except (ipaddress.AddressValueError, ValueError):
        return False
    return not (a.is_loopback or a.is_link_local or a.is_unspecified or a.is_multicast)


def _default_route_ip():
    """This machine's address on the route out, without sending anything
    (the same way launcher_settings and routes_dialog find it)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def _lan_addresses():
    """Every LAN address of this machine, the one on the route out first
    (the likeliest to be the network the phones are on), then the rest in
    the order the system lists them."""
    out = []
    first = _default_route_ip()
    if first and _usable(first):
        out.append(first)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _usable(ip) and ip not in out:
                out.append(ip)
    except (socket.gaierror, OSError):
        pass
    return out


def phone_addresses():
    """{addresses: [ip], reachable: bool, why: '' | 'local-only'}: where a
    phone can reach this server. A server the launcher bound to this
    computer alone (127.0.0.1, the launcher's default) cannot be reached
    from a phone at all; one bound to one network's address only at that
    address; one bound to every interface (or run without a launcher) at
    every LAN address."""
    bound = getattr(_app, 'BOUND_HOST', None)
    if bound and bound not in ('0.0.0.0', '::'):
        if not _usable(bound):
            return {'addresses': [], 'reachable': False, 'why': 'local-only'}
        return {'addresses': [bound], 'reachable': True, 'why': ''}
    found = _lan_addresses()
    return {'addresses': found, 'reachable': bool(found), 'why': '' if found else 'no-network'}


@idm_phone_bp.route(PHONE_PATH)
def idm_phone_page():
    log_event('idm_phone_page', {'remote': request.remote_addr or ''})
    response = make_response(render_template('idm_phone.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@idm_phone_bp.route('/api/idm-phone/show')
def idm_phone_show():
    """Is a show open on the computer: the launch's question answered (a
    show opened, a new one started, the startup one kept), or the show past
    its untouched startup state. The phone page says so plainly while it
    is not."""
    import routes_project
    project = _app.current_project if isinstance(_app.current_project, dict) else {}
    is_open = routes_project.launch_settled() or project.get('is_pristine') is not True
    return jsonify({'open': bool(is_open), 'name': project.get('name') or ''})


@idm_phone_bp.route('/api/idm-phone/address')
def idm_phone_address():
    """The phone page's address on this computer's network, for the QR
    code: the scheme and port this request came in on, every LAN address a
    phone can use (the likeliest first), and why there is none."""
    info = phone_addresses()
    try:
        port = int(request.environ.get('SERVER_PORT') or 0)
    except (TypeError, ValueError):
        port = 0
    scheme = 'https' if request.scheme == 'https' else 'http'
    default_port = 443 if scheme == 'https' else 80
    tail = '' if port in (0, default_port) else f':{port}'
    urls = [f'{scheme}://{ip}{tail}{PHONE_PATH}' for ip in info['addresses']]
    return jsonify({
        'path': PHONE_PATH, 'scheme': scheme, 'port': port,
        'addresses': info['addresses'], 'urls': urls,
        'reachable': info['reachable'], 'why': info['why'],
    })
