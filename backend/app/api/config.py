from fastapi import APIRouter

from app.core.config import Config, load_config, save_config

router = APIRouter()


@router.get("/config")
async def get_config():
    return {"code": 0, "message": "ok", "data": load_config().model_dump()}


@router.put("/config")
async def put_config(cfg: Config):
    save_config(cfg)
    return {"code": 0, "message": "ok", "data": cfg.model_dump()}
