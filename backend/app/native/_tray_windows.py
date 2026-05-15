"""Windows 系统托盘实现。

依赖：pystray>=0.19, pillow>=10.0（pyproject.toml 平台条件依赖，Task 5）。

线程模型：
- webview.start(func=...) 的 func 在子线程执行
- 本模块 install() 在该子线程内 spawn 一个 daemon 子线程跑 pystray.Icon.run()
- icon.run() 阻塞跑 Win32 message loop，必须独占线程
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from app import __version__


def _make_placeholder_icon() -> Image.Image:
    """动态画一个 32x32 的占位图标，不引入二进制资源文件。

    注意：当前白底，Windows 11 深色任务栏下视觉突兀。正式图标需适配透明背景 +
    浅/深色模式，作为 follow-up。
    """
    img = Image.new("RGBA", (32, 32), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((2, 2, 30, 30), radius=6, outline=(0, 0, 0, 255), width=2)
    # 字体回落到默认；中文字符可能渲染为方块，正式图标 follow-up
    draw.text((9, 5), "剪", fill=(0, 0, 0, 255))
    return img


class WindowsTray:
    def __init__(self) -> None:
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def install(
        self,
        window,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        # 幂等：重复 install 时先停掉旧图标，避免两个托盘图标同时存在
        if self._icon is not None:
            self._icon.stop()

        # pystray callback 在 Win32 消息线程执行；pywebview window.destroy() 内部用
        # PostMessage 派发，跨线程调用安全。
        # pystray callback 签名是 (icon, item)，包装一层
        def _wrap(cb):
            return lambda icon, item: cb()

        self._icon = pystray.Icon(
            "capcut_helper",
            icon=_make_placeholder_icon(),
            title=f"capcut_helper v{__version__}",
            menu=pystray.Menu(
                pystray.MenuItem(f"v{__version__}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("打开面板", _wrap(on_open), default=True),
                pystray.MenuItem("检查更新...", _wrap(on_check_update)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", _wrap(on_quit)),
            ),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def set_panel_visible(self, visible: bool) -> None:
        # Windows 上窗口 hide/show 本身就处理任务栏与 Alt+Tab；no-op
        pass

    def teardown(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
        # 不 join 线程：daemon 线程会被主进程退出回收；
        # join 反而可能因 pystray 内部消息循环未及时退出阻塞 destroy
