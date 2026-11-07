/**
 * LED Raster Designer, Update Checker
 *
 * Checks /api/update/check on startup and when the user clicks
 * Help → Check for Updates. Shows a dismissable banner when a
 * newer version is available.
 */
(function () {
    'use strict';

    const banner      = document.getElementById('update-banner');
    const bannerText  = document.getElementById('update-banner-text');
    const bannerLink  = document.getElementById('update-banner-link');
    const bannerClose = document.getElementById('update-banner-dismiss');

    if (!banner) return;

    // ── Helpers ──────────────────────────────────────────────────────
    function dismissedKey(version) {
        return 'lrd-update-dismissed-' + version;
    }

    function isDismissed(version) {
        try { return localStorage.getItem(dismissedKey(version)) === '1'; }
        catch (_) { return false; }
    }

    function dismiss(version) {
        try { localStorage.setItem(dismissedKey(version), '1'); }
        catch (_) { /* private browsing */ }
        banner.style.display = 'none';
    }

    // ── Show / hide banner ──────────────────────────────────────────
    function showBanner(data) {
        if (!data.available) return;
        bannerText.textContent =
            'Version ' + data.latest_version + ' is available (you have ' + data.current_version + ')';
        if (data.download_url) {
            bannerLink.href = data.download_url;
            bannerLink.style.display = '';
        } else {
            bannerLink.style.display = 'none';
        }
        banner.style.display = '';
    }

    // A Check for Updates answer is said in the app's own message (the
    // toast every other notice uses), not a browser alert() that stops the
    // page and reads as the browser talking.
    function say(msg, isError) {
        var app = window.app;
        if (app && typeof app._toast === 'function') app._toast(msg, !!isError, 6000);
        else if (window.console) console.warn(msg);
    }

    // ── Check API ───────────────────────────────────────────────────
    function checkForUpdate(opts) {
        opts = opts || {};
        var url = '/api/update/check';
        if (opts.force) url += '?force=1';

        fetch(url)
            .then(function (r) {
                if (!r.ok) {
                    throw new Error('Server returned HTTP ' + r.status);
                }
                return r.json();
            })
            .then(function (data) {
                if (data.error && opts.userInitiated) {
                    say('Update check failed: ' + data.error, true);
                    return;
                }
                if (!data.available) {
                    if (opts.userInitiated) {
                        say('You are running the latest version (' + data.current_version + ').');
                    }
                    return;
                }
                // Silent check: respect previous dismiss
                if (!opts.userInitiated && isDismissed(data.latest_version)) return;
                showBanner(data);
            })
            .catch(function (err) {
                if (opts.userInitiated) {
                    say('Could not reach the update server. ' + (err.message || err), true);
                }
                console.warn('Update check failed:', err);
            });
    }

    // ── Dismiss button ──────────────────────────────────────────────
    bannerClose.addEventListener('click', function () {
        var version = bannerText.textContent.match(/Version ([\d.]+)/);
        if (version) dismiss(version[1]);
        else banner.style.display = 'none';
    });

    // ── Hook into Help menu ─────────────────────────────────────────
    document.addEventListener('click', function (e) {
        var el = e.target.closest('.menu-option[data-action="check-updates"]');
        if (el) {
            checkForUpdate({ force: true, userInitiated: true });
        }
    });

    // ── Auto-check on startup (silent, cached) ─────────────────────
    setTimeout(function () { checkForUpdate({ force: false }); }, 3000);
})();
