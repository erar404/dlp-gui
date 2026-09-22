# -*- mode: python ; coding: utf-8 -*-
#
# macOS build — produces dist/MD-Tools.app.
#
# ffmpeg is deliberately NOT bundled here (see download_deps.py): a
# copied Homebrew binary depends on Homebrew's own shared libraries,
# so it isn't portable the way a static Windows .exe is. The app
# finds/installs it via Homebrew at runtime instead.


a = Analysis(
    ['dlp-ui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('deps/yt-dlp',  '.'),
        ('qrcode.png',   '.'),
    ],
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
    [],
    exclude_binaries=True,
    name='MD-Tools',
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
    icon='icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='MD-Tools',
)

app = BUNDLE(
    coll,
    name='MD-Tools.app',
    icon='icon.icns',
    bundle_identifier='com.erar404.mdtools',
    info_plist={
        'CFBundleName': 'MD Tools',
        'CFBundleDisplayName': 'MD Tools',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.video',
    },
)
