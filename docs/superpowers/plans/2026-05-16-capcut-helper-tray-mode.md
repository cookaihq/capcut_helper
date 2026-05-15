# capcut_helper 状态栏后台运行模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 capcut_helper 从「关窗即退出」改造成「关窗收到状态栏 / 系统托盘后台运行，仅显式退出才停 FastAPI」，同时把现有「仅 macOS」扩展为 macOS + Windows 双平台。

**Architecture:** 在 `app/native/` 下新增 `tray.py`（跨平台抽象 + 公共 callback）、`_tray_macos.py`（PyObjC NSStatusItem + 替换 pywebview 默认 Quit 项的 action 拦 Cmd+Q + Dock activation policy 切换）、`_tray_windows.py`（pystray Icon + PIL 动态占位图标）。`main.py` 注册 `window.events.closing` 回调把关闭转为「隐藏」。update_checker 资产匹配按 `sys.platform` 分支匹配 mac 的 `.dmg` 和 Windows 的 `.zip`。

**Tech Stack:** Python 3.11+, FastAPI, pywebview 5.x（cocoa + edgechromium 后端），PyObjC（macOS 状态栏，已被 pywebview 拉入），pystray + Pillow（Windows 托盘，新增条件依赖），PyInstaller（双平台打包）。

**Spec：** `docs/superpowers/specs/2026-05-16-capcut-helper-tray-mode-design.md`

---

## 文件结构

**新增**：
- `backend/app/native/tray.py` — 跨平台入口、`TrayPlatform` Protocol、`create_tray_platform()` 工厂、公共 callback（`on_open` / `on_check_update` / `on_quit` / `on_closing`）
- `backend/app/native/_tray_macos.py` — macOS 实现（私有，仅 `tray.py` 导入）
- `backend/app/native/_tray_windows.py` — Windows 实现（私有）
- `backend/capcut_helper_win.spec` — Windows PyInstaller spec
- `scripts/build_win.ps1` — Windows 构建脚本
- `backend/tests/test_tray.py` — 公共 callback 单元测试

**修改**：
- `backend/app/main.py` — 注册 closing 事件、调 `tray.install()`、`webview.start` 改用 `func` 参数
- `backend/app/services/update_checker.py` — `_asset_name_for_tag` 平台分支
- `backend/tests/test_update_checker.py` — 加 Windows 资产名测试
- `backend/pyproject.toml` — 加 pystray + pillow 条件依赖
- `backend/capcut_helper.spec` — 显式声明 `AppKit` hidden import
- `backend/app/native/bridge.py` — Windows 自定义草稿目录探测（spike，调研到则实现）
- `README.md` — 运行行为、Windows 分发说明、已知限制

---

## Task 1：update_checker 资产匹配按平台分支

**Files:**
- Modify: `backend/app/services/update_checker.py` (lines 1-13)
- Modify: `backend/tests/test_update_checker.py` (lines 1-19)

- [ ] **Step 1.1：写失败测试 — Windows 资产名**

修改 `backend/tests/test_update_checker.py`，在文件末尾追加：

```python
import sys


def test_asset_name_for_tag_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _asset_name_for_tag("v0.2.0") == "capcut_helper-arm64-v0.2.0.dmg"


def test_asset_name_for_tag_on_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert _asset_name_for_tag("v0.2.0") == "capcut_helper-x64-v0.2.0.zip"


def test_asset_name_for_tag_unsupported_platform(monkeypatch):
    import pytest
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(NotImplementedError, match="linux"):
        _asset_name_for_tag("v0.2.0")
```

- [ ] **Step 1.2：跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_update_checker.py::test_asset_name_for_tag_on_win32 -v
```
Expected: FAIL（当前实现忽略 platform，返回 `.dmg`）

- [ ] **Step 1.3：实现平台分支**

修改 `backend/app/services/update_checker.py` 的 `_asset_name_for_tag`（替换 lines 11-13）：

```python
import sys


def _asset_name_for_tag(tag: str) -> str:
    """根据 release tag 构造期望的资产名。tag 形如 'v0.2.0'。"""
    if sys.platform == "darwin":
        return f"capcut_helper-arm64-{tag}.dmg"
    if sys.platform == "win32":
        return f"capcut_helper-x64-{tag}.zip"
    raise NotImplementedError(f"unsupported platform: {sys.platform}")
```

注意：`import sys` 加到文件顶部 import 块。

- [ ] **Step 1.4：跑全部测试确认通过**

```bash
cd backend && uv run pytest tests/test_update_checker.py -v
```
Expected: 所有原有测试 + 3 个新测试全 PASS（原测试都跑在 macOS host 上、`sys.platform == 'darwin'`，行为不变）

- [ ] **Step 1.5：commit**

```bash
cd backend
git add app/services/update_checker.py tests/test_update_checker.py
git commit -m "feat(capcut_helper): update_checker 资产匹配按平台分支 mac .dmg / win .zip"
```

---

## Task 2：tray.py 公共抽象 + callback 工厂

**Files:**
- Create: `backend/app/native/tray.py`
- Create: `backend/tests/test_tray.py`

- [ ] **Step 2.1：写失败测试 — on_open 调用顺序**

创建 `backend/tests/test_tray.py`：

```python
from unittest.mock import MagicMock

from app.native.tray import build_tray_callbacks


def _make_platform_mock():
    """模拟 TrayPlatform 的 mock 对象，方便验证调用次数与顺序。"""
    platform = MagicMock()
    platform.set_panel_visible = MagicMock()
    platform.teardown = MagicMock()
    return platform


def test_on_open_shows_window_and_makes_panel_visible():
    """on_open 应该先标 panel visible（mac 切 .regular）再 show 窗口。
    顺序对 mac 的 Dock 显示动画有意义。"""
    window = MagicMock()
    platform = _make_platform_mock()
    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())

    callbacks.on_open()

    # 顺序：set_panel_visible(True) → window.show() → window.restore() → activate
    # 用 mock_calls 列表保证调用序列
    calls = [c[0] for c in platform.set_panel_visible.mock_calls]
    assert calls == [(True,)]
    window.show.assert_called_once()
    window.restore.assert_called_once()
```

- [ ] **Step 2.2：跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_tray.py::test_on_open_shows_window_and_makes_panel_visible -v
```
Expected: FAIL — `ImportError: cannot import name 'build_tray_callbacks' from 'app.native.tray'`

- [ ] **Step 2.3：创建 tray.py 骨架（Protocol + 工厂 + on_open）**

创建 `backend/app/native/tray.py`：

```python
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


@dataclass
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
```

注意：mac 端「mac 抢前台」（`NSApp.activateIgnoringOtherApps_`）放在 `_tray_macos.py` 内部，不在 `on_open` 里——避免公共回调耦合 PyObjC。改为：mac 的 `set_panel_visible(True)` 实现里**包含**激活前台的逻辑。

- [ ] **Step 2.4：跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_tray.py::test_on_open_shows_window_and_makes_panel_visible -v
```
Expected: PASS

- [ ] **Step 2.5：写更多测试 — on_quit、on_closing**

在 `backend/tests/test_tray.py` 追加：

```python
def test_on_quit_teardown_before_destroy():
    """on_quit 必须 teardown → destroy 顺序；反之 win 会留 zombie 托盘图标。"""
    window = MagicMock()
    platform = _make_platform_mock()
    call_order = []
    platform.teardown.side_effect = lambda: call_order.append("teardown")
    window.destroy.side_effect = lambda: call_order.append("destroy")

    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())
    callbacks.on_quit()

    assert call_order == ["teardown", "destroy"]


def test_on_closing_hides_and_cancels():
    """on_closing 必须返回 False（取消关闭）+ hide + set_panel_visible(False)。"""
    window = MagicMock()
    platform = _make_platform_mock()
    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())

    result = callbacks.on_closing()

    assert result is False
    window.hide.assert_called_once()
    platform.set_panel_visible.assert_called_once_with(False)


def test_on_check_update_is_passed_through():
    """on_check_update 透传，不在 build_tray_callbacks 里包装。"""
    window = MagicMock()
    platform = _make_platform_mock()
    custom = MagicMock()
    callbacks = build_tray_callbacks(window, platform, on_check_update=custom)

    callbacks.on_check_update()

    custom.assert_called_once()
```

- [ ] **Step 2.6：跑全部 tray 测试**

```bash
cd backend && uv run pytest tests/test_tray.py -v
```
Expected: 4 个测试全 PASS

- [ ] **Step 2.7：commit**

```bash
cd backend
git add app/native/tray.py tests/test_tray.py
git commit -m "feat(capcut_helper): tray 公共抽象 + callback 工厂——平台无关的 on_open/on_quit/on_closing"
```

---

## Task 3：_tray_macos.py — NSStatusItem + 占位菜单

**Files:**
- Create: `backend/app/native/_tray_macos.py`

本 task 的代码是 GUI 副作用代码（PyObjC AppKit 调用），按 spec §10.1 不写单元测试，只通过 Task 9 的手动测试矩阵验证。

- [ ] **Step 3.1：创建 _tray_macos.py 骨架（NSStatusItem + 占位文字 + 基本菜单结构）**

创建 `backend/app/native/_tray_macos.py`：

```python
"""macOS 状态栏实现。

依赖 PyObjC（AppKit / Foundation），已被 pywebview 间接拉入，不需要单独声明依赖。

关键时机：
- pywebview 5.x 的 `webview.start(func=...)` 在子线程执行 func。
- NSStatusBar / NSMenu 操作必须在主线程。本模块 install() 用 AppHelper.callAfter 派回主线程。
- 替换 pywebview 默认 Quit 项 action 必须在 pywebview 已经 setMainMenu_ 之后；
  时序上 callAfter 派出去的 block 在主循环 idle 时跑，菜单已建好，是安全的。
"""
from __future__ import annotations

from typing import Callable, Optional

import AppKit
from PyObjCTools import AppHelper

from app import __version__


class _MenuTarget(AppKit.NSObject):
    """承载状态栏菜单各项的 selector。必须保持强引用，否则 NSMenuItem 持有 unsafe_unretained 会崩。"""

    def initWithCallbacks_(self, callbacks: dict):
        self = AppKit.NSObject.init(self)
        if self is None:
            return None
        self._callbacks = callbacks
        return self

    def onOpenPanel_(self, sender):
        self._callbacks["on_open"]()

    def onCheckUpdate_(self, sender):
        self._callbacks["on_check_update"]()

    def onQuit_(self, sender):
        self._callbacks["on_quit"]()


class MacOSTray:
    """macOS 状态栏实现。状态：status_item / menu_target / quit_target 必须模块/实例级强引用。"""

    def __init__(self) -> None:
        self._status_item: Optional[AppKit.NSStatusItem] = None
        self._menu_target: Optional[_MenuTarget] = None
        self._quit_target: Optional[_MenuTarget] = None

    def install(
        self,
        window,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        # 必须派回主线程做 NSStatusItem / NSMenu 操作
        def _on_main_thread():
            self._build_status_item(on_open, on_check_update, on_quit)
            self._replace_pywebview_quit_action(on_quit)

        AppHelper.callAfter(_on_main_thread)

    def _build_status_item(
        self,
        on_open: Callable[[], None],
        on_check_update: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        status_bar = AppKit.NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self._status_item.button().setTitle_("剪映")   # 占位文字方案；正式图标 follow-up

        self._menu_target = _MenuTarget.alloc().initWithCallbacks_(
            {"on_open": on_open, "on_check_update": on_check_update, "on_quit": on_quit}
        )
        menu = self._build_menu(self._menu_target)
        self._status_item.setMenu_(menu)

    def _build_menu(self, target: _MenuTarget) -> AppKit.NSMenu:
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
        open_item.setTarget_(target)
        menu.addItem_(open_item)

        check_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "检查更新...", b"onCheckUpdate:", ""
        )
        check_item.setTarget_(target)
        menu.addItem_(check_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出", b"onQuit:", ""
        )
        quit_item.setTarget_(target)
        menu.addItem_(quit_item)

        return menu

    def _replace_pywebview_quit_action(self, on_quit: Callable[[], None]) -> None:
        """替换 pywebview 默认 Quit 项的 action，让 Cmd+Q 走 on_quit。

        依赖 pywebview cocoa `_add_app_menu` 实现细节：Quit 项位于 mainMenu 第一个子菜单、keyEquivalent="q"。
        pywebview 升级后必须重测此项；若结构变了，下面会 RuntimeError 提示。
        """
        self._quit_target = _MenuTarget.alloc().initWithCallbacks_(
            {"on_open": lambda: None, "on_check_update": lambda: None, "on_quit": on_quit}
        )
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
        if visible:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
        else:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def teardown(self) -> None:
        if self._status_item is not None:
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
            self._status_item = None
```

注意几个工程要点：
1. **`set_panel_visible(True)` 包含 `activateIgnoringOtherApps_(True)`**——把 spec §7.1 的「打开面板序列」简化到一个方法里，避免 `tray.py` 公共回调耦合 PyObjC
2. **`_menu_target` 和 `_quit_target` 都是实例属性**——保证生命周期与 `MacOSTray` 实例绑定，不被 GC
3. **`_replace_pywebview_quit_action` 失败抛 `RuntimeError`**——pywebview 升级回归时第一时间报错

- [ ] **Step 3.2：commit**

```bash
cd backend
git add app/native/_tray_macos.py
git commit -m "feat(capcut_helper): _tray_macos.py — NSStatusItem + 替换 pywebview Quit action + Dock 切换"
```

---

## Task 4：_tray_windows.py — pystray + PIL 占位图

**Files:**
- Create: `backend/app/native/_tray_windows.py`

GUI 副作用代码，不写单元测试。

- [ ] **Step 4.1：创建 _tray_windows.py**

创建 `backend/app/native/_tray_windows.py`：

```python
"""Windows 系统托盘实现。

依赖：pystray>=0.19, pillow>=10.0（pyproject.toml 平台条件依赖）。

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
    """动态画一个 32x32 的占位图标，不引入二进制资源文件。"""
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
```

- [ ] **Step 4.2：commit**

```bash
cd backend
git add app/native/_tray_windows.py
git commit -m "feat(capcut_helper): _tray_windows.py — pystray Icon + PIL 动态占位图标"
```

---

## Task 5：pyproject.toml 平台条件依赖

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 5.1：加 pystray + pillow 条件依赖**

修改 `backend/pyproject.toml` 的 `[project] dependencies` 段，在 `packaging>=24.0` 后追加两行：

```toml
[project]
name = "capcut-helper-backend"
dynamic = ["version"]
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
    "pyJianYingDraft>=0.2.6",
    "platformdirs>=4.0",
    "pywebview>=5.0",
    "packaging>=24.0",
    'pystray>=0.19; sys_platform == "win32"',
    'pillow>=10.0; sys_platform == "win32"',
]
```

注意 PEP 508 markers 用单引号 / 双引号都行，但选一种保持一致。这里改为单引号包整个字符串（因为 marker 里嵌了双引号）。

- [ ] **Step 5.2：同步依赖锁定**

```bash
cd backend && uv sync
```

Expected：在 macOS 上 pystray/pillow **不会**被安装（marker `sys_platform == "win32"` 不匹配）；`uv.lock` 会更新声明这两个 conditional dep。

- [ ] **Step 5.3：跑现有测试确认没破坏**

```bash
cd backend && uv run pytest -v
```
Expected: 所有现有测试 + Task 1/2 新增测试全 PASS

- [ ] **Step 5.4：commit**

```bash
cd backend
git add pyproject.toml uv.lock
git commit -m "deps(capcut_helper): 加 pystray/pillow 作为 Windows 条件依赖"
```

---

## Task 6：main.py 集成 closing 事件 + tray.install

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 6.1：改造 main.py**

整个替换 `backend/app/main.py` 内容：

```python
import threading
import time
import urllib.request

import uvicorn
import webview

from app.core.config import load_config
from app.core.logging import setup_logging
from app.core.port import select_port
from app.native.bridge import NativeBridge
from app.native.tray import build_tray_callbacks, create_tray_platform
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

    tray = create_tray_platform()
    # 「检查更新」目前先 no-op；Task 7 接入 update_checker 业务
    callbacks = build_tray_callbacks(window, tray, on_check_update=lambda: None)
    window.events.closing += callbacks.on_closing

    webview.start(
        func=lambda: tray.install(
            window, callbacks.on_open, callbacks.on_check_update, callbacks.on_quit
        ),
    )


if __name__ == "__main__":
    main()
```

注意：
1. `window.events.closing += callbacks.on_closing` — pywebview 的 Event 类支持 `+=` 订阅
2. `webview.start(func=lambda: ...)` — 没传 `args`，用 lambda 捕获参数；这种写法是 pywebview 文档推荐的
3. `on_check_update=lambda: None` — 临时空实现，Task 7 接入真实逻辑

- [ ] **Step 6.2：手动测试 — macOS 启动**

```bash
cd backend && uv run python -m app.main
```

手动检查（第一轮基本流程，没有正式图标也能验证）：

- [ ] 窗口弹出
- [ ] 状态栏出现「剪映」文字
- [ ] 点窗口红 × → 窗口消失、Dock 图标消失、Cmd+Tab 不再出现
- [ ] 关窗后另起一个 terminal 跑 `curl http://127.0.0.1:9527/api/v1/health`（端口看启动日志），应仍返回 200
- [ ] 点状态栏「剪映」→ 菜单弹出，含 v0.1.0 / 打开面板 / 检查更新 / 退出
- [ ] 菜单「打开面板」→ 窗口出现、Dock 出现
- [ ] **Cmd+Q** → 窗口、Dock、状态栏图标全消失（**关键：验证 Cmd+Q 拦截**）
- [ ] 再 `curl` 一次端口已释放（`lsof -i :9527` 应无输出）

如果 Cmd+Q 还是把进程吞掉而不是触发我们的 on_quit，**回到 `_tray_macos.py` 检查 `_replace_pywebview_quit_action` 的时机** —— 此时可能 pywebview 还没 setMainMenu_。修复方式：把 `_replace_pywebview_quit_action` 移到 `window.events.shown` 事件回调里触发（shown 时菜单一定已建好）。

- [ ] **Step 6.3：commit**

```bash
cd backend
git add app/main.py
git commit -m "feat(capcut_helper): main.py 集成 tray + closing 事件——关窗收到状态栏后台运行"
```

---

## Task 7：「检查更新」接入 update_checker 业务

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 7.1：实现 on_check_update**

修改 `backend/app/main.py`，把 `on_check_update=lambda: None` 那段替换为：

```python
    def on_check_update_clicked():
        """状态栏菜单「检查更新」：先打开面板，再让前端通过现有 /api/v1/update/check 横幅 UI 处理。"""
        callbacks_holder["callbacks"].on_open()
        # 触发前端横幅重新拉取（前端启动时已经会查一次，但这里再触发一次让用户能主动重查）
        window.evaluate_js(
            "window.dispatchEvent(new CustomEvent('capcut-helper:check-update'))"
        )

    callbacks_holder = {}   # 闭包占位，避免 callbacks 引用自己
    callbacks = build_tray_callbacks(window, tray, on_check_update=on_check_update_clicked)
    callbacks_holder["callbacks"] = callbacks
    window.events.closing += callbacks.on_closing
```

注意：`window.evaluate_js` 触发前端事件需要前端配合监听 — 这部分**本 task 不实现前端**，先验证后端绑定不抛错；前端监听是 follow-up（仅影响「主动重查」UX，启动检查横幅本来就会展示）。

- [ ] **Step 7.2：手动测试 — 「检查更新」菜单项**

```bash
cd backend && uv run python -m app.main
```

- [ ] 关窗
- [ ] 点状态栏 → 「检查更新...」
- [ ] 窗口应自动弹出
- [ ] 控制台不应有 evaluate_js 报错（前端没监听该事件是 OK 的，不会报错）

- [ ] **Step 7.3：commit**

```bash
cd backend
git add app/main.py
git commit -m "feat(capcut_helper): 状态栏「检查更新」入口先开面板、再触发前端横幅重查"
```

---

## Task 8：capcut_helper.spec（macOS）增量

**Files:**
- Modify: `backend/capcut_helper.spec`

- [ ] **Step 8.1：显式声明 AppKit hidden import**

修改 `backend/capcut_helper.spec`，把 `hiddenimports=pywebview_hiddenimports,` 那一行（约 line 31）替换为：

```python
    hiddenimports=pywebview_hiddenimports + ["AppKit"],
```

理由：AppKit 实际被 pywebview 间接拉入，但我们的 `_tray_macos.py` 直接 import AppKit，显式声明可防 PyInstaller 静态分析在某些版本下漏掉。

- [ ] **Step 8.2：重打 .app 验证**

```bash
cd /Users/zhao/Documents/workspace/coding/zhida/ai-tools-v2/capcut_helper
bash scripts/build_mac.sh
```
Expected: 构建无错误，产物 `dist/capcut_helper.app`

- [ ] **Step 8.3：双击打开 .app，重跑 Task 6.2 的手动测试矩阵**

特别关注：开发模式 `uv run python -m app.main` 工作不代表打包后工作——PyInstaller 经常漏 AppKit 子模块导致 NSStatusBar 找不到。

- [ ] 双击 `dist/capcut_helper.app`
- [ ] 状态栏出现「剪映」
- [ ] Cmd+Q 完整退出

- [ ] **Step 8.4：commit**

```bash
cd /Users/zhao/Documents/workspace/coding/zhida/ai-tools-v2/capcut_helper
git add backend/capcut_helper.spec
git commit -m "build(capcut_helper): mac spec 显式声明 AppKit hidden import"
```

---

## Task 9：capcut_helper_win.spec（Windows PyInstaller spec）

**Files:**
- Create: `backend/capcut_helper_win.spec`

- [ ] **Step 9.1：创建 Windows spec**

创建 `backend/capcut_helper_win.spec`：

```python
# -*- mode: python ; coding: utf-8 -*-
"""capcut_helper PyInstaller spec — 产 Windows x64 EXE + 资源目录。

用法（通过 scripts/build_win.ps1 调起）：
    cd capcut_helper/backend
    uv run pyinstaller --clean --noconfirm `
        --distpath=../dist --workpath=../build `
        capcut_helper_win.spec

前置：frontend/dist 必须先用 `npm run build` 构建好（build_win.ps1 已包含）。
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all("webview")
jianying_datas = collect_data_files("pyJianYingDraft")


a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries,
    datas=[
        ("../frontend/dist", "frontend/dist"),
        *pywebview_datas,
        *jianying_datas,
    ],
    hiddenimports=pywebview_hiddenimports + [
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="capcut_helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI 应用，不带终端窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="capcut_helper",
)
```

注意：Windows 不要 `BUNDLE`（那是 mac `.app` 专用），直接 COLLECT 出 `dist/capcut_helper/` 目录。

- [ ] **Step 9.2：commit**

```bash
cd /Users/zhao/Documents/workspace/coding/zhida/ai-tools-v2/capcut_helper
git add backend/capcut_helper_win.spec
git commit -m "build(capcut_helper): 新增 Windows PyInstaller spec"
```

---

## Task 10：scripts/build_win.ps1

**Files:**
- Create: `scripts/build_win.ps1`

- [ ] **Step 10.1：创建 Windows 构建脚本**

创建 `scripts/build_win.ps1`：

```powershell
# capcut_helper Windows x64 构建脚本。
# 用法（在 PowerShell 中、Windows 机器上）:
#   cd capcut_helper
#   powershell -ExecutionPolicy Bypass -File scripts/build_win.ps1
#
# 前置：node + npm + Python 3.11+ + uv 已安装。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

Write-Host "-> 1/3 安装/构建前端"
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "-> 2/3 PyInstaller 打包"
Push-Location backend
uv run pyinstaller --clean --noconfirm `
    --distpath=../dist --workpath=../build `
    capcut_helper_win.spec
Pop-Location

Write-Host "-> 3/3 压缩 zip"
$tag = (git describe --tags --abbrev=0 2>$null)
if ([string]::IsNullOrEmpty($tag)) {
    $tag = "v0.0.0-dev"
}
$zipName = "capcut_helper-x64-$tag.zip"
$zipPath = "dist/$zipName"
if (Test-Path $zipPath) { Remove-Item $zipPath }
Compress-Archive -Path dist/capcut_helper/* -DestinationPath $zipPath

Write-Host ""
Write-Host "构建完成："
Write-Host "  EXE 目录: $(Resolve-Path dist/capcut_helper)"
Write-Host "  zip:      $(Resolve-Path $zipPath)"
```

- [ ] **Step 10.2：commit**

```bash
git add scripts/build_win.ps1
git commit -m "build(capcut_helper): 新增 Windows 构建脚本 build_win.ps1"
```

注意：Task 10 在 macOS 上无法本地验证 `build_win.ps1` 实际能跑通——只验证语法可读、命令拼接对齐 spec。真正的「构建跑通」属于 Task 13 的手动测试矩阵 Win 部分，需要 Windows 机器。

---

## Task 11：Windows 剪映自定义草稿目录探测（spike）

**Files:**
- Modify: `backend/app/native/bridge.py`（如调研到）
- Modify: `backend/tests/test_native_bridge.py`（如调研到）

本 task 是 spec §2 范围内的探索性工作：调研剪映 Windows 版自定义草稿目录配置位置。若调研失败则只在 Task 12 README 写明已知限制。

- [ ] **Step 11.1：调研剪映 Win 版自定义草稿目录的存储位置**

在 Windows 机器上（或借朋友的）：
1. 启动剪映 Win 版
2. 在「设置 → 草稿位置」改一个自定义路径，比如 `D:\test_drafts`
3. 关闭剪映
4. 找剪映写入这个值的位置（候选）：
   - `%LOCALAPPDATA%\JianyingPro\User Data\Preferences\` 下的 json
   - `HKEY_CURRENT_USER\Software\JianyingPro` 注册表
   - `%APPDATA%\JianyingPro\` 下的 config 文件
   - 用 ProcMon（Sysinternals）观察剪映写哪个文件 / 注册表项

记录调研结果到本 task 的 commit message 或临时 note。

- [ ] **Step 11.2：如果调研到了 — 实现并加测试**

参考 `bridge.py:23-34` 的 `_read_macos_custom_draft_path` 实现一个 `_read_windows_custom_draft_path` 同款异常吞咽（PermissionError / FileNotFoundError → None）。在 `detect_draft_root` 里加 Windows 分支：

```python
def detect_draft_root(self) -> Optional[str]:
    if sys.platform == "darwin":
        custom = _read_macos_custom_draft_path()
        if custom is not None:
            return custom
    elif sys.platform == "win32":
        custom = _read_windows_custom_draft_path()
        if custom is not None:
            return custom
    # 回落到默认目录（不变）
    relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
    if relative is None:
        return None
    candidate = Path.home() / relative
    return str(candidate) if candidate.is_dir() else None
```

同步在 `test_native_bridge.py` 加 Windows 自定义路径测试（参考 mac 同款）。

跑：`cd backend && uv run pytest tests/test_native_bridge.py -v`

- [ ] **Step 11.3：commit**

如果实现了：

```bash
cd backend
git add app/native/bridge.py tests/test_native_bridge.py
git commit -m "feat(capcut_helper): Windows 剪映自定义草稿目录探测 — 读 <调研结果>"
```

如果调研不到（最差路径）：跳过此 task，进入 Task 12 时把这条写进 README 已知限制。

---

## Task 12：README 文档更新

**Files:**
- Modify: `README.md`

- [ ] **Step 12.1：新增「运行行为」章节**

在 README.md 现有「开发」章节之后、「发版」章节之前，插入：

```markdown
## 运行行为

- **启动**：双击 `.app` / `.exe` → FastAPI 本地服务起来 + 状态栏 / 系统托盘出现图标 + 主窗口弹出
- **关闭窗口**（点 ×、Cmd+W、Alt+F4）：窗口隐藏到状态栏 / 托盘，FastAPI 服务**继续运行**，ai-canvas 等调用方仍可访问
- **打开面板**：左键点状态栏 / 托盘图标，或在菜单点「打开面板」
- **完整退出**（停止 FastAPI、释放端口）：
  - macOS：状态栏菜单「退出」、或 ⌘Q
  - Windows：托盘菜单「退出」

### 状态栏 / 托盘菜单

- v0.x.x（当前版本号，只读）
- 打开面板
- 检查更新...
- 退出
```

- [ ] **Step 12.2：扩展「分发给同事」章节，加 Windows 步骤**

在现有「分发给同事」章节后追加：

```markdown
### Windows 分发

把 `dist/capcut_helper-x64-v0.x.x.zip` 发给对方，请对方按以下步骤：

1. 解压 zip，得到 `capcut_helper/` 目录
2. 双击 `capcut_helper.exe`，**首次打开**：因为未做 EV 证书签名，Windows SmartScreen 会拦截，点「更多信息」→「仍要运行」
3. **前置依赖**：WebView2 Runtime。Win11 / 最新 Win10 默认预装；老 Win10 上若启动后窗口空白，从 https://developer.microsoft.com/microsoft-edge/webview2/ 下「Evergreen Standalone Installer」安装一次
4. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择
```

- [ ] **Step 12.3：更新「已知限制」章节**

把现有「已知限制」章节替换为：

```markdown
## 已知限制

- macOS arm64（M 系列 Mac）和 Windows x64。Intel Mac 暂不支持，见 `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md` §9。
- 剪映 10.5+ 草稿编辑保存后会加密，capcut_helper 只能**新建**草稿、不能改剪映动过的草稿。详见 spec §2 实测约束。
- 状态栏 / 托盘图标当前为占位（mac 文字「剪映」、win 占位图），正式图标待补
- 状态栏菜单「检查更新」会打开面板后让前端横幅 UI 处理；前端目前在启动时已自动检查，菜单点击不会强制重查（follow-up）
```

如果 Task 11 调研失败，**额外加一条**：

```markdown
- Windows 剪映自定义草稿目录未实现自动探测：若你在剪映设置里改过草稿目录，需在 capcut_helper「设置」标签手动选择
```

- [ ] **Step 12.4：commit**

```bash
git add README.md
git commit -m "docs(capcut_helper): README 加运行行为/Windows 分发/已知限制更新"
```

---

## Task 13：双平台端到端手动测试

本 task 不写代码，只跑测试矩阵打勾、补漏修。

- [ ] **Step 13.1：macOS 完整测试矩阵**

```bash
cd /Users/zhao/Documents/workspace/coding/zhida/ai-tools-v2/capcut_helper
bash scripts/build_mac.sh
open dist/capcut_helper.app
```

逐项打勾：

- [ ] 双击 .app → 主窗口弹出 + 状态栏出现「剪映」+ Dock 有图标
- [ ] 点窗口 × → 窗口消失 + Dock 图标消失 + Cmd+Tab 不再出现 + 状态栏图标在
- [ ] 关窗后 `curl http://127.0.0.1:<port>/api/v1/health` 仍 200（port 从启动日志读）
- [ ] 状态栏左键 → 窗口出现 + Dock 出现 + 自动抢前台
- [ ] 状态栏右键（或左键，弹菜单一致） → 菜单含 v0.1.x / 打开面板 / 检查更新 / 退出
- [ ] 菜单「打开面板」→ 窗口出现
- [ ] 菜单「检查更新」→ 窗口出现，浏览器控制台无报错
- [ ] 菜单「退出」→ 窗口、Dock、状态栏图标全消失 + `lsof -i :<port>` 无输出
- [ ] **Cmd+Q** → 同「退出」（不是隐藏！— 验证 Quit action 替换生效）
- [ ] 重新启动后再 Cmd+W → 隐藏，**再** Cmd+Q → 退出

- [ ] **Step 13.2：Windows 完整测试矩阵（需 Windows 机器）**

在 Windows 机器上：

```powershell
cd capcut_helper
powershell -ExecutionPolicy Bypass -File scripts/build_win.ps1
.\dist\capcut_helper\capcut_helper.exe
```

逐项打勾：

- [ ] 双击 .exe → 主窗口 + 任务栏图标 + 托盘图标
- [ ] 点 × / Alt+F4 → 窗口消失 + 任务栏图标消失 + Alt+Tab 不再出现 + 托盘图标在
- [ ] 关窗后 `curl http://127.0.0.1:<port>/api/v1/health` 仍 200
- [ ] 托盘左键 → 窗口出现
- [ ] 托盘右键 → 菜单含 v0.1.x / 打开面板 / 检查更新 / 退出
- [ ] 菜单「退出」→ 全消失 + 端口释放 + **托盘图标立即消失，不需 hover 才消失**（验证 teardown 在 destroy 之前）

- [ ] **Step 13.3：如有问题修复后再 commit**

每个发现的 bug 用「test → fix → verify → commit」流程修。

---

## Self-Review

### Spec Coverage

按 spec 章节核对：

- §2.1 双平台状态栏 + 菜单 → Task 3 (mac) + Task 4 (win) ✓
- §2.1 closing 拦截 + Dock 切换 → Task 2 (callback) + Task 3 (mac set_panel_visible) + Task 6 (注册) ✓
- §2.1 左键打开、右键弹菜单 → mac 端 NSStatusItem.setMenu_ 默认左右键都弹菜单（Task 3.1 实测），win 端 pystray `default=True` 项处理 ✓
- §2.1 菜单项 → Task 3.1 + 4.1 ✓
- §2.1 Cmd+Q 拦截 → Task 3.1 `_replace_pywebview_quit_action` ✓
- §2.1 双平台 PyInstaller 脚本 → Task 8 (mac spec) + Task 9 (win spec) + Task 10 (win ps1) ✓
- §2.1 update_checker 平台分支 → Task 1 ✓
- §2.1 Windows draft root 探测 → Task 11 (spike) ✓
- §3.1 启动行为 → Task 6 手动测试矩阵 + Task 13 ✓
- §3.2 关闭行为 → Task 13 ✓
- §3.3 图标交互 → Task 13 ✓
- §3.4 退出顺序 → Task 2.5 `test_on_quit_teardown_before_destroy` 单测 + Task 13 手动 ✓
- §7.1 替换 Quit action → Task 3.1 ✓
- §10.1 单测策略 → Task 1, 2 ✓
- §10.2 手动测试矩阵 → Task 13 ✓
- §12 README → Task 12 ✓

**Gap**：spec §3.3 提到 macOS「左键直接打开面板」（不弹菜单），与 Task 3.1 默认行为（NSStatusItem.setMenu_ 后左键也弹菜单）冲突。

**修补**：Task 3.1 后追加一条 sub-step：

- [ ] **Step 3.1.5（补）：实现 mac 左键直接打开、右键弹菜单**

注意：上面 Step 3.1 用了 `self._status_item.setMenu_(menu)`——这会让**左右键都弹菜单**，与 spec §3.3「左键直接打开面板」不一致。

改为：**不调 `setMenu_`**，而是给 button 设 action，在 action 里根据当前事件类型分发：

```python
# 不调用 self._status_item.setMenu_(menu)
# 改为给 button 绑 action：
self._status_item.button().setTarget_(self._menu_target)
self._status_item.button().setAction_(b"onStatusBarClick:")
self._status_item.button().sendActionOn_(
    AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp
)
self._menu = menu   # 保存菜单引用，右键时手动弹
```

并在 `_MenuTarget` 加：

```python
def onStatusBarClick_(self, sender):
    event = AppKit.NSApp.currentEvent()
    if event.type() == AppKit.NSEventTypeRightMouseUp:
        # 右键 → 弹菜单
        self._status_item_ref.popUpStatusItemMenu_(self._menu_ref)
    else:
        # 左键 → 直接打开面板
        self._callbacks["on_open"]()
```

`_MenuTarget` 需要持有 `status_item` 和 `menu` 引用——把构造方法改为 `initWithCallbacks_statusItem_menu_:`，或者在 `MacOSTray._build_status_item` 里手动 setvalue。

把这块补到 Task 3 step 3.1 的代码里，覆盖原版「`setMenu_`」一段。

### Placeholder Scan

搜了一遍 plan：
- 无 "TODO"、"TBD"、"implement later"
- 无 "add appropriate error handling" 类模糊指令
- 每个代码 step 都有完整 code block
- Task 11 spike 步骤明确「调研到 → 实现 + 测试 / 调研不到 → README 已知限制」二分

### Type Consistency

- `TrayPlatform` Protocol 与 `MacOSTray` / `WindowsTray` 方法签名一致：`install(window, on_open, on_check_update, on_quit)` / `set_panel_visible(bool)` / `teardown()` ✓
- `TrayCallbacks` dataclass 字段（`on_open` / `on_check_update` / `on_quit` / `on_closing`）在所有 task 一致 ✓
- `_asset_name_for_tag(tag: str) -> str` 签名一致 ✓
- `__version__` import 来自 `app/__init__.py`（mac 和 win 一致） ✓

无类型不一致问题。

---

## 工作量再估算

按 task 粒度：

| Task | Bite-size sub-steps | 实际开发耗时 |
|---|---|---|
| 1. update_checker 平台分支 | 5 | ~15 min |
| 2. tray.py 公共抽象 | 7 | ~40 min |
| 3. _tray_macos.py | 2 + 补 1 | ~90 min（含调试 Cmd+Q 时机问题） |
| 4. _tray_windows.py | 2 | ~30 min（无机器只读、不能跑） |
| 5. pyproject.toml | 4 | ~10 min |
| 6. main.py 集成 | 3 | ~30 min（含手动测试） |
| 7. 检查更新接入 | 3 | ~20 min |
| 8. mac spec 增量 | 4 | ~20 min（含重新打包验证） |
| 9. win spec | 2 | ~15 min |
| 10. build_win.ps1 | 2 | ~15 min |
| 11. Windows draft root spike | 3 | ~30~120 min（取决于运气） |
| 12. README | 4 | ~30 min |
| 13. 双平台 e2e | 3 | ~60 min |

**总计**：~7 小时纯开发，加 Windows 端构建实测可能涨到 10+ 小时。
