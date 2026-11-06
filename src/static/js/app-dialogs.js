// app-dialogs: the app's own question dialog for LEDRasterApp - a yes/no
// (appConfirm), a name to type (appPrompt), a message with one OK
// (appAlert) and a pick of several answers (appAsk) - in place of the
// browser's alert(), confirm() and prompt().
//
// Owner, 2026-11-03 (QA round 3): every native alert, confirm and prompt
// goes. The browser's own box names the page's address in its title,
// blocks the whole window, cannot be styled and, in the desktop shell,
// sits on the wrong screen. These are .modal dialogs like the rest of the
// app's (the Recent Files "File not found" one is the model). Each
// resolves a Promise with the answer, so a caller awaits it where it used
// to read the native answer straight back. A confirm keeps its meaning:
// Cancel, Esc and a click on the backdrop all answer false (no), the OK
// button true. A prompt answers the typed text, or null for Cancel.
//
// One at a time: a question asked while another stands waits its turn, so
// two answers never land on the wrong question. Esc answers the TOP one
// (its cancel), capturing on the window ahead of every other Esc rule
// (app-menubar _escapeClosesDialog included), and Enter presses the
// primary button (a prompt's Enter in its box is its OK).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Dialogs {
    // The general form. `opts`:
    //   title     the heading (plain words; optional)
    //   message   the question, plain text (newlines keep their breaks)
    //   detail    a smaller second line (a path), optional
    //   buttons   [{ label, value, primary, danger }], left to right
    //   cancel    the value Esc and the backdrop answer
    //   input     { value, placeholder } for a box to type in; the answer
    //             is then { value, text }
    //   id        the dialog's element id (tests and the log name it)
    appAsk(opts = {}) {
        const run = () => this._appAskNow(opts);
        const prev = this._appAskChain || Promise.resolve();
        const next = prev.then(run, run);
        this._appAskChain = next.catch(() => {});
        return next;
    }

    _appAskNow(opts) {
        const buttons = Array.isArray(opts.buttons) && opts.buttons.length
            ? opts.buttons : [{ label: 'OK', value: true, primary: true }];
        const cancel = Object.prototype.hasOwnProperty.call(opts, 'cancel') ? opts.cancel : false;
        const modal = document.createElement('div');
        modal.id = opts.id || 'app-ask-modal';
        modal.className = 'modal app-ask-modal';
        modal.style.display = 'block';
        modal.innerHTML = `<div class="modal-content app-ask-content" role="dialog" aria-modal="true">
            <h2 class="app-ask-title"></h2>
            <p class="app-ask-text"></p>
            <div class="app-ask-detail"></div>
            <input type="text" class="app-ask-input" autocomplete="off" spellcheck="false">
            <div class="app-ask-buttons"></div>
        </div>`;
        const title = modal.querySelector('.app-ask-title');
        if (opts.title) title.textContent = opts.title; else title.remove();
        modal.querySelector('.app-ask-text').textContent = String(opts.message == null ? '' : opts.message);
        const detail = modal.querySelector('.app-ask-detail');
        if (opts.detail) detail.textContent = opts.detail; else detail.remove();
        const input = modal.querySelector('.app-ask-input');
        if (opts.input) {
            input.value = opts.input.value == null ? '' : String(opts.input.value);
            if (opts.input.placeholder) input.placeholder = opts.input.placeholder;
        } else {
            input.remove();
        }
        const host = modal.querySelector('.app-ask-buttons');
        // Focus goes back where it was when the question closes, as it
        // does after the browser's own dialogs (a select that asked keeps
        // the focus for the next key).
        const before = document.activeElement;
        return new Promise(resolve => {
            let primaryValue = null;
            const done = (value) => {
                window.removeEventListener('keydown', onKey, true);
                modal.remove();
                if (before && before !== document.body && before.isConnected
                        && typeof before.focus === 'function') {
                    try { before.focus({ preventScroll: true }); } catch (_) { /* gone */ }
                }
                const answer = opts.input ? { value, text: input.value } : value;
                sendClientLog('app_dialog_answered', { dialog: modal.id, value: typeof value === 'string' || typeof value === 'boolean' ? value : null });
                resolve(answer);
            };
            const onKey = (e) => {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    done(cancel);
                } else if (e.key === 'Enter' && !e.isComposing && primaryValue !== null
                        && !(e.target && e.target.tagName === 'BUTTON')) {
                    e.preventDefault();
                    e.stopPropagation();
                    done(primaryValue);
                }
            };
            let focus = null;
            buttons.forEach((b, i) => {
                const el = document.createElement('button');
                el.type = 'button';
                el.className = 'btn' + (b.primary ? ' btn-primary' : '') + (b.danger ? ' app-ask-danger' : '');
                el.textContent = b.label;
                el.dataset.answer = String(i);
                el.addEventListener('click', () => done(b.value));
                host.appendChild(el);
                if (b.primary) { primaryValue = b.value; focus = el; }
            });
            modal.addEventListener('mousedown', (e) => { if (e.target === modal) done(cancel); });
            window.addEventListener('keydown', onKey, true);
            document.body.appendChild(modal);
            sendClientLog('app_dialog_open', { dialog: modal.id });
            if (opts.input) { input.focus(); input.select(); }
            else if (focus) focus.focus();
        });
    }

    // confirm(): true for OK, false for Cancel / Esc.
    appConfirm(message, opts = {}) {
        return this.appAsk({
            id: opts.id, title: opts.title, message, detail: opts.detail,
            buttons: [
                { label: opts.cancelLabel || 'Cancel', value: false },
                { label: opts.okLabel || 'OK', value: true, primary: true, danger: !!opts.danger },
            ],
            cancel: false,
        });
    }

    // prompt(): the text typed for OK, null for Cancel / Esc.
    appPrompt(message, value = '', opts = {}) {
        return this.appAsk({
            id: opts.id, title: opts.title, message,
            input: { value, placeholder: opts.placeholder },
            buttons: [
                { label: 'Cancel', value: false },
                { label: opts.okLabel || 'OK', value: true, primary: true },
            ],
            cancel: false,
        }).then(a => (a && a.value ? a.text : null));
    }

    // alert(): one OK. Resolves once it is read.
    appAlert(message, opts = {}) {
        return this.appAsk({
            id: opts.id, title: opts.title, message, detail: opts.detail,
            buttons: [{ label: 'OK', value: true, primary: true }],
            cancel: true,
        });
    }
}

for (const k of Object.getOwnPropertyNames(_Dialogs.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Dialogs.prototype, k));
    }
}
