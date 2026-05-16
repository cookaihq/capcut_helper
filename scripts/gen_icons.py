#!/usr/bin/env python3
"""从 backend/assets/icon.icns 派生 Windows .ico / 托盘 PNG / favicon。

用法（开发者每次更换 icon.icns 后手动跑一次）：
    python scripts/gen_icons.py

产物：
    backend/assets/icon.ico          (16/32/48/64/128/256 多尺寸，给 PyInstaller + Inno Setup)
    backend/assets/tray_icon.png     (64x64 RGBA，给 pystray Windows 托盘)
    frontend/public/favicon.ico       (16/32 多尺寸，给 HTML <link rel="icon">)

依赖：Pillow（Windows 上是项目运行时依赖；Mac dev 上需手动 pip install --user Pillow）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
ICNS_SRC = REPO_ROOT / "backend" / "assets" / "icon.icns"
ICO_OUT = REPO_ROOT / "backend" / "assets" / "icon.ico"
TRAY_OUT = REPO_ROOT / "backend" / "assets" / "tray_icon.png"
FAVICON_OUT = REPO_ROOT / "frontend" / "public" / "favicon.ico"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
FAVICON_SIZES = [(16, 16), (32, 32)]
TRAY_SIZE = (64, 64)


def main() -> int:
    if not ICNS_SRC.is_file():
        print(f"missing icon.icns at {ICNS_SRC}", file=sys.stderr)
        return 1

    # icns 默认 frame 就是 1024×1024 RGBA（已验证），直接用
    master = Image.open(ICNS_SRC).convert("RGBA")

    # .ico 多尺寸：Pillow 内部按 sizes 列表逐档 LANCZOS 重采样后打包
    master.save(ICO_OUT, format="ICO", sizes=ICO_SIZES)
    print(f"wrote {ICO_OUT}")

    # 托盘 PNG：单尺寸 64×64，pystray 在 Windows 上会自适应任务栏 DPI
    master.resize(TRAY_SIZE, Image.LANCZOS).save(TRAY_OUT, format="PNG")
    print(f"wrote {TRAY_OUT}")

    # favicon：浏览器只用 16/32 两档
    FAVICON_OUT.parent.mkdir(parents=True, exist_ok=True)
    master.save(FAVICON_OUT, format="ICO", sizes=FAVICON_SIZES)
    print(f"wrote {FAVICON_OUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
