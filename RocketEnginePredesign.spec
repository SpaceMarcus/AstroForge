# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)
from pathlib import Path

from pygasflow.nozzles import rao_parabola_angles


# RocketCEA opens some package files directly from disk at runtime
# (for example `_version.py` and several thermo/input libraries).
# Those files therefore need to be bundled as real extracted data files.
datas = collect_data_files("matplotlib") + collect_data_files(
    "rocketcea",
    include_py_files=True,
)
# Rao_Parabola_Angles reads digitized chart files directly from disk at runtime.
# Bundle that chart-data directory explicitly so the EXE can resolve it from _MEIPASS.
_rao_data_dir = Path(rao_parabola_angles.__file__).resolve().parent / "plot-4-16-data"
datas += [
    (str(data_path), "pygasflow/nozzles/plot-4-16-data")
    for data_path in _rao_data_dir.glob("*")
    if data_path.is_file()
]
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
        "pygasflow.nozzles.rao_parabola_angles",
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
