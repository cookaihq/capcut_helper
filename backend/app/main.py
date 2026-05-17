import app.core.locale_fix  # noqa: F401 — 必须最先，固定 UTF-8 locale 给 libmediainfo

import json
import logging
import os
import sys
import threading
import time
import urllib.request

# pywebview Windows 后端（webview/platforms/winforms.py）会 `import clr`（pythonnet）。
# pythonnet 默认走 coreclr 后端要求用户机装 .NET 6+，对普通终端用户太重；改走 netfx
# 用 Windows 自带的 .NET Framework 4.x，零额外用户依赖。必须在 `import webview` 之前 set。
if sys.platform == "win32":
    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")

import uvicorn
import webview

from app.core.config import load_config
from app.core.logging import setup_logging
from app.core.port import select_port
from app.core.url_handler import URLParseError, parse_trust_url
from app.native.bridge import NativeBridge
from app.native.tray import build_tray_callbacks, create_tray_platform
from app.server import create_app

logger = logging.getLogger(__name__)


def _run_server(app, port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _wait_for_server(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/v1/health"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)  # noqa: S310 — 本地回环
            return True
        except Exception:  # noqa: BLE001 — 服务还没起来，继续等
            time.sleep(0.1)
    return False


def main() -> None:
    setup_logging()
    cfg = load_config()
    port = select_port(cfg.port_range)
    app = create_app(port)

    # uvicorn 跑在后台守护线程，pywebview GUI 循环必须在主线程
    threading.Thread(target=_run_server, args=(app, port), daemon=True).start()
    if not _wait_for_server(port):
        raise RuntimeError(f"本地服务在端口 {port} 启动超时")

    bridge = NativeBridge()
    # 让 /api/v1/internal/handle-url 能触达 bridge（Windows 单例转发用）
    app.state.bridge = bridge

    window = webview.create_window(
        "剪映助手",
        f"http://127.0.0.1:{port}/",
        js_api=bridge,
        width=900,
        height=640,
    )
    bridge.window = window

    tray = create_tray_platform()

    callbacks = None  # forward declaration（菜单点击时 callbacks 已 binding 完成）

    def on_check_update_clicked():
        """状态栏菜单「检查更新」：先打开面板，再让前端横幅 UI 重查。"""
        callbacks.on_open()
        # 前端 capcut-helper:check-update 监听是 follow-up，未监听时 evaluate_js 不报错
        window.evaluate_js(
            "window.dispatchEvent(new CustomEvent('capcut-helper:check-update'))"
        )

    def on_trust_url_received(url: str) -> None:
        """capcut-helper://trust?origin=... 到达：解析 → 拉出窗口 → 让前端 Modal 弹出。
        前端 TrustRequestModal 监听 capcut-helper:trust-request 事件。"""
        try:
            req = parse_trust_url(url)
        except URLParseError:
            logger.warning("收到非法 trust URL，丢弃：%s", url)
            return
        callbacks.on_open()
        detail = json.dumps({"origin": req.origin}, ensure_ascii=False)
        window.evaluate_js(
            f"window.dispatchEvent(new CustomEvent('capcut-helper:trust-request', {{detail: {detail}}}))"
        )

    callbacks = build_tray_callbacks(window, tray, on_check_update=on_check_update_clicked)
    bridge.register_url_handler(on_trust_url_received)
    window.events.closing += callbacks.on_closing

    webview.start(
        func=lambda: tray.install(
            window, callbacks.on_open, callbacks.on_check_update, callbacks.on_quit
        ),
    )


if __name__ == "__main__":
    main()
