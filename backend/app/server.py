import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.cors import HotReloadCORSMiddleware
from app.core.exceptions import register_exception_handlers
from app.core.request_snapshot import install_request_snapshot


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


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None

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
