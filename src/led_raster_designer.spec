# -*- mode: python ; coding: utf-8 -*-
# LED Raster Designer - PyInstaller spec file
# Build with: python3 -m PyInstaller led_raster_designer.spec
#
# macOS:   produces LED Raster Designer.app opening the launcher window
# Windows: produces LED Raster Designer.exe opening the launcher window

import os
import subprocess
import sys

import certifi
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
BASE_DIR = os.path.abspath('.')
IS_MAC = sys.platform == 'darwin'

# macOS/Windows launch the branded splash/control window (pywebview); the old
# tray (launcher_pc.py) and menu-bar (launcher_mac.py) launchers remain in the
# repo as fallbacks. Linux uses app.py directly.
if IS_MAC or sys.platform == 'win32':
    entry_script = 'launcher_window.py'
else:
    entry_script = 'app.py'

# The game controller reader (native_pad_reader.py) needs SDL itself and
# nothing else pygame bundles: its image, font, sound and MIDI libraries
# stay out, with the pygame modules that load them. pygame imports each of
# those modules inside a try, so in the app they are simply missing.
PYGAME_UNUSED = [
    'pygame.font', 'pygame.sysfont', 'pygame.ftfont', 'pygame.freetype', 'pygame._freetype',
    'pygame.mixer', 'pygame.mixer_music', 'pygame.sndarray', 'pygame.imageext',
    'pygame.midi', 'pygame.pypm', 'pygame.camera', 'pygame._camera',
    'pygame._camera_opencv', 'pygame._camera_vidcapture',
    'pygame.examples', 'pygame.tests', 'pygame.docs',
]


def _linked_names(path):
    """The file names of the libraries a binary links to, lowercased, or
    None when they cannot be read (macOS: otool -L; Windows: its import
    table, with pefile, which PyInstaller brings on Windows)."""
    try:
        if sys.platform == 'darwin':
            out = subprocess.run(['otool', '-L', path], capture_output=True, text=True,
                                 check=True).stdout
            return {os.path.basename(line.strip().split(' (')[0]).lower()
                    for line in out.splitlines()[1:] if line.strip()}
        if sys.platform == 'win32':
            import pefile
            pe = pefile.PE(path, fast_load=True)
            try:
                pe.parse_data_directories(directories=[
                    pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                    pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
                return {e.dll.decode('ascii', 'replace').lower()
                        for attr in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                        for e in getattr(pe, attr, [])}
            finally:
                pe.close()
        return set()
    except Exception:
        return None


def pygame_sdl_only(binaries, linked=None):
    """The bundle's binaries without the libraries pygame ships beside SDL
    that nothing kept needs. SDL2.dll (Windows) or libSDL2-2.0.0.dylib
    (macOS) stays, and so does every pygame library that SDL or a pygame
    module still in the bundle links to, all the way down; the rest
    (image, font, sound, MIDI) goes. pygame's own hook collects every
    library in its folder on Windows. A library whose links cannot be read
    keeps them all: a bigger app, never a reader that cannot load."""
    linked = linked or _linked_names
    libs, keep = {}, []
    for entry in binaries:
        dest, src = entry[0], entry[1]
        name = dest.replace('\\', '/').rsplit('/', 1)[-1].lower()
        where = (src or '').replace('\\', '/').lower()
        if '/pygame/' in where and name.endswith(('.dll', '.dylib')):
            libs.setdefault(name, []).append(entry)
        else:
            keep.append(entry)
    need = {n for n in libs if n.startswith(('sdl2.dll', 'libsdl2-2.0'))}
    todo = [e[1] for e in keep if '/pygame/' in (e[1] or '').replace('\\', '/').lower()]
    todo += [e[1] for n in need for e in libs[n]]
    seen = set()
    while todo:
        src = todo.pop()
        if src in seen:
            continue
        seen.add(src)
        names = linked(src)
        if names is None:
            print(f'pygame_sdl_only: cannot read the links of {src}; keeping all of pygame\'s libraries')
            return list(binaries)
        for n in (names & libs.keys()) - need:
            need.add(n)
            todo += [e[1] for e in libs[n]]
    print('pygame_sdl_only: kept ' + ', '.join(sorted(need)) + '; left out '
          + (', '.join(sorted(libs.keys() - need)) or 'nothing'))
    return keep + [e for n in sorted(need) for e in libs[n]]


# pygame's hook also bundles its default font and its window icon: the
# reader opens no window and draws no text, so they stay out.
def pygame_unused_datas(datas):
    def unused(dest):
        folder, _, name = dest.replace('\\', '/').lower().rpartition('/')
        return folder == 'pygame' and (name == 'freesansbold.ttf' or name.startswith('pygame_icon'))
    return [e for e in datas if not unused(e[0])]


a = Analysis(
    [entry_script, 'app.py', 'launcher_settings.py'],  # Analyze launcher, settings, AND app.py
    pathex=[BASE_DIR],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('VERSION.txt', '.'),
        (os.path.join('..', 'LICENSE'), '.'),  # repo-root LICENSE, served by /api/license (Help > License)
        (os.path.join('..', 'THIRD-PARTY-NOTICES'), '.'),  # served by /api/third-party-notices (Help > License)
        ('launcher_window.html', '.'),  # splash/control window UI
        (certifi.where(), 'certifi'),
    ] + ([('BUILD_TAG.txt', '.')] if os.path.exists(os.path.join(BASE_DIR, 'BUILD_TAG.txt')) else [])  # beta builds only (release.yml)
      + collect_data_files('webview'),  # pywebview bridge/runtime data files
    hiddenimports=[
        'flask',
        'flask_socketio',
        'engineio.async_drivers.threading',
        'PIL',
        'PIL.Image',
        'numpy',
        'pytoshop',
        'pytoshop.layers',
        'pytoshop.enums',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.pdfgen',
        'reportlab.pdfgen.canvas',
        'openpyxl',
        'openpyxl.worksheet.formula',
        'openpyxl.workbook.defined_name',
        'et_xmlfile',
    # Bundle the COMPLETE pywebview package (all submodules + data files):
    # its JS bridge lives in submodules PyInstaller doesn't auto-detect, and
    # a frozen Windows build rendered the window fine but window.pywebview
    # never appeared - the whole js_api was dead.
    ] + collect_submodules('webview')
      # The game controller reader (native_pad_reader.py): the app runs its
      # own executable with --pad-reader, and the reader loads pygame (SDL)
      # only there. pygame's own PyInstaller hook brings its SDL libraries.
      + ['native_pad', 'native_pad_reader', 'pygame', 'pygame._sdl2', 'pygame._sdl2.controller']
      + (['launcher_mac', 'AppKit', 'objc', 'PyObjCTools.AppHelper'] if IS_MAC else [])
      + (['launcher_pc', 'pystray', 'pystray._win32']
         if sys.platform == 'win32' else []),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=PYGAME_UNUSED,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = pygame_sdl_only(a.binaries)
a.datas = pygame_unused_datas(a.datas)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LED Raster Designer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=not (IS_MAC or sys.platform == 'win32'),  # No console on macOS/Windows (tray handles it)
    icon=('icon.ico' if sys.platform == 'win32' else None),  # Windows .exe icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LED Raster Designer',
)

# macOS: wrap into a proper .app bundle you can double-click
if IS_MAC:
    app = BUNDLE(
        coll,
        name='LED Raster Designer.app',
        icon='icon.icns',
        bundle_identifier='com.ledrasterdesigner.app',
        info_plist={
            'CFBundleName': 'LED Raster Designer',
            'CFBundleDisplayName': 'LED Raster Designer',
            'CFBundleShortVersionString': '1.7.0',
            'CFBundleVersion': '1.7.0',
            'NSHighResolutionCapable': True,
            # Menu-bar app, no Dock icon (same as the pre-window launcher):
            # the launcher window hides to the menu-bar status item, which is
            # also how the window comes back. If the frozen window has focus
            # problems as an agent app, flip this to False (Dock icon).
            'LSUIElement': True,
        },
    )
