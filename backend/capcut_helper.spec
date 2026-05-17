# -*- mode: python ; coding: utf-8 -*-
"""capcut_helper PyInstaller spec —— 产 macOS arm64 .app bundle。

用法（一般通过 scripts/build_mac.sh 调起）：
    cd capcut_helper/backend
    uv run pyinstaller --clean --noconfirm \
        --distpath=../dist --workpath=../build \
        capcut_helper.spec

前置：frontend/dist 必须先用 `npm run build` 构建好（build_mac.sh 已包含）。
"""

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

# 单一版本号来源：app/__init__.py::__version__
_init_text = (Path(SPECPATH) / "app" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _init_text).group(1)

# pywebview Mac 后端 hidden imports + 数据文件一次性收齐
pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all("webview")
# pyJianYingDraft 自带的模板等资源（如 DRAFT_META_TEMPLATE）
jianying_datas = collect_data_files("pyJianYingDraft")


a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries,
    datas=[
        # (源路径相对 spec 所在目录, bundle 内目标路径)
        ("../frontend/dist", "frontend/dist"),
        # 状态栏 template 图：运行时 _tray_macos._resource_path 在 _MEIPASS/backend/assets 找
        ("assets/tray_icon_template.png", "backend/assets"),
        ("assets/tray_icon_template@2x.png", "backend/assets"),
        # Windows 托盘图（_tray_windows._resource_path 同款查找）+ EXE 图标资源
        ("assets/tray_icon.png", "backend/assets"),
        ("assets/icon.ico", "backend/assets"),
        *pywebview_datas,
        *jianying_datas,
    ],
    hiddenimports=pywebview_hiddenimports + ["AppKit"],
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
    console=False,            # GUI 应用，不带终端
    disable_windowed_traceback=False,
    target_arch=None,         # 跟随当前 host 架构（M 系列 Mac 上为 arm64）
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico" if sys.platform == "win32" else None,
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

app = BUNDLE(
    coll,
    name="capcut_helper.app",
    icon="assets/icon.icns",
    bundle_identifier="com.cookaihq.capcut_helper",
    info_plist={
        "CFBundleName": "capcut_helper",
        "CFBundleDisplayName": "capcut_helper",
        "CFBundleIdentifier": "com.cookaihq.capcut_helper",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        # 注册 capcut-helper:// URL Scheme，让外部链接（如调用方网页里的
        # <a href="capcut-helper://trust?origin=...">) 能唤起本 app 并派发
        # Apple Event 给 _url_scheme_macos._URLHandler 处理。
        "CFBundleURLTypes": [
            {
                "CFBundleURLName": "com.cookaihq.capcut_helper.trust",
                "CFBundleURLSchemes": ["capcut-helper"],
                "CFBundleTypeRole": "Viewer",
            },
        ],
    },
)
