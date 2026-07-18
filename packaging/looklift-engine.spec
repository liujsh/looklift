# -*- mode: python ; coding: utf-8 -*-
"""looklift 真实引擎 sidecar 的 PyInstaller onedir 配置。"""

from pathlib import Path

import pyvips
from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
site_packages = Path(pyvips.__file__).parent.parent
vips_binaries = [
    (str(site_packages / "_libvips.pyd"), "."),
    (str(site_packages / "libvips-42-*.dll"), "."),
]

a = Analysis(
    [str(project_root / "packaging" / "engine_sidecar.py")],
    pathex=[str(project_root)],
    binaries=vips_binaries,
    datas=collect_data_files("looklift"),
    hiddenimports=["_libvips"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="looklift-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name="looklift-engine",
)
