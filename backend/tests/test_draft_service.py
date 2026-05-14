import pytest

from app.core import config as config_mod
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services import draft_service


def _spec():
    return TimelineSpec.model_validate(
        {
            "draft_name": "svc_test",
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/a.mp4", "type": "video", "filename": "a.mp4"},
                            "timeline": {"start": 0, "duration": 1000000},
                        }
                    ],
                }
            ],
        }
    )


async def test_run_draft_task_success_path(tmp_path, monkeypatch):
    # 配置一个存在的草稿根目录
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(draft_root)))

    # 把 jianying 和下载器都换成假实现，只验证编排与进度
    draft_dir = draft_root / "svc_test"
    monkeypatch.setattr(
        draft_service.builder, "create_empty_draft",
        lambda root, spec: ("FAKE_SCRIPT", draft_dir),
    )
    async def _fake_download(materials, dest):
        return {m.url: dest / m.filename for m in materials}
    monkeypatch.setattr(draft_service, "download_materials", _fake_download)
    monkeypatch.setattr(draft_service.builder, "populate_draft", lambda *a, **k: None)
    monkeypatch.setattr(draft_service.builder, "save_draft", lambda *a, **k: None)

    task = registry.create()
    await draft_service.run_draft_task(task.id, _spec())

    state = registry.get(task.id)
    assert state.status == "done"
    assert state.progress == 100
    assert state.result == str(draft_dir)


async def test_run_draft_task_fails_when_draft_root_not_configured(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)  # 不写 config → draft_root 为 None

    task = registry.create()
    await draft_service.run_draft_task(task.id, _spec())

    state = registry.get(task.id)
    assert state.status == "failed"
    assert "草稿根目录" in state.error
