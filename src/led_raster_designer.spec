# -*- mode: python ; coding: utf-8 -*-
# LED Raster Designer - PyInstaller spec file
# Build with: python3 -m PyInstaller led_raster_designer.spec
#
# macOS:   produces LED Raster Designer.app opening the launcher window
# Windows: produces LED Raster Designer.exe opening the launcher window

import os
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

a = Analysis(
    [entry_script, 'app.py', 'launcher_settings.py'],  # Analyze launcher, settings, AND app.py
    pathex=[BASE_DIR],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('VERSION.txt', '.'),
        ('launcher_window.html', '.'),  # splash/control window UI
        (certifi.where(), 'certifi'),
    ] + collect_data_files('webview'),  # pywebview bridge/runtime data files
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
    # Bundle the COMPLETE pywebview package (all submodules + data files):
    # its JS bridge lives in submodules PyInstaller doesn't auto-detect, and
    # a frozen Windows build rendered the window fine but window.pywebview
    # never appeared - the whole js_api was dead.
    ] + collect_submodules('webview')
      + (['launcher_mac', 'AppKit', 'objc', 'PyObjCTools.AppHelper'] if IS_MAC else [])
      + (['launcher_pc', 'pystray', 'pystray._win32']
         if sys.platform == 'win32' else []),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

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
            'CFBundleShortVersionString': '0.10.5',
            'CFBundleVersion': '0.10.5',
            'NSHighResolutionCapable': True,
            # Menu-bar app, no Dock icon (same as the pre-window launcher):
            # the launcher window hides to the menu-bar status item, which is
            # also how the window comes back. If the frozen window has focus
            # problems as an agent app, flip this to False (Dock icon).
            'LSUIElement': True,
        },
    )
