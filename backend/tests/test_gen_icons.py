"""scripts/gen_icons.py 回归测试。

策略：在 tmp_path 复制 icns，运行脚本，断言产物文件存在且格式 / 尺寸符合预期。
不调脚本内部函数，只验外部契约（命令行可调、产物路径稳定）。

跨平台：脚本只依赖 Pillow，无平台 syscall，Linux / Mac / Win 都能跑。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ICNS_SRC = REPO_ROOT / "backend" / "assets" / "icon.icns"
SCRIPT = REPO_ROOT / "scripts" / "gen_icons.py"


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """复制 icns + 脚本到 tmp_path 模拟一个独立仓库，避免污染真实派生产物。"""
    (tmp_path / "backend" / "assets").mkdir(parents=True)
    (tmp_path / "frontend" / "public").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(ICNS_SRC, tmp_path / "backend" / "assets" / "icon.icns")
    shutil.copy(SCRIPT, tmp_path / "scripts" / "gen_icons.py")
    return tmp_path


def test_script_generates_three_artifacts(fake_repo: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "gen_icons.py")],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert (fake_repo / "backend" / "assets" / "icon.ico").is_file()
    assert (fake_repo / "backend" / "assets" / "tray_icon.png").is_file()
    assert (fake_repo / "frontend" / "public" / "favicon.ico").is_file()


def test_icon_ico_has_multiple_sizes(fake_repo: Path) -> None:
    subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "gen_icons.py")],
        cwd=fake_repo, check=True,
    )
    img = Image.open(fake_repo / "backend" / "assets" / "icon.ico")
    sizes = img.info.get("sizes") or {img.size}
    # 至少覆盖 16/32/256（Windows 资源管理器在小/大图标视图各取一档）
    expected = {(16, 16), (32, 32), (256, 256)}
    assert expected.issubset(set(sizes)), f"missing sizes; got {sizes}"


def test_tray_icon_png_is_64x64_rgba(fake_repo: Path) -> None:
    subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "gen_icons.py")],
        cwd=fake_repo, check=True,
    )
    img = Image.open(fake_repo / "backend" / "assets" / "tray_icon.png")
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_favicon_has_16_and_32(fake_repo: Path) -> None:
    subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "gen_icons.py")],
        cwd=fake_repo, check=True,
    )
    img = Image.open(fake_repo / "frontend" / "public" / "favicon.ico")
    sizes = img.info.get("sizes") or {img.size}
    assert {(16, 16), (32, 32)}.issubset(set(sizes))


def test_missing_icns_exits_nonzero(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "gen_icons.py")
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts" / "gen_icons.py")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "icon.icns" in (result.stderr + result.stdout)
