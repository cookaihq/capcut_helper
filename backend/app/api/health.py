from fastapi import APIRouter, Request, Response

from app.core.config import load_config

router = APIRouter()


@router.get("/health")
async def health(request: Request, response: Response):
    """健康检查 / 服务身份 / CORS 自检。

    health 是「服务发现」入口，调用方需要先用它确认：
    1. 本地服务存在且是 capcut_helper（端口段 9527-9536 扫描）
    2. 自己的 origin 是否在白名单（cors_allowed），否则业务接口会被浏览器拦截

    为了让任意 origin 都能读到响应，本接口手动反射 Origin 到 ACAO
    （HotReloadCORSMiddleware 在 origin 不在白名单时不会动响应头，因此手动设
    置的 ACAO 会保留；在白名单时中间件也会反射 origin，行为一致）。
    """
    origin = request.headers.get("origin")

    cors_allowed: bool | None
    hint: str | None = None
    if origin is None:
        # 非浏览器调用（curl / 服务端 HTTP），不受 CORS 约束
        cors_allowed = None
    else:
        cors_allowed = origin in load_config().cors_origins
        # health 对任意 origin 放行 ACAO，让调用方 JS 能读到 body
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        if not cors_allowed:
            hint = (
                f"当前域名 {origin} 未在 CORS 白名单中，业务接口会被浏览器拦截。"
                "请打开剪映助手 → 设置 → CORS 白名单，添加该域名后保存（无需重启）。"
            )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "service": "capcut_helper",
            "version": request.app.state.version,
            "port": request.app.state.port,
            "last_draft_request_at": request.app.state.last_draft_request_at,
            "your_origin": origin,
            "cors_allowed": cors_allowed,
            "hint": hint,
        },
    }
