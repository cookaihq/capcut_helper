"""仅供本机进程间使用的接口（前缀 /internal）。

Windows 没有 mac 的 NSAppleEventManager 那样的「URL Scheme 派给已运行实例」
机制。当 OS 用 capcut-helper:// 唤起 helper 时，Windows 会启动一个新进程并把
URL 当 sys.argv[1] 传入。新进程检测到已有 capcut_helper 在端口段运行（通过
GET /health 探测），就调本接口把 URL 转交给已运行实例处理，然后自身退出。

为防止外部网页通过本接口推送任意 URL 给 helper，做严格的访问控制：
仅接受 127.0.0.1 / ::1 来源；非本机请求直接 403。
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.url_handler import URLParseError, parse_trust_url

router = APIRouter()


class HandleUrlRequest(BaseModel):
    url: str


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


@router.post("/internal/handle-url")
async def handle_url(req: HandleUrlRequest, request: Request):
    """接收一个 capcut-helper:// URL 并转交给 native bridge 派给前端。
    供 Windows 第二个 helper 进程把 URL 转给已运行实例。仅本机可用。"""
    client_host = request.client.host if request.client else ""
    if client_host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="forbidden: local only")

    try:
        parse_trust_url(req.url)  # 仅作前置格式校验；真正派发由 bridge.on_url_received
    except URLParseError as e:
        raise HTTPException(status_code=400, detail=f"invalid URL: {e}")

    bridge = getattr(request.app.state, "bridge", None)
    if bridge is None:
        # pytest 等没装 bridge 的场景：返回 200 但 noop，不报 500
        return {"code": 0, "message": "ok (no bridge)", "data": None}

    bridge.on_url_received(req.url)
    return {"code": 0, "message": "ok", "data": None}
