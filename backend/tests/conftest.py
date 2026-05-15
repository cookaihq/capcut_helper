from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_snapshot_dir(tmp_path, monkeypatch):
    """所有测试默认把请求快照重定向到 tmp_path，避免污染真实用户日志目录。
    需要自己控制 SNAPSHOT_DIR 的测试可以再次 monkeypatch 覆盖。"""
    from app.core import request_snapshot
    monkeypatch.setattr(request_snapshot, "SNAPSHOT_DIR", tmp_path / "_snapshots")

# 两个 fixture 视频的已知时长（微秒），实测自仓库已有素材
SAMPLE1_DURATION = 9160000
SAMPLE2_DURATION = 33320000


@pytest.fixture
def fixture_video_1() -> Path:
    return _FIXTURE_DIR / "sample1.mp4"


@pytest.fixture
def fixture_video_2() -> Path:
    return _FIXTURE_DIR / "sample2.mp4"
