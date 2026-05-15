import threading
import time
import urllib.request

import uvicorn
import webview

from app.core.config import load_config
from app.core.logging import setup_logging
from app.core.port import select_port
from app.native.bridge import NativeBridge
from app.server import create_app


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
    window = webview.create_window(
        "剪映助手",
        f"http://127.0.0.1:{port}/",
        js_api=bridge,
        width=900,
        height=640,
    )
    bridge.window = window
    webview.start()


if __name__ == "__main__":
    main()
