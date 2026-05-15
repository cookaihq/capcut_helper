"""请求快照 middleware：把进入 /api 的每条请求落盘，方便 bug 复现。

存储路径：platformdirs.user_log_dir("capcut_helper") / requests/{YYYY-MM-DD}/{ts}_{method}_{path-slug}_{rid}.json
保留：30 天（启动时清理一次）
"""
import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from platformdirs import user_log_dir
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(user_log_dir("capcut_helper")) / "requests"
RETENTION_DAYS = 30
MAX_BODY_BYTES = 1 * 1024 * 1024  # 1MB 上限，超过截断
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization"}
PATH_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]")


def _slugify_path(path: str) -> str:
    """把 URL path 转成可放进文件名的 slug。"""
    return PATH_SLUG_RE.sub("_", path.strip("/")) or "root"


def _redact_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        out[k] = "<redacted>" if k.lower() in SENSITIVE_HEADERS else v
    return out


def _decode_body(body: bytes) -> tuple[str, dict | None]:
    """body bytes → (preview, json_obj or None)。超过 MAX_BODY_BYTES 截断。"""
    if not body:
        return "", None
    truncated = len(body) > MAX_BODY_BYTES
    raw = body[:MAX_BODY_BYTES]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary {len(body)} bytes, truncated={truncated}>", None
    obj = None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    return text + ("...<truncated>" if truncated else ""), obj


def _write_snapshot(path: Path, payload: dict) -> None:
    """同步写文件，被 asyncio.to_thread 包到线程池。失败只 log，不影响请求。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — 快照失败不能影响业务
        logger.warning("request snapshot write failed: %s", exc)


def cleanup_old_snapshots(retention_days: int = RETENTION_DAYS) -> None:
    """启动时调用一次，删除超期的 {YYYY-MM-DD} 目录。"""
    if not SNAPSHOT_DIR.is_dir():
        return
    cutoff = datetime.now().date() - timedelta(days=retention_days)
    for child in SNAPSHOT_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            day = datetime.strptime(child.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            for f in child.iterdir():
                f.unlink(missing_ok=True)
            child.rmdir()


class RequestSnapshotMiddleware(BaseHTTPMiddleware):
    """对 path 前缀匹配 self.prefix 的请求做快照。"""

    def __init__(self, app, prefix: str = "/api") -> None:
        super().__init__(app)
        self.prefix = prefix

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith(self.prefix):
            return await call_next(request)
        # 浏览器 CORS preflight，每个跨域业务请求伴随一次，无业务价值，跳过
        if request.method == "OPTIONS":
            return await call_next(request)

        rid = uuid.uuid4().hex[:12]
        ts = time.time()
        ts_iso = datetime.fromtimestamp(ts).isoformat(timespec="milliseconds")

        # 读 body 后必须把它"塞回去"，否则后续 handler 读不到
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        body_preview, body_json = _decode_body(body)
        snapshot: dict = {
            "ts": ts_iso,
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "headers": _redact_headers(request.headers),
            "body_json": body_json,
            "body_text": body_preview if body_json is None else None,
            "client": request.client.host if request.client else None,
        }

        try:
            response = await call_next(request)
        except Exception:
            snapshot["status_code"] = None
            snapshot["error"] = "exception_in_handler"
            await self._save(snapshot, ts_iso, rid)
            raise

        snapshot["status_code"] = response.status_code
        await self._save(snapshot, ts_iso, rid)
        return response

    async def _save(self, snapshot: dict, ts_iso: str, rid: str) -> None:
        date_dir = ts_iso[:10]
        ts_compact = ts_iso[11:].replace(":", "").replace(".", "_")
        slug = _slugify_path(snapshot["path"])
        fname = f"{ts_compact}_{snapshot['method']}_{slug}_{rid}.json"
        path = SNAPSHOT_DIR / date_dir / fname
        await asyncio.to_thread(_write_snapshot, path, snapshot)


def install_request_snapshot(app: FastAPI, prefix: str = "/api") -> None:
    """挂载 middleware + 启动时清理。"""
    cleanup_old_snapshots()
    app.add_middleware(RequestSnapshotMiddleware, prefix=prefix)
