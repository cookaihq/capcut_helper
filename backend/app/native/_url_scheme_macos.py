"""macOS capcut-helper:// URL Scheme 接收 handler。

mac 的 URL Scheme 派发走 Apple Event Manager：当用户点击 capcut-helper://...
链接时，OS 会激活已注册该 scheme 的 app 并发一个 GURL Apple Event
（kInternetEventClass / kAEGetURL）。本模块注册一个 NSObject handler，事件
到达时把 URL 字符串拿出来交给 callback。

注意：
- 必须在 NSApp run loop 启动后注册，否则 sharedAppleEventManager 拿不到。
  调用方应在 webview.start(func=...) 的 func 里调 install_url_scheme_handler。
- handler 必须长期强引用，否则被 GC 后 Apple Event 派来时找不到对象会崩。
- 如果 app 未运行时收到 URL，OS 会先启动 app，然后派发事件——此时 handler
  还没注册，事件会被 NSApp 缓冲，注册完后立即派给我们。
- 配套：capcut_helper.spec 的 info_plist 必须声明 CFBundleURLTypes 才能让
  OS 把 capcut-helper:// 路由到本 app。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

import objc
from Foundation import NSAppleEventManager, NSObject
from PyObjCTools import AppHelper

logger = logging.getLogger(__name__)

# Apple Event 四字符常量。这些值是 macOS Carbon API 历史遗留，PyObjC 不暴露
# 命名常量，直接用 OSType（4 字符 ASCII 拼成的 32-bit int）。
_kInternetEventClass = 0x4755524C  # 'GURL'
_kAEGetURL = 0x4755524C            # 'GURL'
_keyDirectObject = 0x2D2D2D2D      # '----'


class _URLHandler(NSObject):
    def initWithCallback_(self, cb):
        self = objc.super(_URLHandler, self).init()
        if self is None:
            return None
        self._callback = cb
        return self

    def handleEvent_withReplyEvent_(self, event, reply_event):
        """Apple Event Manager 派发入口。selector 名拼写必须严格对应注册时的
        b"handleEvent:withReplyEvent:" — 改一处必须改两处。"""
        descriptor = event.paramDescriptorForKeyword_(_keyDirectObject)
        if descriptor is None:
            logger.warning("GURL 事件无 directObject 参数，丢弃")
            return
        url = descriptor.stringValue()
        if not url:
            logger.warning("GURL 事件 directObject 为空字符串，丢弃")
            return
        try:
            self._callback(url)
        except Exception:  # noqa: BLE001 — Apple Event 派发必须吞异常
            logger.exception("URL handler callback 异常：%s", url)


# 模块级强引用：Apple Event Manager 持有的是 weak/unretained，handler 被 GC 后
# 派事件会崩。保留模块作用域引用让生命周期跟进程一致。
_handler_strong_ref: Optional[_URLHandler] = None


def install_url_scheme_handler(callback: Callable[[str], None]) -> None:
    """注册 capcut-helper:// URL Scheme handler。callback(url:str) 在主线程被调。

    通过 AppHelper.callAfter 派回主线程执行，所以本函数本身可以从任意线程调；
    pywebview 的 webview.start(func=...) func 跑在子线程，所以必须派回去。
    """
    def _on_main_thread():
        global _handler_strong_ref
        _handler_strong_ref = _URLHandler.alloc().initWithCallback_(callback)
        manager = NSAppleEventManager.sharedAppleEventManager()
        manager.setEventHandler_andSelector_forEventClass_andEventID_(
            _handler_strong_ref,
            b"handleEvent:withReplyEvent:",
            _kInternetEventClass,
            _kAEGetURL,
        )
        logger.info("capcut-helper:// URL Scheme handler 已注册")

    AppHelper.callAfter(_on_main_thread)
