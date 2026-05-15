"""macOS 状态栏实现。

依赖 PyObjC（AppKit / Foundation），已被 pywebview 间接拉入，不需要单独声明依赖。

关键时机：
- pywebview 5.x 的 `webview.start(func=...)` 在子线程执行 func。
- NSStatusBar / NSMenu 操作必须在主线程。本模块 install() 用 AppHelper.callAfter 派回主线程。
- 替换 pywebview 默认 Quit 项 action 必须在 pywebview 已经 setMainMenu_ 之后；
  时序上 callAfter 派出去的 block 在主循环 idle 时跑，菜单已建好，是安全的。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Optional

import AppKit
import objc
from PyObjCTools import AppHelper

from app import __version__

logger = logging.getLogger(__name__)


def _resource_path(rel: str) -> Path:
    """与 app/server.py::_resource_path 同款约定：
    - 开发模式：相对 capcut_helper/ 仓库根（_tray_macos.py 在 backend/app/native/，parents[3] = capcut_helper/）
    - PyInstaller 冻结：相对 sys._MEIPASS
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parents[3] / rel


def _load_tray_template_image() -> AppKit.NSImage:
    """加载状态栏 template 图（1x + @2x），交由 macOS 按主题自动渲染颜色。

    把两份 bitmap rep 都设为 18pt 逻辑尺寸：1x 屏渲染 18px，Retina 屏渲染 36px，
    系统会按 backing scale 自动挑选锐利的那张。
    """
    paths = [
        _resource_path("backend/assets/tray_icon_template.png"),
        _resource_path("backend/assets/tray_icon_template@2x.png"),
    ]
    image = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(18, 18))
    for p in paths:
        rep = AppKit.NSBitmapImageRep.imageRepWithContentsOfFile_(str(p))
        if rep is None:
            raise RuntimeError(f"无法加载状态栏图标：{p}")
        rep.setSize_(AppKit.NSMakeSize(18, 18))
        image.addRepresentation_(rep)
    image.setTemplate_(True)
    return image


class _MenuTarget(AppKit.NSObject):
    """承载状态栏按钮点击 + 菜单项 selector 的 PyObjC 对象。

    必须保持强引用（保存到 MacOSTray 实例属性），否则 NSStatusItem.button() 持有的是
    unsafe_unretained，被 GC 后点击图标会崩。
    """

    def initWithCallbacks_statusItem_menu_(self, callbacks, status_item, menu):
        self = objc.super(_MenuTarget, self).init()
        if self is None:
            return None
        self._callbacks = callbacks
        self._status_item = status_item
        self._menu = menu
        return self

    def onStatusBarClick_(self, sender):
        """状态栏 button 的 target/action。根据当前事件类型分发左右键。

        左键 → on_open；右键 / Ctrl+点击 → 弹菜单。
        """
        event = AppKit.NSApp.currentEvent()
        if event is not None and event.type() == AppKit.NSEventTypeRightMouseUp:
            self._status_item.popUpStatusItemMenu_(self._menu)
        else:
            self._callbacks["on_open"]()

    def onOpenPanel_(self, sender):
        self._callbacks["on_open"]()

    def onCheckUpdate_(self, sender):
        self._callbacks["on_check_update"]()

    def onQuit_(self, sender):
        self._callbacks["on_quit"]()


class _QuitTarget(AppKit.NSObject):
    """专门承载 Cmd+Q action 的轻量 PyObjC 对象。
    与 _MenuTarget 分开，避免「Cmd+Q 路径」误访问状态栏菜单引用。
    """

    def initWithCallback_(self, callback):
        self = objc.super(_QuitTarget, self).init()
        if self is None:
            return None
        self._callback = callback
        return self

    def onQuit_(self, sender):
        self._callback()


class MacOSTray:
    """macOS 状态栏实现。状态 status_item / menu_target / quit_target / menu 必须实例级强引用。"""

    def __init__(self) -> None:
        self._status_item: Optional[AppKit.NSStatusItem] = None
        self._menu: Optional[AppKit.NSMenu] = None
        self._menu_target: Optional[_MenuTarget] = None
        self._quit_target: Optional[_QuitTarget] = None

    def install(
        self,
        window,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        """webview.start(func=...) 在子线程调本方法。
        NSStatusItem / NSMenu / setMainMenu_ 操作必须主线程，所以派回去。
        """
        def _on_main_thread():
            try:
                self._build_status_item(on_open, on_check_update, on_quit)
                self._replace_pywebview_quit_action(on_quit)
            except Exception:
                logger.exception("_tray_macos 安装失败")

        AppHelper.callAfter(_on_main_thread)

    def _build_status_item(
        self,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        status_bar = AppKit.NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(AppKit.NSSquareStatusItemLength)
        button = self._status_item.button()
        button.setImage_(_load_tray_template_image())
        button.setImagePosition_(AppKit.NSImageOnly)

        self._menu = self._build_menu_skeleton()

        callbacks = {
            "on_open": on_open,
            "on_check_update": on_check_update,
            "on_quit": on_quit,
        }
        self._menu_target = _MenuTarget.alloc().initWithCallbacks_statusItem_menu_(
            callbacks, self._status_item, self._menu
        )

        # 绑菜单项的 target/action
        for item in self._menu.itemArray():
            sel = item.action()
            if sel is not None:
                item.setTarget_(self._menu_target)

        # 不调 setMenu_——那样左右键都弹菜单。
        # 改为给 button 绑 action：左键 → on_open，右键 → 弹菜单（在 _MenuTarget.onStatusBarClick_ 里分发）。
        button.setTarget_(self._menu_target)
        button.setAction_(b"onStatusBarClick:")
        button.sendActionOn_(
            AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp
        )

    def _build_menu_skeleton(self) -> AppKit.NSMenu:
        """构造 NSMenu，但不绑 target——target 在 _build_status_item 里统一绑。"""
        menu = AppKit.NSMenu.alloc().init()

        version_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"v{__version__}", None, ""
        )
        version_item.setEnabled_(False)
        menu.addItem_(version_item)
        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        open_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "打开面板", b"onOpenPanel:", ""
        )
        menu.addItem_(open_item)

        check_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "检查更新...", b"onCheckUpdate:", ""
        )
        menu.addItem_(check_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出", b"onQuit:", ""
        )
        menu.addItem_(quit_item)

        return menu

    def _replace_pywebview_quit_action(self, on_quit: Callable[[], None]) -> None:
        """替换 pywebview 默认 Quit 项的 action，让 Cmd+Q 走 on_quit。

        依赖 pywebview cocoa `_add_app_menu` 实现细节：Quit 项位于 mainMenu 第一个子菜单、
        keyEquivalent="q"。pywebview 升级后必须重测此项；若结构变了，下面会 RuntimeError 提示。
        """
        self._quit_target = _QuitTarget.alloc().initWithCallback_(on_quit)

        main_menu = AppKit.NSApp.mainMenu()
        if main_menu is None or main_menu.numberOfItems() == 0:
            raise RuntimeError("pywebview main menu not initialized yet (timing bug?)")
        app_menu = main_menu.itemArray()[0].submenu()
        for item in app_menu.itemArray():
            if item.keyEquivalent() == "q":
                item.setAction_(b"onQuit:")
                item.setTarget_(self._quit_target)
                return
        raise RuntimeError("pywebview default Quit menu item not found — pywebview API changed?")

    def set_panel_visible(self, visible: bool) -> None:
        """mac 切 NSApp activation policy。visible=True 同时把窗口抢到前台。"""
        if visible:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
        else:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def teardown(self) -> None:
        if self._status_item is not None:
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
            self._status_item = None
