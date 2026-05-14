from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).parent / "fixtures"

# 两个 fixture 视频的已知时长（微秒），实测自仓库已有素材
SAMPLE1_DURATION = 9160000
SAMPLE2_DURATION = 33320000


@pytest.fixture
def fixture_video_1() -> Path:
    return _FIXTURE_DIR / "sample1.mp4"


@pytest.fixture
def fixture_video_2() -> Path:
    return _FIXTURE_DIR / "sample2.mp4"
