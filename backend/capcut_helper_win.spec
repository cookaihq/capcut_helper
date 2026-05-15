# -*- mode: python ; coding: utf-8 -*-
"""capcut_helper PyInstaller spec — 产 Windows x64 EXE + 资源目录。

用法（通过 scripts/build_win.ps1 调起）：
    cd capcut_helper/backend
    uv run pyinstaller --clean --noconfirm `
        --distpath=../dist --workpath=../build `
        capcut_helper_win.spec

前置：frontend/dist 必须先用 `npm run build` 构建好（build_win.ps1 已包含）。
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all("webview")
jianying_datas = collect_data_files("pyJianYingDraft")


a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries,
    datas=[
        ("../frontend/dist", "frontend/dist"),
        *pywebview_datas,
        *jianying_datas,
    ],
    hiddenimports=pywebview_hiddenimports + [
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="capcut_helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI 应用，不带终端窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="capcut_helper",
)
