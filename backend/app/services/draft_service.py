import asyncio
from pathlib import Path

from app.core.config import load_config
from app.core.exceptions import DraftRootNotConfigured
from app.core.tasks import registry
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from app.services.downloader import download_materials


async def run_draft_task(task_id: str, spec: TimelineSpec) -> None:
    """后台任务主体：建空草稿 → 下素材进文件夹 → 填轨道片段 → 保存。
    全程更新 task registry 的状态与进度。"""
    try:
        cfg = load_config()
        if not cfg.draft_root or not Path(cfg.draft_root).is_dir():
            raise DraftRootNotConfigured("剪映草稿根目录未配置或不存在")

        registry.update(task_id, status="building", progress=10)
        # pyJianYingDraft 是同步阻塞库，放线程里跑，避免卡事件循环
        script, draft_dir = await asyncio.to_thread(
            builder.create_empty_draft, cfg.draft_root, spec
        )

        registry.update(task_id, status="downloading", progress=30)
        material_paths = await download_materials(spec.material_urls(), draft_dir)

        registry.update(task_id, status="building", progress=70)
        await asyncio.to_thread(builder.populate_draft, script, spec, material_paths)
        await asyncio.to_thread(builder.save_draft, script)

        registry.update(task_id, status="done", progress=100, result=str(draft_dir))
    except Exception as exc:  # noqa: BLE001 — 任何失败都落到 task 状态上报
        registry.update(task_id, status="failed", error=str(exc))


def dispatch_draft_task(spec: TimelineSpec) -> str:
    """创建 task 并在后台启动 run_draft_task，立即返回 task_id。
    必须在有运行中事件循环的上下文调用（FastAPI async 路由内）。"""
    state = registry.create()
    asyncio.create_task(run_draft_task(state.id, spec))
    return state.id
