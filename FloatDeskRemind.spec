# -*- mode: python ; coding: utf-8 -*-
# FloatDesk Remind - PyInstaller spec file
# onedir mode: no extraction delay on startup
#
# Migration modules are collected automatically via collect_submodules().
# When adding a new migration file (src/data/migrations/vNNN_*.py),
# no changes to this spec file are required.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('src/ui/styles/main.qss', 'src/ui/styles'),
    ],
    hiddenimports=[
        'win32api',
        'win32con',
        'pywintypes',
        'winreg',
        *collect_submodules('src.data.migrations'),
    ],
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
    name='FloatDeskRemind',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FloatDeskRemind',
)
