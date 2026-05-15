# -*- mode: python ; coding: utf-8 -*-
"""capcut_helper PyInstaller spec —— 产 macOS arm64 .app bundle。

用法（一般通过 scripts/build_mac.sh 调起）：
    cd capcut_helper/backend
    uv run pyinstaller --clean --noconfirm \
        --distpath=../dist --workpath=../build \
        capcut_helper.spec

前置：frontend/dist 必须先用 `npm run build` 构建好（build_mac.sh 已包含）。
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

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
    icon=None,
    bundle_identifier="com.cookaihq.capcut_helper",
    info_plist={
        "CFBundleName": "capcut_helper",
        "CFBundleDisplayName": "capcut_helper",
        "CFBundleIdentifier": "com.cookaihq.capcut_helper",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
