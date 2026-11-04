/*
 * whatsnew.js: the "What's New" window shown once after an update.
 *
 * This browser remembers the version it last ran (localStorage). On the
 * first launch of a newer version the window opens when there is something
 * to say:
 *   - a new MAJOR.MINOR with curated highlights (whatsnew_content.js), or
 *   - ANY update, patch releases included, that added Advanced Guide steps
 *     (each step's `since`, quickstart.js). The window shows that
 *     version's curated entry when it has one ("1.6.1"), else the new
 *     steps' titles, then every other curated patch entry of the same
 *     MAJOR.MINOR newer than the version last run, newest first (1.6.0 ->
 *     1.6.2 reads 1.6.2's entry, then 1.6.1's); Show me is offered either
 *     way.
 * When steps were added, Show me runs exactly the Advanced Guide steps
 * whose `since` is newer than the version last run (in guide order, so a
 * user who skipped versions sees all of them), each from its own entry
 * snapshot (QuickStart.startSteps). Close skips them. Anything else (a patch
 * with no new steps, a downgrade) only moves the stamp, silently.
 *
 * A beta stamps its whole tag ("1.5.3-beta.11"), so the full 1.5.3 it led
 * to is still an update and opens the window for 1.5.3 (owner, 2026-10-21:
 * "first time start on any new version should always show it"). Up to
 * 1.5.3 a beta stamped the bare "1.5.3"; a stamp written before the
 * lrd_whatsnew_full mark reads as a beta's for the same reason. A beta
 * that goes straight to a later version never ran its own full release,
 * so 1.6.1-beta.2 -> 1.6.2 also shows 1.6.1's entry and steps.
 *
 * A brand-new install has no stamp: it is stamped silently and the
 * first-run Quick Start guide keeps its job: the window and the guide
 * never stack. Content ships with the app (offline).
 *
 * Reopen any time from Help -> What's New (open()).
 */
(function () {
    'use strict';

    // The version this browser last ran ("1.5.3"). Up to 1.5.2 it held the
    // MAJOR.MINOR the window last showed ("1.5"), which reads as "1.5.0".
    var LS_KEY = 'lrd_whatsnew_seen';
    // Set by every stamp this build writes; a bare stamp without it came
    // from a build that stamped betas bare.
    var MARK_KEY = 'lrd_whatsnew_full';
    // The first full release that writes the mark (1.5.3). A bare stamp
    // without it at this version or later can only be a beta's.
    var MARKED_SINCE = [1, 5, 3];

    // "1.5.2" / "v1.0.3.1" -> [1, 5, 2] / [1, 0, 3, 1]; null when unparseable.
    function parts(version) {
        var m = /^v?(\d+(?:\.\d+)*)/.exec(String(version == null ? '' : version).trim());
        return m ? m[1].split('.').map(Number) : null;
    }
    // Like a sort comparator; a missing part reads as 0 (1.5 = 1.5.0).
    function cmp(a, b) {
        var n = Math.max(a.length, b.length);
        for (var i = 0; i < n; i++) {
            var d = (a[i] || 0) - (b[i] || 0);
            if (d) return d;
        }
        return 0;
    }
    function clean(version) { var p = parts(version); return p ? p.join('.') : null; }
    // "1.5.3-beta.11" -> "beta.11"; null for a full release.
    function preOf(version) {
        var m = /^v?\d+(?:\.\d+)*-(\S+)/.exec(String(version == null ? '' : version).trim());
        return m ? m[1] : null;
    }
    // What a launch of `version` stamps: "1.5.3", or "1.5.3-beta.11".
    function stampOf(version) {
        var c = clean(version), pre = preOf(version);
        return c && pre ? c + '-' + pre : c;
    }
    // The version just before `version`, for counting its own steps:
    // "1.5.3" -> "1.5.2", "1.6.0" -> "1.5.99999".
    function below(version) {
        var p = parts(version);
        if (!p) return null;
        while (p.length < 3) p.push(0);
        for (var i = p.length - 1; i >= 0; i--) {
            if (p[i] > 0) {
                p[i] -= 1;
                for (var j = i + 1; j < p.length; j++) p[j] = 99999;
                return p.join('.');
            }
        }
        return null;
    }
    // "0.12.2" / "v1.0.3.1" -> "0.12" / "1.0"; null when unparseable.
    function majorMinor(version) {
        var p = parts(version);
        return p && p.length >= 2 ? (p[0] + '.' + p[1]) : null;
    }

    function content() { return window.WHATS_NEW_CONTENT || {}; }

    function getStamp() {
        try {
            var v = localStorage.getItem(LS_KEY);
            if (v && !preOf(v) && localStorage.getItem(MARK_KEY) !== '1') return v + '-legacy';
            return v;
        } catch (e) { return null; }
    }
    function setStamp(v) {
        try { localStorage.setItem(LS_KEY, v); localStorage.setItem(MARK_KEY, '1'); } catch (e) {}
    }

    // ── the guide steps (quickstart.js) ──────────────────────────────────
    function guide() { return window.QuickStart || null; }
    // The Advanced Guide steps whose `since` is newer than `after` and not
    // newer than `upTo`, in guide order.
    function stepsBetween(after, upTo) {
        var q = guide();
        return q && q.newSteps ? q.newSteps(after, upTo) : [];
    }
    function stepSince(k) {
        var q = guide();
        var s = q && q.steps ? q.steps()[k] : null;
        return s ? s.since : null;
    }
    function stepTitle(k) {
        var q = guide();
        var s = q && q.steps ? q.steps()[k] : null;
        return s ? s.title : String(k);
    }

    // The curated patch entries ("1.6.1", "1.6.2") of `cur`'s MAJOR.MINOR
    // newer than `seen` (every one when `seen` is null) and not newer than
    // `cur`, newest first.
    function patchEntries(seen, cur) {
        var hi = parts(cur), lo = seen == null ? null : parts(seen);
        var mm = majorMinor(cur);
        if (!hi || !mm) return [];
        return Object.keys(content()).filter(function (k) {
            var p = parts(k);
            return !!p && p.length >= 3 && majorMinor(k) === mm && cmp(p, hi) <= 0
                && (!lo || cmp(p, lo) > 0);
        }).sort(function (a, b) { return cmp(parts(b), parts(a)); });
    }

    /*
     * The window an update from `seen` to `cur` owes, or null: the curated
     * entries and the steps added in between. An update that crossed into a
     * new MAJOR.MINOR leads with that feature version's entry, so a person
     * skipping 1.5.0 still reads what 1.5 brought. Within one MAJOR.MINOR
     * the running version's own entry leads. Every curated patch entry
     * since `seen` follows in `also`, newest first, so 1.6.0 -> 1.6.2 reads
     * 1.6.2's entry and then 1.6.1's.
     *   { key, also: [keys], after, upTo, steps }  key null = list the steps' titles
     */
    function windowFor(seen, cur, between) {
        var steps = (between || stepsBetween)(seen, cur) || [];
        var mm = majorMinor(cur);
        var own = content()[cur] ? cur : null;
        var key = (majorMinor(seen) !== mm && content()[mm]) ? mm : own;
        var also = patchEntries(seen, cur).filter(function (k) { return k !== key; });
        // No entry of its own and no steps to list: the newest older entry leads.
        if (!key && !steps.length && also.length) key = also.shift();
        if (!key && !steps.length) return null;
        return { key: key, also: also, after: seen, upTo: cur, steps: steps };
    }

    /*
     * The whole gating rule, as a pure function of the running version and
     * the stamp (tests hit this directly; `between` stands in for the guide's
     * steps). Returns { show, stamp, window }:
     *   show   - open the window this launch
     *   stamp  - version to write NOW; when show is true the stamp is
     *            written on dismiss instead, so an update that crashes
     *            before dismissal shows again next time
     *   window - what it shows (windowFor), when show is true
     */
    function decide(currentVersion, stamped, between) {
        var cur = clean(currentVersion);
        if (!cur || !majorMinor(cur)) return { show: false, stamp: null, window: null };
        var mine = stampOf(currentVersion);
        var seen = clean(stamped);
        // First run: no stamp yet. Stamp silently; the Quick Start guide
        // owns the first launch and the window must not pile on top of it.
        if (!seen) return { show: false, stamp: mine, window: null };
        var order = cmp(parts(cur), parts(seen));
        var pre = preOf(stamped);
        // A beta's stamp (or a bare stamp no full release could have
        // written) never saw its own version's full release.
        var beta = !!pre && (pre !== 'legacy' || cmp(parts(seen), MARKED_SINCE) >= 0);
        var win = null;
        if (order === 0 && preOf(stamped) && !preOf(currentVersion)) {
            // The full release after its own betas: everything this
            // version brought is news to someone who only ran its betas.
            win = windowFor(below(cur), cur, between);
            if (win) win.after = null;
        } else if (order <= 0) {
            // The same version, or an older one: nothing new to say.
            return { show: false, stamp: stampOf(stamped) === mine ? null : mine, window: null };
        } else if (beta) {
            // A beta straight to a later version: its own version's entry
            // and steps are news too (1.6.1-beta.2 -> 1.6.2 shows 1.6.1's).
            win = windowFor(below(seen), cur, between);
            if (win) win.after = null;
        } else {
            win = windowFor(seen, cur, between);
        }
        // Updated, but nothing curated and no new steps (a plain patch):
        // stamp so the next update compares against this one, and stay quiet.
        if (!win) return { show: false, stamp: mine, window: null };
        win.stamp = mine;
        return { show: true, stamp: null, window: win };
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

    // A step title is written with HTML entities (&rsquo;); the window
    // shows text.
    function plain(html) {
        var t = document.createElement('textarea');
        t.innerHTML = String(html || '');
        return t.value;
    }

    // The window's lead line: the version of the curated entry that leads;
    // for steps alone, the version they came in, or "since" the version
    // last run when they span several.
    function heading(win) {
        if (win.key) return 'What’s new in v' + win.key;
        var one = win.steps.every(function (k) { return clean(stepSince(k)) === win.upTo; });
        return one || !win.after ? 'What’s new in v' + win.upTo : 'What’s new since v' + win.after;
    }

    function itemList(items) {
        var list = el('div', 'border-top:1px solid #3a3a3a;');
        (items || []).forEach(function (item) {
            var row = el('div', 'padding:11px 0;border-bottom:1px solid #333;');
            row.appendChild(el('div',
                'color:#fff;font-weight:600;font-size:13px;' + (item.d ? 'margin-bottom:3px;' : ''), item.h));
            if (item.d) {
                row.appendChild(el('div',
                    'color:#c0c0c0;font-size:12.5px;line-height:1.5;', item.d));
            }
            list.appendChild(row);
        });
        return list;
    }

    function render(win) {
        var panel = build().firstChild;
        panel.innerHTML = '';
        var entry = win.key ? content()[win.key] : {
            title: 'New in the Advanced Guide',
            items: win.steps.map(function (k) { return { h: plain(stepTitle(k)) }; })
        };

        panel.appendChild(el('div',
            'color:#888;font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;',
            heading(win)));
        panel.appendChild(el('h2',
            'margin:0 0 16px;color:#fff;font-size:19px;', entry.title));
        panel.appendChild(itemList(entry.items));

        // The other patch entries since the version last run, newest first.
        (win.also || []).forEach(function (k) {
            var more = content()[k];
            if (!more) return;
            panel.appendChild(el('div',
                'color:#888;font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin:22px 0 4px;',
                'And in v' + k));
            panel.appendChild(el('h2',
                'margin:0 0 16px;color:#fff;font-size:17px;', more.title));
            panel.appendChild(itemList(more.items));
        });

        var btns = el('div',
            'display:flex;justify-content:flex-end;gap:8px;margin-top:16px;');
        // Show me: the Advanced Guide steps this window is about, each
        // from its own entry snapshot. Only when there are some.
        var q = guide();
        if (win.steps.length && q && q.startSteps) {
            var show = el('button', null, 'Show me');
            show.id = 'whatsnew-show-me';
            show.className = 'btn';
            show.style.cssText = 'background:#3a3a3a;padding:8px 16px;';
            show.title = win.steps.length === 1 ? 'Play the new step of the Advanced Guide'
                : 'Play the ' + win.steps.length + ' new steps of the Advanced Guide';
            show.onclick = function () {
                dismiss();
                q.startSteps(win.steps);
            };
            btns.appendChild(show);
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

    function openWindow(win) {
        if (!win) return false;
        render(win);
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
    // on the local server, still offline); the baked page title is the
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

    // The Quick Start guide auto-shows on the first run only. If its overlay
    // is up, or is still on its way (the guide still deciding, which can
    // take a few seconds while the app initializes),
    // hold the window until the guide is gone so the two never stack. Give
    // up quietly after ~2 min without stamping, so the window simply tries
    // again next launch.
    function whenTourClear(cb, tries) {
        tries = tries || 0;
        if (tries > 240) { autoPending = false; return; }
        var overlay = document.getElementById('qs-catch');
        var tourUp = !!overlay && overlay.style.display !== 'none';
        // Is the guide on its way? It says so itself (quickstart.js
        // autoPending: true until it has shown or decided not to); with no
        // guide script, only a first run could bring one.
        var q = window.QuickStart;
        var tourComing = false;
        if (q && typeof q.autoPending === 'function') {
            tourComing = !!q.autoPending();
        } else {
            try { tourComing = localStorage.getItem('lrd_quickstart_first_run_done') !== '1'; } catch (e) {}
        }
        // On its way but its overlay not built yet: give it ~12s to appear
        // before concluding it is not coming (it gives up on its own after
        // ~6s).
        var tourPending = tourComing && !overlay && tries < 24;
        if (!tourUp && !tourPending && tries >= 4) { cb(); return; }
        setTimeout(function () { whenTourClear(cb, tries + 1); }, 500);
    }

    function show(win) {
        if (openWindow(win)) pendingStampOnDismiss = win.stamp || win.upTo;
    }

    // The launch's own decision, from load until the window has opened or
    // decided not to. The startup panel picker (app-presets.js
    // maybeOpenStartupPicker) waits it out, so the two never stack.
    var autoPending = true;

    function autoRun(force) {
        // Never auto-show inside an automated browser (same rule as the
        // guide): the backdrop would block E2E tests. Tests that exercise
        // the window itself call autoRun(true).
        if (!force && navigator.webdriver) { autoPending = false; return; }
        fetchVersion(function (version) {
            var d = decide(version, getStamp());
            if (d.stamp) setStamp(d.stamp);
            if (!d.show) { autoPending = false; return; }
            var go = function () {
                try { show(d.window); } finally { autoPending = false; }
            };
            force ? go() : whenTourClear(go, 0);
        });
    }

    // Help -> What's New, opened by hand. An update this browser has not
    // closed the window for yet shows exactly the window it is owed: the
    // steps since the version last run. Otherwise it shows the running
    // version's curated entry and then every earlier patch entry of its
    // MAJOR.MINOR, newest first (1.6.2, then 1.6.1), and Show me runs the
    // steps those versions added. A build with no entry of its own shows
    // its feature version's entry (the newest entry when there is none),
    // and Show me runs every step that feature version has added so far
    // (1.5.0 up to the running 1.5.x), so the steps always match what the
    // window is about.
    function open() {
        fetchVersion(function (version) {
            var d = decide(version, getStamp());
            if (d.show) { show(d.window); return; }
            var cur = clean(version);
            var mm = majorMinor(cur);
            var key = cur && content()[cur] ? cur : (mm && content()[mm] ? mm : null);
            if (!key) {
                key = Object.keys(content()).filter(function (k) { return parts(k); })
                    .sort(function (a, b) { return cmp(parts(b), parts(a)); })[0] || null;
            }
            var also = key === cur ? patchEntries(null, cur).filter(function (k) { return k !== cur; }) : [];
            var shown = [key].concat(also);
            var steps = !mm ? [] : stepsBetween(null, cur).filter(function (k) {
                // A version's own entry is about that version's steps (and
                // each entry shown after it, its own); a feature version's,
                // about every step it brought.
                return key === cur ? shown.indexOf(clean(stepSince(k))) >= 0
                    : majorMinor(stepSince(k)) === mm;
            });
            if (!key && !steps.length) return;
            openWindow({ key: key, also: also, after: null, upTo: cur, steps: steps });
        });
    }

    window.WhatsNew = {
        open: open,
        dismiss: dismiss,
        autoRun: autoRun,
        autoPending: function () { return autoPending; },
        decide: decide,
        windowFor: windowFor,
        _majorMinor: majorMinor,
        LS_KEY: LS_KEY,
        MARK_KEY: MARK_KEY
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { autoRun(false); });
    } else {
        autoRun(false);
    }
})();
