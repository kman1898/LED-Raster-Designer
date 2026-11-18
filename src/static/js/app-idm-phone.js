// app-idm-phone: the IDM Locator tab's way onto a phone. "Use a phone"
// opens a dialog with a QR code of the phone page's address on this
// computer's network (routes_idm_phone.py /api/idm-phone/address) and the
// address in plain text beside it. The code is drawn here (qr-code.js); no
// network service sees the address. A computer on more than one network
// lists each address, the likeliest first, and remembers the one picked
// (per viewer). A server the launcher set to this computer alone, or a
// computer on no network, gets a plain note saying what to change.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog, escapeCovered } from './helpers.js';
import { qrSvg } from './qr-code.js';

const ADDRESS_KEY = 'lrdIdmPhoneAddress';

class _IdmPhone {
    // Once, from _idmWire.
    _idmPhoneWire() {
        const btn = document.getElementById('idm-phone-open');
        if (!btn || btn.dataset.wired) return;
        btn.dataset.wired = '1';
        btn.addEventListener('click', () => {
            this.openIdmPhoneDialog();
            if (document.activeElement === btn) btn.blur();
        });
    }

    async openIdmPhoneDialog() {
        const modal = this._idmPhoneDialog();
        // flex: the dialog sits in the middle of the window (style.css)
        modal.style.display = 'flex';
        const body = modal.querySelector('.idm-phone-body');
        body.setAttribute('aria-busy', 'true');
        let info = null;
        try {
            const res = await fetch('/api/idm-phone/address', { cache: 'no-store' });
            if (res.ok) info = await res.json();
        } catch (_) { info = null; }
        this._idmPhoneInfo = info;
        this._idmPhoneRender();
        body.removeAttribute('aria-busy');
        sendClientLog('idm_phone_dialog', {
            addresses: info ? info.addresses.length : 0, reachable: !!(info && info.reachable),
        });
        return info;
    }

    closeIdmPhoneDialog() {
        const modal = document.getElementById('idm-phone-modal');
        if (modal) modal.style.display = 'none';
    }

    _idmPhoneDialog() {
        let modal = document.getElementById('idm-phone-modal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'idm-phone-modal';
        modal.className = 'modal';
        modal.style.display = 'none';
        modal.innerHTML = `
            <div class="modal-content idm-phone-dialog" role="dialog" aria-labelledby="idm-phone-title">
                <h2 id="idm-phone-title">Use a phone</h2>
                <div class="idm-phone-body">
                    <div id="idm-phone-qr" class="idm-phone-qr" hidden></div>
                    <div class="idm-phone-text">
                        <div id="idm-phone-lead">Scan the code with the phone's camera, or type the address into its browser:</div>
                        <span id="idm-phone-url" class="idm-phone-url"></span>
                        <div id="idm-phone-pick" class="idm-phone-pick" hidden>
                            <label for="idm-phone-address">Network</label>
                            <select id="idm-phone-address" data-tooltip="Network, This computer is on more than one network. Pick the one the phones are on."></select>
                        </div>
                        <div>The phone must be on the same network as this computer.</div>
                        <div id="idm-phone-note" class="idm-phone-note" hidden></div>
                    </div>
                </div>
                <div class="idm-phone-actions">
                    <button type="button" class="btn" id="idm-phone-copy" data-tooltip="Copy address, Copy the phone page's address, to send it to a phone.">Copy address</button>
                    <button type="button" class="btn btn-primary" id="idm-phone-close">Close</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.closeIdmPhoneDialog();
        });
        modal.querySelector('#idm-phone-close').addEventListener('click', () => this.closeIdmPhoneDialog());
        modal.querySelector('#idm-phone-address').addEventListener('change', (e) => {
            try { localStorage.setItem(ADDRESS_KEY, e.target.value); } catch (_) { /* per viewer only */ }
            sendClientLog('idm_phone_address', { address: e.target.value });
            this._idmPhoneRender();
        });
        modal.querySelector('#idm-phone-copy').addEventListener('click', () => this._idmPhoneCopy());
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.style.display !== 'none'
                    && !escapeCovered(modal, e)) this.closeIdmPhoneDialog();
        });
        return modal;
    }

    // The address picked: the one this viewer picked before while it is
    // still one of this computer's, else the likeliest.
    _idmPhonePicked(info) {
        const list = (info && info.addresses) || [];
        let saved = null;
        try { saved = localStorage.getItem(ADDRESS_KEY); } catch (_) { saved = null; }
        return list.includes(saved) ? saved : (list[0] || null);
    }

    // The phone page's address on `ip`.
    _idmPhoneUrl(info, ip) {
        const i = info && info.addresses ? info.addresses.indexOf(ip) : -1;
        return i >= 0 && info.urls ? info.urls[i] : '';
    }

    _idmPhoneRender() {
        const info = this._idmPhoneInfo;
        const qr = document.getElementById('idm-phone-qr');
        const url = document.getElementById('idm-phone-url');
        const lead = document.getElementById('idm-phone-lead');
        const pick = document.getElementById('idm-phone-pick');
        const sel = document.getElementById('idm-phone-address');
        const note = document.getElementById('idm-phone-note');
        const copy = document.getElementById('idm-phone-copy');
        if (!qr || !url) return;
        const ip = this._idmPhonePicked(info);
        const link = ip ? this._idmPhoneUrl(info, ip) : '';
        let why = '';
        if (!info) {
            why = 'The address could not be read. Close this and try again.';
        } else if (!info.reachable && info.why === 'local-only') {
            why = 'Phones can\'t reach the app yet: it is set to this computer only. In the launcher, set Network interface to All Interfaces, restart the app, then open this again.';
        } else if (!info.reachable) {
            why = 'This computer has no network address a phone can reach. Join the network the phones are on (Wi-Fi or a cable), then open this again.';
        } else if (info.addresses.length > 1) {
            why = 'This computer is on more than one network. If the phone can\'t open the page, pick another network above.';
        }
        qr.hidden = !link;
        qr.innerHTML = link ? qrSvg(link, `QR code for ${link}`) : '';
        qr.dataset.url = link;
        url.textContent = link;
        url.hidden = !link;
        if (lead) lead.hidden = !link;
        if (copy) copy.disabled = !link;
        const many = !!(info && info.addresses && info.addresses.length > 1);
        if (pick) pick.hidden = !many;
        if (sel) {
            const opts = many ? info.addresses : [];
            if (sel.options.length !== opts.length || opts.some((a, i) => sel.options[i].value !== a)) {
                sel.innerHTML = '';
                opts.forEach(a => {
                    const o = document.createElement('option');
                    o.value = a;
                    o.textContent = a;
                    sel.appendChild(o);
                });
            }
            if (ip && many) sel.value = ip;
        }
        if (note) {
            note.textContent = why;
            note.hidden = !why;
        }
    }

    async _idmPhoneCopy() {
        const url = document.getElementById('idm-phone-url');
        const text = url ? url.textContent : '';
        if (!text) return;
        let ok = false;
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
                ok = true;
            }
        } catch (_) { ok = false; }
        if (!ok && url) {
            // the address is selected instead, for Ctrl+C
            const range = document.createRange();
            range.selectNodeContents(url);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
        this._toast(ok ? 'Address copied.' : 'Press Ctrl+C (Cmd+C on a Mac) to copy the address.');
    }
}

for (const k of Object.getOwnPropertyNames(_IdmPhone.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_IdmPhone.prototype, k));
    }
}
