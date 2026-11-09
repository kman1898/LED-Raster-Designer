/**
 * LED Raster Designer, Update Checker
 *
 * Checks /api/update/check on startup and when the user clicks
 * Help → Check for Updates. Shows a dismissable banner when a
 * newer version is available.
 *
 * An installed Windows copy (the check answers can_install) updates in
 * place (owner, 2026-11-08): Update downloads the release's setup with a
 * progress bar, the server checks it against the release's checksums, and
 * Install and restart asks about unsaved changes, runs the setup and closes
 * the app; the setup reopens it. Every other copy (macOS, the Windows .zip,
 * a source run, another device on the network) keeps the Download link to
 * the release page.
 */
(function () {
    'use strict';

    const banner      = document.getElementById('update-banner');
    const bannerText  = document.getElementById('update-banner-text');
    const bannerLink  = document.getElementById('update-banner-link');
    const bannerClose = document.getElementById('update-banner-dismiss');
    const actionBtn   = document.getElementById('update-banner-action');
    const progress    = document.getElementById('update-banner-progress');
    const progressBar = document.getElementById('update-banner-progress-bar');

    if (!banner) return;

    // The banner sits in the page's flow above the menu bar (style.css), so
    // showing it, hiding it or a line wrapping in it changes the height the
    // app has. Whatever measures (the canvas, the panels' fold tabs and
    // resize strips) re-measures then, as on a window resize.
    var bannerHeight = 0;
    var relayoutQueued = false;
    function relayout() {
        var h = banner.offsetHeight;
        if (h === bannerHeight || relayoutQueued) return;
        relayoutQueued = true;
        requestAnimationFrame(function () {
            relayoutQueued = false;
            bannerHeight = banner.offsetHeight;
            try { window.dispatchEvent(new Event('resize')); } catch (_) { /* old browser */ }
            var app = window.app;
            if (app && typeof app.settleLayout === 'function') app.settleLayout();
        });
    }
    if (typeof ResizeObserver === 'function') new ResizeObserver(relayout).observe(banner);

    var shown = null;        // the check answer the banner shows
    var pollTimer = null;
    var installing = false;
    var downloading = false;   // Update clicked, not yet ready or refused

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

    // A Check for Updates answer is said in the app's own message (the
    // toast every other notice uses), not a browser alert() that stops the
    // page and reads as the browser talking.
    function say(msg, isError) {
        var app = window.app;
        if (app && typeof app._toast === 'function') app._toast(msg, !!isError, 6000);
        else if (window.console) console.warn(msg);
    }

    function setAction(label) {
        if (!actionBtn) return;
        if (label) {
            actionBtn.textContent = label;
            actionBtn.disabled = false;
            actionBtn.style.display = '';
        } else {
            actionBtn.style.display = 'none';
        }
    }

    function setProgress(percent) {
        if (!progress) return;
        if (percent === null || percent === undefined) {
            progress.style.display = 'none';
            return;
        }
        progress.style.display = '';
        progressBar.style.width = Math.max(0, Math.min(100, percent)) + '%';
        progress.setAttribute('aria-valuenow', String(Math.round(percent)));
    }

    // The release page link: the whole answer on a copy that cannot
    // update itself, and the way out when an update was refused.
    function setLink(show) {
        if (show && shown && shown.download_url) {
            bannerLink.href = shown.download_url;
            bannerLink.style.display = '';
        } else {
            bannerLink.style.display = 'none';
        }
    }

    var NOT_DOWNLOADED = 'The update could not be downloaded. Check the internet connection and click Update to try again.';

    function availableText(data) {
        return 'Version ' + data.latest_version + ' is available (you have ' + data.current_version + ')';
    }

    // ── Show / hide banner ──────────────────────────────────────────
    function showBanner(data) {
        if (!data.available) return;
        shown = data;
        bannerText.textContent = availableText(data);
        setProgress(null);
        if (data.can_install && actionBtn) {
            setLink(false);
            setAction('Update');
            // A download already under way (or done) picks up where it is.
            fetchStatus().then(applyStatus).catch(function () { /* idle */ });
        } else {
            setAction(null);
            setLink(true);
        }
        banner.style.display = '';
    }

    // ── Update in place ─────────────────────────────────────────────
    function fetchStatus() {
        return fetch('/api/update/status').then(function (r) {
            if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
            return r.json();
        });
    }

    function stopPolling() {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    }

    function poll() {
        stopPolling();
        pollTimer = setTimeout(function () {
            pollTimer = null;
            fetchStatus().then(applyStatus).catch(function () {
                downloading = false;
                say(NOT_DOWNLOADED, true);
                if (shown) showBanner(shown);
            });
        }, 400);
    }

    // The server's download state, said in the banner.
    function applyStatus(st) {
        if (!st || installing) return;
        downloading = st.state === 'downloading' || st.state === 'verifying';
        if (st.state === 'downloading') {
            bannerText.textContent = 'Downloading ' + (st.percent || 0) + '%';
            setAction(null);
            setProgress(st.percent || 0);
            poll();
        } else if (st.state === 'verifying') {
            bannerText.textContent = 'Checking the download';
            setAction(null);
            setProgress(100);
            poll();
        } else if (st.state === 'ready') {
            stopPolling();
            bannerText.textContent = 'Version ' + (st.version || (shown && shown.latest_version) || '')
                + ' is ready to install';
            setProgress(null);
            setAction('Install and restart');
        } else if (st.state === 'error') {
            stopPolling();
            if (st.error) say(st.error, true);
            if (shown) {
                bannerText.textContent = availableText(shown);
                setProgress(null);
                setAction('Update');
                setLink(true);
            }
        }
    }

    function startDownload() {
        downloading = true;
        setAction(null);
        setLink(false);
        bannerText.textContent = 'Downloading 0%';
        setProgress(0);
        fetch('/api/update/download', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(applyStatus)
            .catch(function () {
                downloading = false;
                say(NOT_DOWNLOADED, true);
                if (shown) showBanner(shown);
            });
    }

    function postInstall(discard) {
        return fetch('/api/update/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ discard: !!discard }),
        }).then(function (r) {
            return r.json().then(function (body) { body._status = r.status; return body; });
        });
    }

    // Install and restart: the same Save / Don't Save / Cancel question New
    // and Open ask, then the setup runs and the app closes. Work is never
    // dropped without an answer: a show with unsaved changes elsewhere (the
    // server says so) is asked about before anything closes.
    async function install() {
        var app = window.app;
        var hadUnsaved = !!(app && typeof app.projectHasUnsavedChanges === 'function'
            && app.projectHasUnsavedChanges());
        if (app && typeof app.confirmUnsavedChanges === 'function') {
            if (!(await app.confirmUnsavedChanges('update'))) return;
            // A Save tells the server the show is saved; let that land first.
            if (app._unsavedPost) { try { await app._unsavedPost; } catch (_) { /* said again */ } }
        }
        actionBtn.disabled = true;
        var answer = await postInstall(hadUnsaved);
        if (answer._status === 409 && answer.unsaved) {
            var go = app && typeof app.appAsk === 'function' ? await app.appAsk({
                id: 'update-unsaved-modal',
                title: 'Install the update?',
                message: 'The show has changes that are not saved. If the app closes to install the update now, those changes are lost.',
                buttons: [
                    { label: 'Cancel', value: false, primary: true },
                    { label: 'Install anyway', value: true, danger: true },
                ],
                cancel: false,
            }) : false;
            if (!go) { actionBtn.disabled = false; return; }
            answer = await postInstall(true);
        }
        if (!answer.ok) {
            say(answer.error || 'The update could not be installed.', true);
            fetchStatus().then(applyStatus).catch(function () { /* left as is */ });
            actionBtn.disabled = false;
            return;
        }
        installing = true;
        stopPolling();
        setAction(null);
        setProgress(null);
        bannerClose.style.display = 'none';
        bannerText.textContent = 'Installing version ' + (answer.version || '')
            + '. The app closes now and opens again when the update is done.';
        reloadWhenUpdated(shown && shown.current_version);
    }

    // This page comes back by itself on the new version: once the app
    // answers again with a version other than the one that installed, the
    // page reloads (and keeps its place, app-start-page.js).
    function reloadWhenUpdated(oldVersion) {
        var tries = 0;
        function again() {
            if (++tries > 300) {   // ten minutes
                bannerText.textContent = 'The update is taking longer than it should. '
                    + 'Open LED Raster Designer from the Start menu.';
                return;
            }
            setTimeout(function () {
                fetch('/api/version', { cache: 'no-store' })
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (d) {
                        if (d && d.version && d.version !== oldVersion) window.location.reload();
                        else again();
                    })
                    .catch(again);
            }, 2000);
        }
        again();
    }

    if (actionBtn) {
        actionBtn.addEventListener('click', function () {
            if (actionBtn.disabled) return;
            if (actionBtn.textContent === 'Install and restart') {
                install().catch(function () {
                    actionBtn.disabled = false;
                    say('The update could not be started. Click Install and restart to try again.', true);
                });
            } else {
                startDownload();
            }
        });
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
                // A download or an install under way keeps its banner.
                if (installing || downloading) return;
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
        stopPolling();
        if (shown && shown.latest_version) dismiss(shown.latest_version);
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
