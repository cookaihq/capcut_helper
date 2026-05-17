"""CORS 白名单管理接口。

供前端 TrustRequestModal 在用户点「允许」后调用，把 origin 追加到 cors_origins
配置。是 PUT /api/v1/config 的窄化版——只能新增、自带格式校验、幂等，避免前
端 Modal 误覆盖整个 config 对象。
"""
from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.core.config import load_config, save_config
from app.core.url_handler import is_valid_origin

router = APIRouter()


class ApproveOriginRequest(BaseModel):
    origin: str

    @field_validator("origin")
    @classmethod
    def _validate(cls, v: str) -> str:
        if not is_valid_origin(v):
            raise ValueError("origin 必须符合 http(s)://host[:port] 形式，不接受路径/查询/通配符/IPv6")
        return v


@router.post("/cors-origins")
async def approve_origin(req: ApproveOriginRequest):
    """把 origin 追加到 cors_origins 白名单（幂等：已存在直接返回 added=false）。

    CORS 中间件是热生效的，写入后下一次业务请求即时被信任，无需重启。
    """
    cfg = load_config()
    if req.origin in cfg.cors_origins:
        return {
            "code": 0,
            "message": "已在白名单中",
            "data": {"origin": req.origin, "added": False},
        }
    cfg.cors_origins = list(cfg.cors_origins) + [req.origin]
    save_config(cfg)
    return {
        "code": 0,
        "message": "已添加",
        "data": {"origin": req.origin, "added": True},
    }
