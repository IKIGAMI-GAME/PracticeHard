# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['practice_hard.py'],
    pathex=[],
    binaries=[('/opt/homebrew/bin/ffmpeg', '.'), ('/opt/homebrew/bin/ffprobe', '.')],
    datas=[('practice_hard.icns', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PracticeHard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['practice_hard.ico'],
)
app = BUNDLE(
    exe,
    name='PracticeHard.app',
    icon='practice_hard.ico',
    bundle_identifier=None,
)
