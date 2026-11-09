/* Output to Display: the page side (templates/output.html).
   Classic script. This page never draws a layer itself: the designer renders
   the chosen canvas with its own renderer and this page holds the pixels,
   sizes them, and handles full screen and closing. The frames come one of
   two ways:

   * a browser window the designer opened (window.open): the designer hands
     each frame to present() below (app-output-display.js);
   * a native window the desktop app opened full screen on the chosen display
     (?feed=<id>, output_native.py): this page waits on the server for each
     frame (routes_output.py), since a native window is no child of the
     designer's browser.

   Always 1:1, in the display's own resolution: one canvas pixel per display
   pixel, at the resolution the OS shows for that display, from the top-left
   corner. A 1920 x 1080 canvas fills a display set to 1920 x 1080 and the
   top-left quarter of one set to 3840 x 2160; what the canvas leaves unused
   stays black, and so does everything past the canvas.
   "The resolution the OS shows" is not the same unit everywhere:
   * macOS shows points ("looks like 1920 x 1080"; a HiDPI display draws
     each point with 2 x 2 device pixels). One canvas pixel per point is one
     per CSS pixel. (A browser zoom is taken back out: a Mac's backing scale
     is a whole number.)
   * Windows shows the display's pixels (Settings > Display resolution) and
     scales everything else by its Scale setting. One canvas pixel per
     display pixel is the CSS size divided by devicePixelRatio.
   A canvas bigger than the display is not cropped or shrunk: the output
   stays black and says so. There is no other scale; an old ?scale= on the
   address (a window opened by an earlier build) is ignored.
*/
(function () {
    'use strict';

    var params = new URLSearchParams(window.location.search);
    var feed = params.get('feed') || '';
    var canvas = document.getElementById('output-canvas');
    var ctx = canvas.getContext('2d', { alpha: false });
    var hint = document.getElementById('output-hint');
    var message = document.getElementById('output-message');
    var frames = 0;
    var fullscreenSince = 0;
    var fullscreenLeftAt = 0;
    var missingText = '';

    document.body.dataset.native = feed ? '1' : '0';
    if (feed) hint.textContent = 'Esc to close';

    function showMessage(text) {
        message.textContent = text;
        message.hidden = !text;
    }

    function isMac() {
        var p = String(navigator.platform || '');
        return /Mac/i.test(p) || (!p && /Macintosh/.test(navigator.userAgent || ''));
    }

    // Display pixels (as the OS counts them) per CSS pixel; see the top.
    function displayPxPerCss() {
        var dpr = window.devicePixelRatio || 1;
        if (isMac()) return dpr / (Math.round(dpr) || 1);
        return dpr;
    }

    function isFullscreen() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement);
    }

    // The display this window is on, in display pixels.
    function displaySize(k) {
        return {
            width: Math.round((window.screen.width || 0) * k),
            height: Math.round((window.screen.height || 0) * k)
        };
    }

    var lastLog = '';
    function logLayout(info) {
        var key = JSON.stringify(info);
        if (key === lastLog) return;
        lastLog = key;
        try {
            var body = JSON.stringify({
                action: 'output_display_layout',
                details: Object.assign({ clientTime: new Date().toISOString(), url: window.location.href }, info)
            });
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/log', new Blob([body], { type: 'application/json' }));
            } else {
                fetch('/api/log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body });
            }
        } catch (e) { /* logging never stops the picture */ }
    }

    function layout() {
        var w = canvas.width;
        var h = canvas.height;
        if (!w || !h) return;
        var k = displayPxPerCss();
        var cssW = w / k;
        var cssH = h / k;
        canvas.style.width = cssW + 'px';
        canvas.style.height = cssH + 'px';
        canvas.style.left = '0px';
        canvas.style.top = '0px';
        // Hard pixel edges: a display that draws a point with several device
        // pixels shows each canvas pixel as one crisp block.
        canvas.style.imageRendering = 'pixelated';
        var display = displaySize(k);
        var tooBig = !!(display.width && display.height && (w > display.width || h > display.height));
        canvas.style.visibility = tooBig ? 'hidden' : 'visible';
        document.body.dataset.tooBig = tooBig ? '1' : '0';
        if (tooBig) {
            showMessage('This canvas is ' + w + ' × ' + h + '; this display is '
                + display.width + ' × ' + display.height
                + '. Set the display to the canvas size, or use a smaller canvas.');
        } else if (!missingText) {
            showMessage('');
        }
        logLayout({
            native: !!feed,
            mac: isMac(),
            dpr: window.devicePixelRatio || 1,
            displayPxPerCss: k,
            screen: [window.screen.width, window.screen.height],
            display: [display.width, display.height],
            window: [window.innerWidth, window.innerHeight],
            canvas: [w, h],
            css: [cssW, cssH],
            fullscreen: isFullscreen() || (window.innerWidth === window.screen.width && window.innerHeight === window.screen.height),
            tooBig: tooBig
        });
    }

    // One frame: `src` is a canvas (or a decoded image) holding the raster
    // at its own resolution.
    function present(src, meta) {
        if (!src || !src.width || !src.height) return;
        if (canvas.width !== src.width || canvas.height !== src.height) {
            canvas.width = src.width;
            canvas.height = src.height;
        }
        try {
            ctx.drawImage(src, 0, 0);
        } catch (e) {
            // A canvas from the other window refused (should not happen on
            // one origin): go through the pixels instead.
            if (!src.getContext) throw e;
            var img = src.getContext('2d').getImageData(0, 0, src.width, src.height);
            ctx.putImageData(img, 0, 0);
        }
        frames += 1;
        document.body.dataset.frames = String(frames);
        missingText = '';
        showMessage('');
        if (meta && meta.title) document.title = meta.title;
        layout();
    }

    function missing(text) {
        canvas.width = 0;
        canvas.height = 0;
        missingText = text || 'Nothing to show.';
        showMessage(missingText);
    }

    window.lrdOutput = {
        present: present,
        missing: missing,
        params: {
            canvas: params.get('canvas') || '',
            view: params.get('view') || 'pixel-map'
        }
    };

    // ---- a browser window: fed by its opener ------------------------------

    function opener() {
        try {
            var o = window.opener;
            return (o && !o.closed) ? o : null;
        } catch (e) {
            return null;
        }
    }

    // Tell the designer window this page is ready for frames (on first load
    // and again after a reload of this window).
    function attach() {
        var o = opener();
        try {
            if (o && o.app && typeof o.app._outputDisplayAttach === 'function') {
                o.app._outputDisplayAttach(window);
                return true;
            }
        } catch (e) { /* the opener is another origin or gone */ }
        return false;
    }

    // ---- a native window: fed through the server -------------------------

    var seq = 0;
    var stopped = false;

    function decode(blob) {
        if (typeof createImageBitmap === 'function') return createImageBitmap(blob);
        return new Promise(function (resolve, reject) {
            var url = URL.createObjectURL(blob);
            var img = new Image();
            img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = function (e) { URL.revokeObjectURL(url); reject(e); };
            img.src = url;
        });
    }

    function poll() {
        if (stopped) return;
        fetch('/api/output/feed/' + encodeURIComponent(feed) + '?after=' + seq, { cache: 'no-store' })
            .then(function (res) {
                if (res.status === 410 || res.status === 404) {
                    // Closed from the dialog, or the designer left: the app
                    // is closing this window.
                    stopped = true;
                    missing('This output was closed.');
                    return null;
                }
                if (res.status === 204) return null;
                if (!res.ok) throw new Error('HTTP ' + res.status);
                var next = Number(res.headers.get('X-Frame-Seq')) || seq + 1;
                var title = '';
                try { title = decodeURIComponent(res.headers.get('X-Output-Title') || ''); } catch (e) { title = ''; }
                var type = res.headers.get('Content-Type') || '';
                if (type.indexOf('application/json') === 0) {
                    return res.json().then(function (j) {
                        seq = next;
                        if (title) document.title = title;
                        missing(j.message);
                    });
                }
                return res.blob().then(decode).then(function (img) {
                    seq = next;
                    present(img, { title: title });
                    if (img && typeof img.close === 'function') img.close();
                });
            })
            .then(function () { setTimeout(poll, 0); },
                function () { setTimeout(poll, 1000); });
    }

    function closeNative() {
        stopped = true;
        fetch('/api/output/feed/' + encodeURIComponent(feed) + '/close', { method: 'POST' })
            .catch(function () { /* the app is going anyway */ });
    }

    if (feed) {
        poll();
    } else {
        if (!attach()) {
            showMessage('Open this from View › Output to Display in the designer window.');
        }
        // The designer window closing takes its outputs with it.
        setInterval(function () {
            if (!opener()) window.close();
        }, 1000);
    }

    // ---- full screen (browser windows; a native window opens full screen) --
    function enterFullscreen() {
        if (feed) return;
        var el = document.documentElement;
        var req = el.requestFullscreen || el.webkitRequestFullscreen;
        if (!req) return;
        try {
            var p = req.call(el);
            if (p && typeof p.catch === 'function') p.catch(function () {});
        } catch (e) { /* needs a gesture; the hint says how */ }
    }
    function exitFullscreen() {
        var exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (!exit) return;
        try {
            var p = exit.call(document);
            if (p && typeof p.catch === 'function') p.catch(function () {});
        } catch (e) { /* already out */ }
    }

    function fadeHintSoon() {
        hint.classList.remove('faded');
        clearTimeout(fadeHintSoon.timer);
        fadeHintSoon.timer = setTimeout(function () { hint.classList.add('faded'); }, 4000);
    }

    document.addEventListener('fullscreenchange', function () {
        if (isFullscreen()) {
            fullscreenSince = Date.now();
            hint.classList.add('faded');
        } else {
            fullscreenLeftAt = Date.now();
            fadeHintSoon();
        }
        layout();
    });

    // A click goes full screen; a double-click (or F) toggles. The first
    // click of a double-click has just gone full screen, so the double-click
    // only leaves when full screen is older than the double-click itself.
    document.addEventListener('click', function () {
        if (!isFullscreen()) enterFullscreen();
    });
    document.addEventListener('dblclick', function () {
        if (!feed && isFullscreen() && Date.now() - fullscreenSince > 700) exitFullscreen();
    });
    document.addEventListener('keydown', function (e) {
        if (feed) {
            if (e.key === 'Escape') closeNative();
            return;
        }
        if (e.key === 'f' || e.key === 'F') {
            if (isFullscreen()) exitFullscreen(); else enterFullscreen();
        } else if (e.key === 'Escape') {
            // Esc leaves full screen (the browser does that itself); a
            // second Esc, out of full screen, ends the output.
            if (isFullscreen()) {
                exitFullscreen();
            } else if (Date.now() - fullscreenLeftAt > 400) {
                window.close();
            }
        }
    });

    // The pointer hides over the picture after two still seconds.
    var idleTimer = null;
    document.addEventListener('mousemove', function () {
        document.body.classList.remove('lrd-output-idle');
        clearTimeout(idleTimer);
        idleTimer = setTimeout(function () {
            document.body.classList.add('lrd-output-idle');
        }, 2000);
    });

    window.addEventListener('resize', layout);
    // A move to a display with another pixel ratio re-sizes 1:1.
    (function watchRatio() {
        if (!window.matchMedia) return;
        var mq = window.matchMedia('(resolution: ' + (window.devicePixelRatio || 1) + 'dppx)');
        var onChange = function () {
            if (mq.removeEventListener) mq.removeEventListener('change', onChange);
            layout();
            watchRatio();
        };
        if (mq.addEventListener) mq.addEventListener('change', onChange);
    })();

    fadeHintSoon();
    if (params.get('fs') === '1') enterFullscreen();
})();
