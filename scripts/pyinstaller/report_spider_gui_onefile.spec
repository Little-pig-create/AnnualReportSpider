# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project_root = Path.cwd().resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app_metadata import APP_ICON_DIRNAME, APP_ICON_ICO_FILENAME, APP_ICON_PNG_FILENAME

icon_path = project_root / APP_ICON_DIRNAME / APP_ICON_ICO_FILENAME
icon_png_path = project_root / APP_ICON_DIRNAME / APP_ICON_PNG_FILENAME
version_info_path = project_root / "build" / "version_info.txt"

datas = [
    (str(project_root / "README.md"), "."),
    (str(project_root / "webui" / "dist"), "webui/dist"),
    (str(icon_path), APP_ICON_DIRNAME),
    (str(icon_png_path), APP_ICON_DIRNAME),
]

datas += collect_data_files("webview", subdir="lib")
datas += collect_data_files("webview", subdir="js")

binaries = collect_dynamic_libs("webview")

hiddenimports = [
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.mshtml",
    "pythonnet",
    "clr",
]

excludes = [
    "pandas",
    "scipy",
    "numba",
    "openpyxl",
    "lxml",
]

a = Analysis(
    [str(project_root / "webview_desktop.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="AnnualReportSpiderGUI",
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
    icon=str(icon_path),
    version=str(version_info_path),
)
