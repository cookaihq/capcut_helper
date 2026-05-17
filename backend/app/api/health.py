from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from app.core.config import load_config
from app.core.url_handler import TRUST_ACTION, URL_SCHEME

router = APIRouter()


@router.get("/health")
async def health(request: Request, response: Response):
    """健康检查 / 服务身份 / CORS 自检 / 版本感知。

    health 是「服务发现」入口，调用方需要先用它确认：
    1. 本地服务存在且是 capcut_helper（端口段 9527-9536 扫描）
    2. 自己的 origin 是否在白名单（cors_allowed），否则业务接口会被浏览器拦截
    3. helper 是否有新版本可用（latest_version / has_update）

    为了让任意 origin 都能读到响应，本接口手动反射 Origin 到 ACAO
    （HotReloadCORSMiddleware 在 origin 不在白名单时不会动响应头，因此手动设
    置的 ACAO 会保留；在白名单时中间件也会反射 origin，行为一致）。
    """
    origin = request.headers.get("origin")

    cors_allowed: bool | None
    hint: str | None = None
    trust_url: str | None = None
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
                "请打开剪映助手 → 设置 → CORS 白名单，添加该域名后保存（无需重启）；"
                "或在调用方页面引导用户点击 trust_url 一键唤起剪映助手授权。"
            )
            trust_url = f"{URL_SCHEME}://{TRUST_ACTION}?origin={quote(origin, safe='')}"

    update_info = request.app.state.update_info
    latest_version = update_info.latest_version if update_info else None
    has_update = bool(update_info and update_info.has_update)
    release_url = update_info.release_url if update_info else None

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
            "scheme": URL_SCHEME,
            "trust_url": trust_url,
            "latest_version": latest_version,
            "has_update": has_update,
            "release_url": release_url,
        },
    }
