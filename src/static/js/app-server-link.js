// WHEN THE APP IS NOT RUNNING (owner, 2026-11-10).
//
// "when the app is closed the web interface is still usable. it doesnt
// die. that is not proper functionality". Once the app has really stopped,
// every open page, the host's and any tablet's, dims with "LED Raster
// Designer isn't running. Start it to keep working." and takes no input
// behind it: no clicks, no keys, and no saves held back to send later.
// When the app is running again the page reloads by itself and joins the
// show as the server holds it, the way any page joining the live show does
// (app-start-page.js _claimLaunchPage, _takeReloadPlace). The page's own
// copy is never written over the server's: from the moment it finds the
// app gone, every write it would send is refused before it leaves
// (app-core.js SERVER_LINK).
//
// Gone means the socket dropped (or a request could not reach the server)
// and, GRACE_MS later, the server still does not answer. A blip the
// socket recovers from inside the grace shows nothing. The app's own Quit
// tells every page first ('app_quitting', launcher_window _announce_quit),
// and those pages dim at once. A write that was on its way, or failed on
// its way, when the app went makes the overlay say so.
//
// Not the guide lock: a guide running in another window holds the show
// with a toast and its own refusals (app-core.js _refuseWhileGuideElsewhere);
// this is the app itself being gone.
import { LEDRasterApp, SERVER_LINK, LIVE_WRITES } from './app-core.js';
import { sendClientLog } from './helpers.js';

const GRACE_MS = 3000;
const PROBE_TIMEOUT_MS = 1500;
// Between tries while the app is gone: quick at first, then every 5 s.
const RETRY_MS = [1000, 1500, 2000, 3000, 5000];
// After a Quit, a server still answering with the same run for this long
// did not quit after all: the page follows it again.
const QUIT_SETTLE_MS = 15000;

export const SERVER_GONE_TEXT = "LED Raster Designer isn't running. Start it to keep working.";
const UPDATING_TEXT = 'LED Raster Designer is updating. This page comes back by itself when it opens again.';
const LOST_TEXT = 'Your last changes may not have been saved.';
const WAIT_TEXT = 'This page reconnects by itself when the app is running again.';

// ── Nothing the person does reaches the page behind the overlay ──────────
//
// Registered at import, on window in the capture phase, ahead of every
// handler the app adds later, so a key or a click stops here.
const BLOCKED_EVENTS = ['keydown', 'keyup', 'keypress', 'beforeinput', 'input', 'paste', 'cut',
    'mousedown', 'mouseup', 'click', 'dblclick', 'auxclick', 'contextmenu',
    'pointerdown', 'pointerup', 'touchstart', 'touchend', 'touchmove', 'wheel',
    'dragstart', 'dragover', 'drop', 'submit'];
let blocking = false;

function swallow(e) {
    if (!blocking) return;
    e.stopImmediatePropagation();
    if (e.cancelable) e.preventDefault();
}

if (typeof window !== 'undefined') {
    BLOCKED_EVENTS.forEach((type) => {
        window.addEventListener(type, swallow, { capture: true, passive: false });
    });
}

// A beacon is a write too (the unsaved answer a closing page sends): only
// the page's log goes out while the app is gone.
(function gateBeacons() {
    if (typeof navigator === 'undefined' || typeof navigator.sendBeacon !== 'function'
            || navigator.sendBeacon.__lrdGated) return;
    const native = navigator.sendBeacon.bind(navigator);
    const gated = function (url, data) {
        if (SERVER_LINK.gone) {
            let path = null;
            try { path = new URL(url, window.location.href).pathname; } catch (_) { path = null; }
            if (path !== '/api/log') return false;
        }
        return native(url, data);
    };
    gated.__lrdGated = true;
    try { navigator.sendBeacon = gated; } catch (_) { /* left as it was */ }
})();

class _ServerLink {
    // connectWebSocket: watch the socket and the requests for the app
    // going away.
    _wireServerLink() {
        if (this._serverLinkWired) return;
        this._serverLinkWired = true;
        SERVER_LINK.onTrouble = () => this._linkSuspect('request');
        const s = this.socket;
        if (!s) return;
        s.on('disconnect', (reason) => {
            // this page's own disconnect (_linkDown) says nothing new
            if (reason === 'io client disconnect') return;
            this._linkSuspect(`socket:${reason}`);
        });
        s.on('connect', () => this._linkConnected());
        s.on('app_quitting', () => this._linkQuitting('server'));
    }

    // Is the overlay up?
    serverGone() {
        return !!SERVER_LINK.gone;
    }

    // Something looked wrong: check again once the grace has passed.
    _linkSuspect(why) {
        if (SERVER_LINK.gone || this._linkTimer || this._linkProbing) return;
        sendClientLog('server_link_suspect', { why });
        this._linkTimer = setTimeout(() => {
            this._linkTimer = null;
            this._linkCheck();
        }, GRACE_MS);
    }

    async _linkCheck() {
        if (SERVER_LINK.gone) return;
        const session = await this._linkProbe();
        if (SERVER_LINK.gone) return;
        if (!session) {
            this._linkDown('unreachable');
            return;
        }
        // The app went and came back inside the grace: it is a new run,
        // so this page follows it.
        if (this._serverSessionId && session !== this._serverSessionId) {
            this._linkFollow('new_session');
            return;
        }
        // The server answers but the socket is still away: keep watching.
        // A socket the server let go (a restart on a new interface) does
        // not retry by itself.
        if (this.socket && !this.socket.connected) {
            if (!this.socket.active) {
                try { this.socket.connect(); } catch (_) { /* tried again next check */ }
            }
            this._linkSuspect('still_disconnected');
        }
    }

    // The socket is back (a blip, or socket.io's own retry): the same run
    // carries on; a new one is followed.
    _linkConnected() {
        if (SERVER_LINK.gone) return;
        if ((this._socketConnects || 0) <= 1) return;
        this._linkProbe().then((session) => {
            if (SERVER_LINK.gone || !session) return;
            if (this._serverSessionId && session !== this._serverSessionId) this._linkFollow('new_session');
        });
    }

    // The server's run id, or null when it does not answer.
    async _linkProbe() {
        this._linkProbing = true;
        const ctl = typeof AbortController === 'function' ? new AbortController() : null;
        const timer = ctl ? setTimeout(() => ctl.abort(), PROBE_TIMEOUT_MS) : null;
        try {
            const res = await fetch('/api/server-session', { cache: 'no-store', signal: ctl ? ctl.signal : undefined });
            if (!res.ok) return null;
            const data = await res.json();
            return data && data.session_id ? String(data.session_id) : null;
        } catch (_) {
            return null;
        } finally {
            if (timer) clearTimeout(timer);
            this._linkProbing = false;
        }
    }

    // The app is quitting: this page's own File > Quit, or the server
    // telling every page (launcher_window _announce_quit).
    _linkQuitting(source) {
        if (SERVER_LINK.gone) return;
        this._linkQuit = { session: this._serverSessionId || null, at: Date.now() };
        this._linkDown(`quit:${source}`);
    }

    // The app is gone: refuse every write from here on, stop the socket's
    // own retries (their first connect would hand the page a show to merge
    // into its stale copy), dim the page and wait for the app.
    _linkDown(why) {
        if (this._linkTimer) { clearTimeout(this._linkTimer); this._linkTimer = null; }
        SERVER_LINK.gone = true;
        if (LIVE_WRITES.out > 0) SERVER_LINK.lost = true;
        try {
            if (this.socket) {
                if (this.socket.io && typeof this.socket.io.reconnection === 'function') this.socket.io.reconnection(false);
                this.socket.sendBuffer = [];
                this.socket.disconnect();
            }
        } catch (_) { /* gone either way */ }
        const status = document.getElementById('status-message');
        if (status) status.textContent = 'Not running';
        this._linkShowOverlay();
        sendClientLog('server_link_down', { why, lost: SERVER_LINK.lost });
        this._linkSawDown = false;
        this._linkWait(0);
    }

    _linkWait(attempt) {
        const delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
        this._linkWaitTimer = setTimeout(async () => {
            const session = await this._linkProbe();
            if (!session) {
                this._linkSawDown = true;
                this._linkWait(attempt + 1);
                return;
            }
            // Just quit and still answering: the process has not gone yet.
            const q = this._linkQuit;
            if (q && !this._linkSawDown && session === q.session && Date.now() - q.at < QUIT_SETTLE_MS) {
                this._linkWait(attempt + 1);
                return;
            }
            this._linkFollow('back');
        }, delay);
    }

    // The app is running: load the show as it now stands. The page reloads
    // and joins like any other page; writes stay refused until it goes, so
    // the reload's own goodbye (the unsaved answer, a pending step) cannot
    // land on the app that just started.
    _linkFollow(why) {
        SERVER_LINK.gone = true;
        if (!blocking) this._linkShowOverlay();
        sendClientLog('server_link_back', { why });
        try { window.location.reload(); } catch (_) { /* nothing else to do */ }
    }

    _linkShowOverlay() {
        blocking = true;
        let el = document.getElementById('server-gone-overlay');
        if (!el) {
            ensureStyles();
            el = document.createElement('div');
            el.id = 'server-gone-overlay';
            el.setAttribute('role', 'alertdialog');
            el.setAttribute('aria-modal', 'true');
            el.setAttribute('aria-labelledby', 'server-gone-text');
            el.innerHTML = `<div class="server-gone-card">
                <div id="server-gone-text" class="server-gone-text"></div>
                <div id="server-gone-lost" class="server-gone-lost" hidden></div>
                <div id="server-gone-wait" class="server-gone-wait"></div>
            </div>`;
            document.body.appendChild(el);
        }
        const updating = typeof window !== 'undefined' && window.__lrdUpdateInstalling === true;
        el.querySelector('#server-gone-text').textContent = updating ? UPDATING_TEXT : SERVER_GONE_TEXT;
        el.querySelector('#server-gone-wait').textContent = updating ? '' : WAIT_TEXT;
        const lost = el.querySelector('#server-gone-lost');
        lost.textContent = LOST_TEXT;
        const sayLost = () => { lost.hidden = !SERVER_LINK.lost; };
        sayLost();
        // A write refused after the overlay went up (a debounced save
        // firing) is said too.
        if (!this._linkLostWatch) this._linkLostWatch = setInterval(sayLost, 250);
        // Everything else on the page is out of reach: no focus, no
        // clicks, nothing for assistive tech to act on.
        if (document.activeElement && typeof document.activeElement.blur === 'function') {
            try { document.activeElement.blur(); } catch (_) { /* nothing focused */ }
        }
        [...document.body.children].forEach((child) => {
            if (child !== el && child.tagName !== 'SCRIPT') child.inert = true;
        });
    }
}

function ensureStyles() {
    if (document.getElementById('server-gone-style')) return;
    const style = document.createElement('style');
    style.id = 'server-gone-style';
    style.textContent = `
#server-gone-overlay { position: fixed; inset: 0; z-index: 2147483000; display: flex;
    align-items: center; justify-content: center; padding: 16px; box-sizing: border-box;
    background: rgba(0, 0, 0, 0.62); cursor: default; }
#server-gone-overlay .server-gone-card { box-sizing: border-box; width: 440px; max-width: 100%;
    padding: 18px 20px; background: var(--ps-panel, #2e2e2e); color: var(--ps-text, #f0f0f0);
    border: 1px solid var(--ps-dark, #131313); border-left: 3px solid var(--ps-accent, #e22330);
    border-radius: 4px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    font-family: var(--font-ps, system-ui, sans-serif); }
#server-gone-overlay .server-gone-text { font-size: 15px; font-weight: 600; line-height: 1.4; }
#server-gone-overlay .server-gone-lost { margin-top: 10px; font-size: 13px; line-height: 1.45;
    color: var(--ps-accent-hi, #ef3340); font-weight: 600; }
#server-gone-overlay .server-gone-wait { margin-top: 10px; font-size: 12px; line-height: 1.45;
    color: var(--ps-faint, #969696); }
#server-gone-overlay .server-gone-wait:empty { display: none; }`;
    document.head.appendChild(style);
}

for (const k of Object.getOwnPropertyNames(_ServerLink.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ServerLink.prototype, k));
    }
}
