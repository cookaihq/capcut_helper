import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.cors import HotReloadCORSMiddleware
from app.core.exceptions import register_exception_handlers
from app.core.request_snapshot import install_request_snapshot
from app.services.update_checker import check_for_update

logger = logging.getLogger(__name__)


def _resource_path(rel: str) -> Path:
    """资源文件路径解析：
    - 开发模式：从源码树解析（server.py 在 backend/app/，上跳两级到 capcut_helper/）
    - PyInstaller 冻结后：从 sys._MEIPASS 解析（PyInstaller 在运行时把打进 bundle 的
      data files 解压/映射到这个目录）
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parents[2] / rel


# 前端构建产物目录
_FRONTEND_DIST = _resource_path("frontend/dist")


async def _refresh_update_info(app: FastAPI) -> None:
    """启动后台异步刷新 app.state.update_info，让 health 接口能附带最新版本信息。
    任何异常都吞掉，update_info 维持上次值（首次失败则保持 None）。"""
    try:
        info = await check_for_update(app.state.version)
        app.state.update_info = info
    except Exception:  # noqa: BLE001 — 网络/解析失败不影响主流程
        logger.exception("启动时刷新 update_info 失败，health 将返回 latest_version=null")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn 启动后 fire-and-forget 查一次更新，结果给 health 用。
    不阻塞 startup —— 首次请求若早于查更新完成，health 的 latest_version 为 null。"""
    asyncio.create_task(_refresh_update_info(app))
    yield


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper", lifespan=lifespan)
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None
    app.state.update_info = None  # 由 lifespan 异步填充

    # add_middleware 是 LIFO：越晚 add 越靠外层。
    # 先 add snapshot 让它在内层 → CORS preflight（OPTIONS）被中间件直接 400
    # 拒绝时不会进入业务路由，也就不会被 snapshot 记录；简单请求（GET/POST）
    # 即使 Origin 不在白名单，仍会穿透到业务并被 snapshot 记录，只是响应不带
    # Access-Control-Allow-Origin，浏览器侧 JS 拿不到响应。
    install_request_snapshot(app)
    app.add_middleware(
        HotReloadCORSMiddleware,
        get_origins=lambda: load_config().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    # 先挂 API 路由，再挂前端静态文件到 /（StaticFiles 是兜底匹配）。
    # dist 不存在时（如只跑后端 pytest、还没构建前端）跳过，不影响后端测试。
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

    return app
