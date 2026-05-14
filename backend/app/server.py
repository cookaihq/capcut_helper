from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.exceptions import register_exception_handlers


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__

    cfg = load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app
