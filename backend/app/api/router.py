from fastapi import APIRouter

from app.api import config, drafts, health, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(drafts.router)
api_router.include_router(tasks.router)
api_router.include_router(config.router)
