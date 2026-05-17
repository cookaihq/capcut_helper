"""系统级控制接口。

当前只有 POST /system/restart：spawn 一个新实例后退出当前进程，让设置页
「保存并重启生效」按钮能让 port_range 等启动期才读的配置真正生效。

设计要点：
1. 响应必须先写回前端再退出，否则前端拿到的是 connection reset。所以走
   FastAPI BackgroundTasks，路由直接返回 200，sleep 半秒后再 spawn + 自杀。
2. 不走 on_quit 的优雅 teardown：那条路径依赖 pywebview 主线程调度
   window.destroy()，后台任务跨线程调用并不稳；直接 os._exit 让 OS 回收，
   新实例会接管托盘图标。
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks

from app.core.restart import spawn_new_instance

logger = logging.getLogger(__name__)

router = APIRouter()

_RESPONSE_GRACE_SECONDS = 0.5


def _restart_now() -> None:
    time.sleep(_RESPONSE_GRACE_SECONDS)
    try:
        spawn_new_instance()
    except Exception:  # noqa: BLE001 — 拉新进程失败也要退当前进程吗？不退，留给用户排查
        logger.exception("spawn 新实例失败，放弃重启")
        return
    logger.info("新实例已 spawn，当前进程退出")
    os._exit(0)


@router.post("/system/restart")
async def restart(background_tasks: BackgroundTasks):
    """触发重启：立即返回 200，后台 spawn 新实例并 os._exit。"""
    background_tasks.add_task(_restart_now)
    return {"code": 0, "message": "ok", "data": None}
