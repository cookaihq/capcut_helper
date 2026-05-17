"""Windows capcut-helper:// URL Scheme 接收 + 单实例转发。

Windows 没有 mac 的 NSAppleEventManager 那样的「URL Scheme 派给已运行实例」
机制。OS 唤起 capcut-helper:// 链接时，会启动一个新 capcut_helper.exe 进程
并把 URL 作为 sys.argv[1] 传入。本模块提供两个函数：

1. detect_url_arg(argv): 从 argv 里找出 capcut-helper:// URL（如果有）
2. try_forward_to_existing(url, port_range): 扫端口段探测已运行实例并 POST
   转发；成功返回 True，新进程应当立即退出，让已运行实例处理 URL

如果端口段没找到已运行实例（如首启），调用方应当继续正常启动流程，并在
webview 就绪后自己调 bridge.on_url_received(url) 派发到前端 Modal。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional, Sequence

from app.core.url_handler import URL_SCHEME

logger = logging.getLogger(__name__)

_HEALTH_TIMEOUT_S = 0.5
_FORWARD_TIMEOUT_S = 2.0


def detect_url_arg(argv: Sequence[str]) -> Optional[str]:
    """从启动参数里挑出 capcut-helper:// URL（OS 唤起时作为 argv[1] 传入）。
    没有返回 None。argv 通常是 sys.argv，跳过 argv[0]（程序自身路径）。"""
    for arg in argv[1:]:
        if isinstance(arg, str) and arg.startswith(f"{URL_SCHEME}://"):
            return arg
    return None


def try_forward_to_existing(url: str, port_range: Sequence[int]) -> bool:
    """扫 port_range[start..end] 找已运行的 capcut_helper 实例并把 URL 转过去。

    流程：对每个端口先 GET /health 看 data.service == "capcut_helper"
    确认是本服务（避免误命中本机别的服务），然后 POST /internal/handle-url
    把 URL 转过去。任一端口成功转发返回 True；全部失败返回 False。

    所有 HTTP 错误都吞掉，因为这个函数是「best-effort 探测」，失败不致命，
    调用方会回退到「自己启动」分支。
    """
    start, end = port_range[0], port_range[1]
    for port in range(start, end + 1):
        if not _is_capcut_helper_at(port):
            continue
        if _post_url_to(port, url):
            logger.info("已把 URL 转发给端口 %d 上的 capcut_helper 实例: %s", port, url)
            return True
    return False


def _is_capcut_helper_at(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/health",  # noqa: S310 — 本地回环
            timeout=_HEALTH_TIMEOUT_S,
        ) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    data = body.get("data") if isinstance(body, dict) else None
    return isinstance(data, dict) and data.get("service") == "capcut_helper"


def _post_url_to(port: int, url: str) -> bool:
    payload = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/internal/handle-url",  # noqa: S310
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_FORWARD_TIMEOUT_S) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
