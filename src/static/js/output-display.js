/* Output to Display: the page side (templates/output.html).
   Classic script. The designer window that opened this page renders the
   chosen canvas with its own renderer and hands each frame to present()
   below (app-output-display.js). This page never draws a layer itself: it
   holds the pixels, sizes them, and handles full screen and closing.

   Scale modes (?scale=):
     fit   - the whole raster, as large as the window allows, centred.
     1to1  - one raster pixel on one device pixel, from the top-left corner
             (the CSS size is divided by devicePixelRatio, so a 150% display
             still gets the raster pixel for pixel).
*/
(function () {
    'use strict';

    var params = new URLSearchParams(window.location.search);
    var scaleMode = params.get('scale') === '1to1' ? '1to1' : 'fit';
    var canvas = document.getElementById('output-canvas');
    var ctx = canvas.getContext('2d', { alpha: false });
    var hint = document.getElementById('output-hint');
    var message = document.getElementById('output-message');
    var frames = 0;
    var fullscreenSince = 0;
    var fullscreenLeftAt = 0;

    document.body.dataset.scale = scaleMode;

    function showMessage(text) {
        message.textContent = text;
        message.hidden = !text;
    }

    function layout() {
        var w = canvas.width;
        var h = canvas.height;
        if (!w || !h) return;
        var dpr = window.devicePixelRatio || 1;
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var cssW, cssH, left, top;
        if (scaleMode === '1to1') {
            cssW = w / dpr;
            cssH = h / dpr;
            left = 0;
            top = 0;
        } else {
            var s = Math.min(vw / w, vh / h);
            cssW = w * s;
            cssH = h * s;
            left = Math.max(0, (vw - cssW) / 2);
            top = Math.max(0, (vh - cssH) / 2);
        }
        canvas.style.width = cssW + 'px';
        canvas.style.height = cssH + 'px';
        canvas.style.left = left + 'px';
        canvas.style.top = top + 'px';
        // Hard pixel edges whenever a raster pixel covers one or more device
        // pixels; smoothing only when Fit has to shrink the raster.
        canvas.style.imageRendering = (cssW * dpr >= w - 0.5) ? 'pixelated' : 'auto';
    }

    // One frame from the designer window: `src` is a canvas holding the
    // raster at its own resolution.
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
            var img = src.getContext('2d').getImageData(0, 0, src.width, src.height);
            ctx.putImageData(img, 0, 0);
        }
        frames += 1;
        document.body.dataset.frames = String(frames);
        showMessage('');
        if (meta && meta.title) document.title = meta.title;
        layout();
    }

    function missing(text) {
        canvas.width = 0;
        canvas.height = 0;
        showMessage(text || 'Nothing to show.');
    }

    window.lrdOutput = {
        present: present,
        missing: missing,
        params: {
            canvas: params.get('canvas') || '',
            view: params.get('view') || 'pixel-map',
            scale: scaleMode
        }
    };

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

    if (!attach()) {
        showMessage('Open this from View › Output to Display in the designer window.');
    }

    // The designer window closing takes its outputs with it.
    setInterval(function () {
        if (!opener()) window.close();
    }, 1000);

    // ---- full screen ------------------------------------------------------
    function isFullscreen() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement);
    }
    function enterFullscreen() {
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
        if (isFullscreen() && Date.now() - fullscreenSince > 700) exitFullscreen();
    });
    document.addEventListener('keydown', function (e) {
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
