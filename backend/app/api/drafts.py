import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Request

from app.core.config import load_config
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services.draft_service import run_draft_task
from pyJianYingDraft import DraftFolder

router = APIRouter()

# 持有后台任务的强引用，防止 asyncio 在任务完成前把它当垃圾回收
_background_tasks: set[asyncio.Task] = set()


@router.post("/drafts")
async def create_draft(spec: TimelineSpec, request: Request):
    request.app.state.last_draft_request_at = time.time()
    state = registry.create(spec.draft_name)
    task = asyncio.create_task(run_draft_task(state.id, spec))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": state.id,
            # 调用方可立即用 EventSource 订阅这个 URL 拿实时进度
            # （包含每个素材的下载字节进度）；不订阅就用老方式 GET /tasks/{id}
            # 轮询，subtasks 字段同样有最新状态
            "stream_url": f"/api/v1/tasks/{state.id}/stream",
        },
    }


@router.get("/drafts")
async def list_drafts():
    cfg = load_config()
    if not cfg.draft_root or not Path(cfg.draft_root).is_dir():
        return {"code": 0, "message": "ok", "data": []}
    names = DraftFolder(cfg.draft_root).list_drafts()
    return {"code": 0, "message": "ok", "data": names}
