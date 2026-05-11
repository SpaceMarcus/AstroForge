# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


# RocketCEA opens some package files directly from disk at runtime
# (for example `_version.py` and several thermo/input libraries).
# Those files therefore need to be bundled as real extracted data files.
datas = collect_data_files("matplotlib") + collect_data_files(
    "rocketcea",
    include_py_files=True,
)
binaries = collect_dynamic_libs("rocketcea")
hiddenimports = collect_submodules(
    "rocketcea",
    filter=lambda name: ".examples" not in name and ".tests" not in name,
)

a = Analysis(
    ["gui_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "matplotlib.backends.backend_tkagg",
        "PIL._tkinter_finder",
    ]
    + hiddenimports,
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
    name="AstraForge",
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
)
