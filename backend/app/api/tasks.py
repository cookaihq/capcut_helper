from fastapi import APIRouter

from app.core.exceptions import TaskNotFound
from app.core.tasks import registry

router = APIRouter()


@router.get("/tasks")
async def list_tasks():
    tasks = sorted(registry.list(), key=lambda t: t.created_at, reverse=True)
    return {"code": 0, "message": "ok", "data": [t.to_dict() for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    state = registry.get(task_id)
    if state is None:
        raise TaskNotFound(f"任务不存在: {task_id}")
    return {"code": 0, "message": "ok", "data": state.to_dict()}
