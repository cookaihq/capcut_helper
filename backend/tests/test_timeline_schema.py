import pytest
from pydantic import ValidationError

from app.schemas.timeline import TimelineSpec


def _video_spec():
    return {
        "draft_name": "测试草稿",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {"url": "https://x/a.mp4", "type": "video", "filename": "a.mp4"},
                        "timeline": {"start": 0, "duration": 9160000},
                    }
                ],
            }
        ],
    }


def test_valid_video_spec_parses():
    spec = TimelineSpec.model_validate(_video_spec())
    assert spec.draft_name == "测试草稿"
    assert spec.allow_replace is False
    assert spec.tracks[0].segments[0].material.url == "https://x/a.mp4"


def test_material_urls_dedups_by_url():
    data = _video_spec()
    seg = data["tracks"][0]["segments"][0]
    data["tracks"][0]["segments"].append(dict(seg))  # 同一个 URL 用两次
    spec = TimelineSpec.model_validate(data)
    assert len(spec.material_urls()) == 1


def test_video_segment_without_material_rejected():
    data = _video_spec()
    del data["tracks"][0]["segments"][0]["material"]
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)


def test_text_segment_without_text_rejected():
    data = _video_spec()
    data["tracks"][0]["type"] = "text"
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)


def test_draft_name_with_path_separator_rejected():
    data = _video_spec()
    data["draft_name"] = "bad/name"
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)
