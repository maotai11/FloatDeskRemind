# -*- mode: python ; coding: utf-8 -*-
# FloatDesk Remind - PyInstaller spec file

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
        'win32gui',
        'pywintypes',
        'winreg',
        'src.data.migrations.v001_initial',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FloatDeskRemind',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['Qt6*.dll', 'PySide6/*.pyd', 'python*.dll', 'vcruntime*.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    onefile=True,
)
