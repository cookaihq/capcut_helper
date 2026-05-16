"""_tray_windows 图标加载回归测试。

仅在 Windows + pystray 可用时运行。验：
1. _resource_path() 返回的路径能 Image.open 成功（说明 gen_icons.py 产物存在且可读）
2. 没有 _make_placeholder_icon 函数残留（避免回退到白底占位）
"""
from __future__ import annotations

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

pytest.importorskip("pystray")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from app.native import _tray_windows  # noqa: E402


def test_resource_path_points_to_existing_tray_png() -> None:
    path = _tray_windows._resource_path("backend/assets/tray_icon.png")
    assert path.is_file(), f"tray icon missing at {path}"
    img = Image.open(path)
    assert img.size == (64, 64)


def test_placeholder_icon_function_is_gone() -> None:
    """确保 _make_placeholder_icon 已删除，不会被误调到。"""
    assert not hasattr(_tray_windows, "_make_placeholder_icon")
