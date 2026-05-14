import json

import httpx
import respx

from app.core import config as config_mod
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services.draft_service import run_draft_task
from tests.conftest import SAMPLE1_DURATION, SAMPLE2_DURATION


@respx.mock
async def test_full_draft_creation_flow(tmp_path, monkeypatch, fixture_video_1, fixture_video_2):
    # 真实跑：mock 掉 HTTP 下载，其余（建草稿、填片段、保存）都用真实 pyJianYingDraft
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(draft_root)))

    respx.get("https://x/v1.mp4").mock(
        return_value=httpx.Response(200, content=fixture_video_1.read_bytes())
    )
    respx.get("https://x/v2.mp4").mock(
        return_value=httpx.Response(200, content=fixture_video_2.read_bytes())
    )

    spec = TimelineSpec.model_validate(
        {
            "draft_name": "e2e_draft",
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

    task = registry.create("e2e_draft")
    await run_draft_task(task.id, spec)

    state = registry.get(task.id)
    assert state.status == "done", state.error
    assert state.progress == 100

    draft_dir = draft_root / "e2e_draft"
    # 素材已下载进草稿文件夹（自包含）
    assert len(list(draft_dir.glob("*.mp4"))) == 2

    content = json.loads((draft_dir / "draft_content.json").read_text("utf-8"))
    assert content["canvas_config"]["width"] == 1920
    assert len(content["tracks"]) == 1
    assert len(content["tracks"][0]["segments"]) == 2
    # 素材路径指向草稿文件夹内的副本
    for material in content["materials"]["videos"]:
        assert str(draft_dir) in material["path"]
