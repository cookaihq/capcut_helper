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

    # Windows URL Scheme 入口：OS 唤起 capcut-helper://... 时会启动新 .exe
    # 进程并把 URL 作 sys.argv[1] 传入。先探测已运行实例，能转发就转发并退出；
    # 否则继续本进程正常启动，启动完后自己派 URL 到前端。
    initial_url: str | None = None
    if sys.platform == "win32":
        from app.native._url_scheme_windows import (
            detect_url_arg,
            try_forward_to_existing,
        )
        url_arg = detect_url_arg(sys.argv)
        if url_arg is not None:
            if try_forward_to_existing(url_arg, cfg.port_range):
                # 已运行实例接收了 URL，本进程使命达成
                return
            # 没找到已运行实例：留到 _post_start 派发给本进程的前端
            initial_url = url_arg

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

    def _post_start() -> None:
        """webview 主循环就绪后跑的副作用：装托盘、注册 URL Scheme、派初启 URL。
        必须等主循环起来才能调，否则 macOS NSAppleEventManager 拿不到 shared
        instance / pystray 也不能创建图标。"""
        tray.install(window, callbacks.on_open, callbacks.on_check_update, callbacks.on_quit)
        if sys.platform == "darwin":
            from app.native._url_scheme_macos import install_url_scheme_handler
            install_url_scheme_handler(bridge.on_url_received)
        # Windows 首启 + sys.argv 带 URL：本进程接到 URL 但还没启动过实例，
        # 启动完成后自己派给前端 Modal（同一进程内派发，不需要 HTTP 转发）
        if initial_url is not None:
            bridge.on_url_received(initial_url)

    webview.start(func=_post_start)


if __name__ == "__main__":
    main()
