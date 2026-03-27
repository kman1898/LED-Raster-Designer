# -*- mode: python ; coding: utf-8 -*-
# LED Raster Designer - PyInstaller spec file
# Build with: python3 -m PyInstaller led_raster_designer.spec
#
# macOS:   produces LED Raster Designer.app with menu bar icon
# Windows: produces LED Raster Designer.exe with system tray

import os
import sys

import certifi

block_cipher = None
BASE_DIR = os.path.abspath('.')
IS_MAC = sys.platform == 'darwin'

# macOS uses rumps menu bar launcher; Windows uses pystray system tray; Linux uses app.py directly
if IS_MAC:
    entry_script = 'launcher_mac.py'
elif sys.platform == 'win32':
    entry_script = 'launcher_pc.py'
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
        (certifi.where(), 'certifi'),
    ],
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
    ] + (['rumps'] if IS_MAC else [])
      + (['pystray', 'pystray._win32'] if sys.platform == 'win32' else []),
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
    icon=None,
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
        icon=None,
        bundle_identifier='com.ledrasterdesigner.app',
        info_plist={
            'CFBundleName': 'LED Raster Designer',
            'CFBundleDisplayName': 'LED Raster Designer',
            'CFBundleShortVersionString': '0.7.5.8',
            'CFBundleVersion': '0.7.5.8',
            'NSHighResolutionCapable': True,
            'LSUIElement': True,  # Menu bar only — no Dock icon
        },
    )
