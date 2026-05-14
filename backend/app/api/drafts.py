import asyncio

from fastapi import APIRouter

from app.core.config import load_config
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services.draft_service import run_draft_task
from pyJianYingDraft import DraftFolder

router = APIRouter()


@router.post("/drafts")
async def create_draft(spec: TimelineSpec):
    state = registry.create()
    asyncio.create_task(run_draft_task(state.id, spec))
    return {"code": 0, "message": "ok", "data": {"task_id": state.id}}


@router.get("/drafts")
async def list_drafts():
    cfg = load_config()
    if not cfg.draft_root:
        return {"code": 0, "message": "ok", "data": []}
    names = DraftFolder(cfg.draft_root).list_drafts()
    return {"code": 0, "message": "ok", "data": names}
