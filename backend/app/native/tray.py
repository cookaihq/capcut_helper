"""跨平台状态栏 / 托盘抽象。

macOS 用 PyObjC NSStatusItem（`_tray_macos.py`），Windows 用 pystray（`_tray_windows.py`）。
公共回调（on_open / on_check_update / on_quit / on_closing）在本模块统一定义。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Protocol


class TrayPlatform(Protocol):
    """状态栏 / 托盘平台实现接口。"""

    def install(
        self,
        window,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        """在主线程 / 子线程安装状态栏图标 + 菜单。各平台自行处理线程语义。"""
        ...

    def set_panel_visible(self, visible: bool) -> None:
        """mac 切 NSApp activation policy；win no-op。"""
        ...

    def teardown(self) -> None:
        """移除图标 / 停止托盘线程。on_quit 时调用，必须在 window.destroy 之前。"""
        ...


@dataclass(frozen=True)
class TrayCallbacks:
    on_open: Callable[[], None]
    on_check_update: Callable[[], None]
    on_quit: Callable[[], None]
    on_closing: Callable[[], bool]


def build_tray_callbacks(
    window,
    platform: TrayPlatform,
    on_check_update: Callable[[], None],
) -> TrayCallbacks:
    """构造与平台无关的公共回调。

    - `on_open`：show 窗口、(mac) 切 .regular、抢前台
    - `on_quit`：teardown 托盘 → destroy 窗口 → 进程退出 → FastAPI 守护线程被回收
    - `on_closing`：关闭窗口拦截，返回 False 表示「取消关闭、改为隐藏」
    """

    def on_open() -> None:
        platform.set_panel_visible(True)
        window.show()
        window.restore()

    def on_quit() -> None:
        platform.set_panel_visible(True)   # destroy 前切回 regular，避免 Dock 视觉错位
        platform.teardown()
        window.destroy()

    def on_closing() -> bool:
        window.hide()
        platform.set_panel_visible(False)
        return False   # 取消 pywebview 默认的销毁

    return TrayCallbacks(
        on_open=on_open,
        on_check_update=on_check_update,
        on_quit=on_quit,
        on_closing=on_closing,
    )


def create_tray_platform() -> TrayPlatform:
    """根据 sys.platform 返回对应实现。"""
    if sys.platform == "darwin":
        from app.native._tray_macos import MacOSTray
        return MacOSTray()
    if sys.platform == "win32":
        from app.native._tray_windows import WindowsTray
        return WindowsTray()
    raise NotImplementedError(f"unsupported platform: {sys.platform}")
