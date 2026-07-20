# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\levyr\\RugWatch\\desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\levyr\\RugWatch\\rugwatch', 'rugwatch'), ('C:\\Users\\levyr\\RugWatch\\data', 'data'), ('C:\\Users\\levyr\\RugWatch\\RugCheck Documentation.md', '.')],
    hiddenimports=['rugwatch', 'rugwatch.db', 'rugwatch.config', 'rugwatch.cli', 'rugwatch.cloud_store', 'rugwatch.remote_wallets', 'rugwatch.http_util', 'rugwatch.alerts', 'rugwatch.ingest', 'rugwatch.ingest.scan_mint', 'rugwatch.monitor', 'rugwatch.monitor.launches', 'rugwatch.sources', 'rugwatch.sources.rugcheck', 'rugwatch.sources.pumpfun', 'rugwatch.sources.rpc', 'rugwatch.sources.solscan', 'certifi'],
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
    name='RugWatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RugWatch',
)
