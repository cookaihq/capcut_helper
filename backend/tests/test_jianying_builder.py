import json
import shutil

import pytest

from app.core.exceptions import DraftNameConflict
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from tests.conftest import SAMPLE1_DURATION, SAMPLE2_DURATION


def _two_video_spec(allow_replace=False):
    return TimelineSpec.model_validate(
        {
            "draft_name": "builder_test",
            "allow_replace": allow_replace,
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/v1.mp4", "type": "video", "filename": "v1.mp4"},
                            "timeline": {"start": 0, "duration": SAMPLE1_DURATION},
                        },
                        {
                            "material": {"url": "https://x/v2.mp4", "type": "video", "filename": "v2.mp4"},
                            "timeline": {"start": SAMPLE1_DURATION, "duration": SAMPLE2_DURATION},
                        },
                    ],
                }
            ],
        }
    )


def test_create_populate_save_writes_valid_draft(tmp_path, fixture_video_1, fixture_video_2):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec()

    script, draft_dir = builder.create_empty_draft(str(draft_root), spec)
    assert draft_dir == draft_root / "builder_test"
    assert draft_dir.is_dir()

    # 模拟「下素材进草稿文件夹」：把 fixture 复制进去
    v1 = draft_dir / "v1.mp4"
    v2 = draft_dir / "v2.mp4"
    shutil.copy(fixture_video_1, v1)
    shutil.copy(fixture_video_2, v2)
    material_paths = {"https://x/v1.mp4": v1, "https://x/v2.mp4": v2}

    builder.populate_draft(script, spec, material_paths)
    builder.save_draft(script)

    content = json.loads((draft_dir / "draft_content.json").read_text("utf-8"))
    assert content["canvas_config"]["width"] == 1920
    assert content["canvas_config"]["height"] == 1080
    assert len(content["tracks"]) == 1
    assert len(content["tracks"][0]["segments"]) == 2
    assert content["tracks"][0]["segments"][0]["target_timerange"] == {
        "start": 0,
        "duration": SAMPLE1_DURATION,
    }


def test_create_empty_draft_raises_conflict_when_exists(tmp_path):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec(allow_replace=False)

    builder.create_empty_draft(str(draft_root), spec)  # 第一次成功
    with pytest.raises(DraftNameConflict):
        builder.create_empty_draft(str(draft_root), spec)  # 第二次重名且不允许覆盖
