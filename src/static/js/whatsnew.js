/*
 * whatsnew.js: the "What's New" splash shown once after a feature update.
 *
 * Shows when the running version's MAJOR.MINOR differs from the last one
 * this browser saw (localStorage), and never on a patch release
 * (0.12.1 -> 0.12.2 stays silent). A brand-new install has no stamp: it is
 * stamped silently and the first-run Quick Start tour keeps its job - the
 * splash and the tour never stack. Content comes from whatsnew_content.js
 * (curated highlights per MAJOR.MINOR, shipped with the app - offline).
 *
 * Reopen any time from Help -> What's New.
 */
(function () {
    'use strict';

    var LS_KEY = 'lrd_whatsnew_seen'; // last MAJOR.MINOR this browser saw

    // "0.12.2" / "v1.0.3.1" -> "0.12" / "1.0"; null when unparseable.
    function majorMinor(version) {
        var m = /^v?(\d+)\.(\d+)/.exec(String(version || '').trim());
        return m ? (m[1] + '.' + m[2]) : null;
    }

    function content() { return window.WHATS_NEW_CONTENT || {}; }

    function getStamp() {
        try { return localStorage.getItem(LS_KEY); } catch (e) { return null; }
    }
    function setStamp(mm) {
        try { localStorage.setItem(LS_KEY, mm); } catch (e) {}
    }

    /*
     * The whole gating rule, as a pure function (tests hit this directly).
     * Returns { show, stamp }:
     *   show  - open the splash this launch
     *   stamp - MAJOR.MINOR to write NOW (first run / no entry); when show
     *           is true the stamp is written on dismiss instead, so an
     *           update that crashes before dismissal shows again next time.
     */
    function decide(currentVersion, stamped) {
        var cur = majorMinor(currentVersion);
        if (!cur) return { show: false, stamp: null };
        // First run: no stamp yet. Stamp silently; the Quick Start tour owns
        // the first launch and the splash must not pile on top of it.
        if (!stamped) return { show: false, stamp: cur };
        // Same feature version (patch updates land here too): stay quiet.
        if (majorMinor(stamped) === cur) return { show: false, stamp: null };
        // Feature version changed but we have nothing curated to say:
        // stamp so it does not re-check forever, and stay quiet.
        if (!content()[cur]) return { show: false, stamp: cur };
        return { show: true, stamp: null };
    }

    // ── the modal ────────────────────────────────────────────────────────
    // Same desktop-panel language as the About / Shortcuts dialogs: a
    // .modal backdrop with a neutral-gray .modal-content panel, accent bar
    // on top (accent-aware via --ps-accent). Built lazily, reused.

    var modal = null;

    function build() {
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'whatsnew-modal';
        modal.className = 'modal';
        modal.style.display = 'none';

        var panel = document.createElement('div');
        panel.className = 'modal-content';
        panel.style.cssText =
            'background:#252525;border-radius:8px;border:1px solid #3a3a3a;' +
            'border-top:3px solid var(--ps-accent, #e22330);' +
            'max-width:520px;margin:56px auto;padding:26px 30px 20px;' +
            'max-height:calc(100vh - 112px);overflow-y:auto;';
        modal.appendChild(panel);
        document.body.appendChild(modal);
        modal.addEventListener('click', function (e) {
            if (e.target === modal) dismiss();
        });
        return modal;
    }

    function el(tag, css, text) {
        var n = document.createElement(tag);
        if (css) n.style.cssText = css;
        if (text != null) n.textContent = text;
        return n;
    }

    function render(mm, entry) {
        var panel = build().firstChild;
        panel.innerHTML = '';

        panel.appendChild(el('div',
            'color:#888;font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;',
            'What’s new in v' + mm));
        panel.appendChild(el('h2',
            'margin:0 0 16px;color:#fff;font-size:19px;', entry.title));

        var list = el('div', 'border-top:1px solid #3a3a3a;');
        (entry.items || []).forEach(function (item) {
            var row = el('div', 'padding:11px 0;border-bottom:1px solid #333;');
            row.appendChild(el('div',
                'color:#fff;font-weight:600;font-size:13px;margin-bottom:3px;', item.h));
            row.appendChild(el('div',
                'color:#c0c0c0;font-size:12.5px;line-height:1.5;', item.d));
            list.appendChild(row);
        });
        panel.appendChild(list);

        var btns = el('div',
            'display:flex;justify-content:flex-end;gap:8px;margin-top:16px;');
        // The tour system has a stable entry point (window.QuickStart), so
        // offer the walkthrough; without it, plain dismiss only. The
        // what's-new TOUR is the natural continuation of this splash - the
        // Advanced Guide is the fallback for a build whose quickstart
        // predates the tour registry.
        var startTour = window.QuickStart
            && (window.QuickStart.startWhatsNew || window.QuickStart.startAdvanced);
        if (startTour) {
            var tour = el('button', null, 'See the walkthrough');
            tour.id = 'whatsnew-tour';
            tour.className = 'btn';
            tour.style.cssText = 'background:#3a3a3a;padding:8px 16px;';
            tour.onclick = function () {
                dismiss();
                startTour();
            };
            btns.appendChild(tour);
        }
        var close = el('button', null, 'Close');
        close.id = 'whatsnew-close';
        close.className = 'btn';
        close.style.cssText =
            'background:var(--ps-accent, #e22330);color:#fff;padding:8px 20px;';
        close.onclick = dismiss;
        btns.appendChild(close);
        panel.appendChild(btns);
    }

    var pendingStampOnDismiss = null;

    function openFor(mm) {
        var entry = content()[mm];
        if (!entry) return false;
        render(mm, entry);
        modal.style.display = 'block';
        // A reopened panel starts at the top (after display, so the reset
        // is not clamped away while the panel has no layout).
        modal.firstChild.scrollTop = 0;
        return true;
    }

    function dismiss() {
        if (modal) modal.style.display = 'none';
        if (pendingStampOnDismiss) {
            setStamp(pendingStampOnDismiss);
            pendingStampOnDismiss = null;
        }
    }

    // ── version source ───────────────────────────────────────────────────
    // /api/version is the same authority the About dialog uses (VERSION.txt
    // on the local server - still offline); the baked page title is the
    // fallback if that fetch fails.

    function fetchVersion(cb) {
        var fromTitle = function () {
            var m = /v(\d+\.\d+[\d.]*)/.exec(document.title || '');
            cb(m ? m[1] : null);
        };
        try {
            fetch('/api/version')
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    (d && d.version) ? cb(d.version) : fromTitle();
                })
                .catch(fromTitle);
        } catch (e) { fromTitle(); }
    }

    // ── auto-show ────────────────────────────────────────────────────────

    // The Quick Start tour auto-shows on launch unless the user disabled
    // it. If its overlay is up - or is still on its way (tour enabled but
    // not built yet; it can take a few seconds while the app initializes) -
    // hold the splash until the tour is gone so the two never stack. Give
    // up quietly after ~2 min without stamping, so the splash simply tries
    // again next launch.
    function whenTourClear(cb, tries) {
        tries = tries || 0;
        if (tries > 240) return;
        var overlay = document.getElementById('qs-catch');
        var tourUp = !!overlay && overlay.style.display !== 'none';
        var tourEnabled = true;
        try {
            tourEnabled = localStorage.getItem('lrd_quickstart_disabled') !== '1';
        } catch (e) {}
        // Tour enabled but its overlay never built: it may still be waiting
        // for the app to finish loading. Give it ~12s to appear before
        // concluding it is not coming (it gives up on its own after ~6s).
        var tourPending = tourEnabled && !overlay && tries < 24;
        if (!tourUp && !tourPending && tries >= 4) { cb(); return; }
        setTimeout(function () { whenTourClear(cb, tries + 1); }, 500);
    }

    function autoRun(force) {
        // Never auto-show inside an automated browser (same rule as the
        // tour): the backdrop would block E2E tests. Tests that exercise
        // the splash itself call autoRun(true).
        if (!force && navigator.webdriver) return;
        fetchVersion(function (version) {
            var d = decide(version, getStamp());
            if (d.stamp) setStamp(d.stamp);
            if (!d.show) return;
            var mm = majorMinor(version);
            var go = function () {
                if (openFor(mm)) pendingStampOnDismiss = mm;
                else setStamp(mm); // no entry (decide() already guards this)
            };
            force ? go() : whenTourClear(go, 0);
        });
    }

    // Help -> What's New. Shows the running version's entry; if a build
    // ever runs without one, falls back to the newest entry we have.
    function open() {
        fetchVersion(function (version) {
            var mm = majorMinor(version);
            if (!mm || !content()[mm]) {
                var keys = Object.keys(content()).sort(function (a, b) {
                    var pa = a.split('.').map(Number), pb = b.split('.').map(Number);
                    return (pb[0] - pa[0]) || (pb[1] - pa[1]);
                });
                mm = keys[0];
            }
            if (mm) openFor(mm);
        });
    }

    window.WhatsNew = {
        open: open,
        dismiss: dismiss,
        autoRun: autoRun,
        decide: decide,
        _majorMinor: majorMinor,
        LS_KEY: LS_KEY
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { autoRun(false); });
    } else {
        autoRun(false);
    }
})();
