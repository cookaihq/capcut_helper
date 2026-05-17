import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.exceptions import TaskNotFound
from app.core.tasks import registry

logger = logging.getLogger(__name__)
router = APIRouter()

# SSE 空闲 ping 间隔：超过这个时间没真实事件就发一行注释（: ping\n\n），
# 让代理/浏览器不会因为长时间无数据而 idle-timeout 关连接。
_IDLE_PING_INTERVAL_S = 15.0


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


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request):
    """SSE 推送任务实时进度。订阅当前 task 的事件流，task done/failed 后关闭。

    协议：
    - Content-Type: text/event-stream
    - 每条事件：`event: <name>\\ndata: <json>\\n\\n`
    - event 取值：progress（status / subtask 状态变化）、done（任务结束）
    - 任务结束（done/failed）后服务端主动关闭连接
    - 空闲 15s 发一行注释 `: ping\\n\\n` 防止代理/浏览器超时

    客户端示例（浏览器 EventSource）：
        const es = new EventSource(`/api/v1/tasks/${id}/stream`)
        es.addEventListener('progress', (e) => render(JSON.parse(e.data)))
        es.addEventListener('done',     (e) => { es.close(); ... })
    """
    if registry.get(task_id) is None:
        raise TaskNotFound(f"任务不存在: {task_id}")

    async def event_generator():
        """客户端断开由 StreamingResponse 取消本 generator 自然触发；不要用
        request.is_disconnected()，它和项目里的 BaseHTTPMiddleware（snapshot）
        组合时会报 'Unexpected message received: http.request'（starlette 已知
        边界）。yield 抛出 CancelledError 时 finally 仍跑 unsubscribe。"""
        queue = registry.subscribe(task_id)
        try:
            while True:
                try:
                    event_type, data = await asyncio.wait_for(
                        queue.get(), timeout=_IDLE_PING_INTERVAL_S,
                    )
                except asyncio.TimeoutError:
                    # 心跳：服务端→客户端的 idle 保活
                    yield ": ping\n\n"
                    continue

                payload = json.dumps(data, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {payload}\n\n"

                if event_type == "done":
                    return
        finally:
            registry.unsubscribe(task_id, queue)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # nginx / 反代禁缓冲；本地没代理也无害
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
