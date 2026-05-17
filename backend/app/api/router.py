from fastapi import APIRouter

from app.api import config, cors_origins, drafts, health, internal, tasks, update

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(drafts.router)
api_router.include_router(tasks.router)
api_router.include_router(config.router)
api_router.include_router(update.router)
api_router.include_router(cors_origins.router)
api_router.include_router(internal.router)
