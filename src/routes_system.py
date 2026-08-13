"""
System / host-environment routes (first extracted blueprint).

These endpoints report on the machine the server runs on and have no coupling
to the project state, so they were the natural first piece to pull out of the
monolithic app.py during the backend modularization.
"""
import os
import sys
import threading

from flask import Blueprint, jsonify

system_bp = Blueprint('system', __name__)

# ── System fonts (enumerate fonts installed on this machine) ──
# The server runs locally with OS access, so it can read the user's installed
# fonts and hand the real family names to the UI. The browser (on the same
# machine) can then render any of them in canvas, no need to bundle fonts.
# Works on every browser (unlike the Chromium-only Local Font Access API).
_SYSTEM_FONTS = None
_SYSTEM_FONTS_LOCK = threading.Lock()


def _font_search_dirs():
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return ['/System/Library/Fonts',
                '/System/Library/Fonts/Supplemental',
                '/Library/Fonts',
                os.path.join(home, 'Library', 'Fonts')]
    if sys.platform == 'win32':
        dirs = [os.path.join(os.environ.get('WINDIR', r'C:\\Windows'), 'Fonts')]
        local = os.environ.get('LOCALAPPDATA')
        if local:
            dirs.append(os.path.join(local, 'Microsoft', 'Windows', 'Fonts'))
        return dirs
    return ['/usr/share/fonts', '/usr/local/share/fonts',
            os.path.join(home, '.fonts'),
            os.path.join(home, '.local', 'share', 'fonts')]


def _enumerate_system_fonts():
    """Return a sorted list of unique font family names installed on this
    machine. Family names come from each font's own name table (via Pillow),
    so they match what the browser uses to reference the font in CSS/canvas."""
    from PIL import ImageFont
    families = set()
    collection_exts = ('.ttc', '.otc')
    font_exts = ('.ttf', '.otf') + collection_exts
    for d in _font_search_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                low = fn.lower()
                if not low.endswith(font_exts):
                    continue
                path = os.path.join(root, fn)
                is_collection = low.endswith(collection_exts)
                idx = 0
                while idx < 64:
                    try:
                        face = ImageFont.truetype(path, 10, index=idx)
                        fam = (face.getname() or [None])[0]
                        if fam:
                            fam = fam.strip()
                        # Skip Apple/OS internal fonts (names start with a dot).
                        if fam and not fam.startswith('.'):
                            families.add(fam)
                    except Exception:
                        break
                    if not is_collection:
                        break
                    idx += 1
    return sorted(families, key=lambda s: s.lower())


def get_system_fonts():
    """Lazily enumerate + cache the installed font families (computed once)."""
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is not None:
        return _SYSTEM_FONTS
    with _SYSTEM_FONTS_LOCK:
        if _SYSTEM_FONTS is None:
            try:
                _SYSTEM_FONTS = _enumerate_system_fonts()
            except Exception as e:
                print(f'[LED Raster Designer] Font enumeration failed: {e}')
                _SYSTEM_FONTS = []
    return _SYSTEM_FONTS


@system_bp.route('/api/system-fonts', methods=['GET'])
def api_system_fonts():
    """Font families installed on the machine running the app."""
    return jsonify({'fonts': get_system_fonts()})
