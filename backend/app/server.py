from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.exceptions import register_exception_handlers

# 前端构建产物目录：capcut_helper/frontend/dist
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None

    cfg = load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
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
