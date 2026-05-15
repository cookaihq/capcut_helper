# capcut_helper 状态栏后台运行模式 — 设计文档

> 创建日期：2026-05-16
> 状态：brainstorming 完成，待写实现计划
> 范围：把 capcut_helper 从「关窗即退出」改造成「关窗收到状态栏 / 系统托盘后台运行，仅显式退出才停服务」。同时把现有「仅 macOS」扩展为 **macOS + Windows 双平台**。
> 前置：Plan 1（本地服务）+ Plan 2（GUI）+ Plan 3（macOS 打包）已合入 main。

## 1. 项目目标

让 capcut_helper 像 macOS 上的 Bartender、Windows 上的 Telegram 一样：

- 后端 FastAPI 服务**持续后台运行**（让 ai-canvas 能随时调用），不依赖主窗口是否可见
- 状态栏 / 系统托盘**始终保留图标**作为「应用还在运行」的可视提示
- **关闭窗口 ≠ 退出应用**：用户最常用的「点 × 关闭」只是收到状态栏 / 托盘
- **完整退出**有明确入口：状态栏 / 托盘菜单「退出」，或 macOS 主菜单 ⌘Q

## 2. 范围

### 2.1 核心范围

- 双平台（macOS arm64 + Windows x64）状态栏 / 托盘图标 + 菜单
- 窗口关闭按钮拦截 → 隐藏到状态栏（同时 macOS 端把 Dock 图标动态切换为隐藏）
- 状态栏图标交互：左键打开面板、右键弹菜单
- 菜单项：版本号（只读）/ 打开面板 / 检查更新 / 退出
- macOS 自建应用主菜单以拦截 ⌘Q，让 ⌘Q 走与「退出」菜单项完全相同的路径
- 双平台 PyInstaller 打包脚本（macOS `build_mac.sh` 已存在、扩展；Windows `build_win.ps1` 新增）
- update_checker 资产匹配按平台分支（mac → `.dmg`，win → `.zip`）
- Windows 端 `detect_draft_root` 自定义草稿目录探测（当前 `bridge.py` TODO 项）：实现阶段先调研剪映 Win 版自定义草稿目录配置位置（registry / 配置文件），调研到则实现，调研不到则回落到默认路径并写入 §11 已知限制

### 2.2 非目标

- **开机自启动**：状态栏应用常见但非必需。本次先让用户手动启动，后续单独 spec
- **多窗口 / 通知中心 / Sparkle 式自动更新**：当前 update_checker 是「启动检查 + 横幅提示」，本次只增加「状态栏菜单手动触发」入口，复用现有横幅
- **正式状态栏图标设计**：本次用占位实现（mac 显示文字「剪映」、win 用 PIL 动态画的占位图），正式图标作为 follow-up
- **代码签名 / 公证**（mac）/ **EV 证书签名**（win）：依旧绕过 Gatekeeper / SmartScreen，README 已有说明
- **Intel Mac**：与现有 spec 一致，arm64-only

## 3. 行为规范

### 3.1 启动行为

双击 `.app` / `.exe` →
1. 后端 FastAPI 守护线程起来
2. 状态栏 / 托盘出现图标
3. **同时弹出主窗口**（这是用户「双击应用看到窗口」的心智模型）
4. macOS 启动时 `setActivationPolicy_(NSApplicationActivationPolicyRegular)`（默认），Dock 有图标

### 3.2 关闭窗口行为

| 触发 | macOS 行为 | Windows 行为 |
|---|---|---|
| 红色 × / Cmd+W | closing 事件 → hide + 切 `.accessory` + cancel 关闭 | closing 事件 → hide + cancel 关闭 |
| Cmd+Q | 走自建主菜单 action → on_quit（**完整退出**） | N/A |
| Alt+F4 | N/A | closing 事件（同 ×） |

关闭窗口后：
- 后端 FastAPI 持续运行，端口不释放
- 状态栏 / 托盘图标继续可见
- macOS 上 Dock 图标淡出、Cmd+Tab 不再出现该应用
- Windows 上任务栏图标 / Alt+Tab 自动消失（pywebview hide 默认行为）

### 3.3 状态栏 / 托盘图标交互

| 触发 | macOS | Windows |
|---|---|---|
| 左键单击图标 | 打开面板（show + 切 `.regular` + activate） | 同（pystray `default=True` 菜单项行为） |
| 右键单击图标 | 弹菜单 | 弹菜单（pystray 原生） |
| 菜单「打开面板」 | 同左键 | 同左键 |
| 菜单「检查更新」 | 先 on_open() 再触发现有检查逻辑 | 同 |
| 菜单「退出」 | on_quit（完整退出） | on_quit（完整退出） |
| Cmd+Q（mac 主菜单） | on_quit（完整退出） | N/A |

「打开面板」是幂等的：窗口已在前台时再点一次没副作用。

### 3.4 完整退出行为

`on_quit()` 触发后：
1. macOS：`setActivationPolicy_(.regular)`（防止 destroy 时残留 accessory 状态），Windows：no-op
2. `tray.teardown()`：mac 移除 NSStatusItem；win 调 `pystray.Icon.stop()` 让托盘线程退出
3. `window.destroy()`：pywebview 销毁窗口并退出主循环
4. `webview.start()` 返回 → `main()` 返回 → Python 进程退出
5. uvicorn 守护线程随主进程被回收 → FastAPI 端口释放

**约束**：步骤 2 必须在步骤 3 之前。Windows 上若反过来，pystray 线程没机会优雅退出，会留 zombie 托盘图标（hover 才消失）。

## 4. 模块结构

```
backend/app/
├── main.py                       # 修改：注册 closing 拦截 + webview.start(func=tray.install)
└── native/
    ├── bridge.py                 # 不变
    ├── tray.py                   # 新增：跨平台入口 + 公共回调（on_open / on_quit / on_check_update）
    ├── _tray_macos.py            # 新增：PyObjC NSStatusItem + NSMenu + 主菜单（拦 Cmd+Q）+ Dock 切换
    └── _tray_windows.py          # 新增：pystray Icon + Menu
```

**抽象接口**（写在 `tray.py` 里）：

```python
class TrayPlatform(Protocol):
    def install(self, window, on_open, on_check_update, on_quit) -> None: ...
    def set_panel_visible(self, visible: bool) -> None: ...  # mac 切 policy，win no-op
    def teardown(self) -> None: ...
```

**职责划分**：
- `tray.py` — 公共回调实现、closing 事件回调、根据 `sys.platform` 选实现
- `_tray_macos.py` — 所有 PyObjC 调用（AppKit / Foundation），不外泄
- `_tray_windows.py` — 所有 pystray 调用 + PIL 占位图标生成

**为什么不单独成 `tray/` 子包**：当前一共 3 个文件，扁平结构 import 路径短、没有未来扩展点（不会再加第三平台）。

## 5. 修改后的 main.py 流程

```
1. setup_logging() / load_config() / select_port()         # 不变
2. uvicorn 守护线程起 FastAPI + _wait_for_server            # 不变
3. tray = create_tray_platform()                           # 新增
4. bridge = NativeBridge()
5. window = webview.create_window(..., js_api=bridge)      # 不变
6. bridge.window = window
7. tray_callbacks = build_tray_callbacks(window, tray)     # 新增
8. window.events.closing += on_closing                     # 新增（cancelable）
9. webview.start(func=tray.install,                        # 修改
                 func_args=(window, *tray_callbacks))
10. webview.start() 返回 → main() 返回 → 进程结束
```

**`webview.start(func=...)`** 的回调在 NSApp / WinForms 主循环启动后立刻在主线程执行，是 PyObjC 创建 NSStatusItem / pystray 启动子线程的安全时机。

## 6. closing 事件回调

```python
def on_closing() -> bool:
    """Return False to cancel close (hide instead)."""
    window.hide()
    tray.set_panel_visible(False)   # mac 切 .accessory；win no-op
    return False                     # 取消 pywebview 默认的销毁行为
```

pywebview cocoa 后端 / winforms 后端的 closing 事件均为 `cancelable=True`，返回 False 即取消。

## 7. 平台特定实现要点

### 7.1 macOS（`_tray_macos.py`）

**NSStatusItem 创建**（在 `install()` 里，已经在 NSApp 主线程）：

```python
status_bar = AppKit.NSStatusBar.systemStatusBar()
status_item = status_bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
status_item.button().setTitle_("剪映")   # 占位文字方案
# 后续替换为图标：status_item.button().setImage_(NSImage.imageNamed_("tray"))
```

**必须强引用 `status_item`**（保存到模块级变量或 `tray.py` 实例），否则会被 GC，图标消失。

**左右键区分**：

```python
status_item.button().sendActionOn_(
    AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp
)
# action handler 里通过 NSApp.currentEvent().type() 判断
```

**Dock 切换**（模块级私有函数）：

```python
def _set_dock_hidden():
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

def _set_dock_visible():
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
```

**自建主菜单**（拦 Cmd+Q）：

```python
main_menu = AppKit.NSMenu.alloc().init()
app_menu_item = AppKit.NSMenuItem.alloc().init()
main_menu.addItem_(app_menu_item)

app_menu = AppKit.NSMenu.alloc().init()
quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
    "退出 capcut_helper", b"onQuitFromMenu:", "q"
)
quit_item.setTarget_(menu_target)   # menu_target 是持有 on_quit 的 PyObjC 对象
app_menu.addItem_(quit_item)
app_menu_item.setSubmenu_(app_menu)

AppKit.NSApp.setMainMenu_(main_menu)
```

pywebview 当前在不传 `window.menu` 参数时不会自己调 `setMainMenu_`，所以这里直接覆盖不会冲突。

**Dock 切换顺序敏感**：
- hide 时 **先 hide 窗口、再切 accessory**（避免空 Dock 图标闪一下）
- show 时 **先切 regular、再 show 窗口**（让 Dock 图标先出现，再把窗口抢前）

**「打开面板」完整调用序列**（左键 / 菜单「打开面板」/「检查更新」均复用）：

```
_set_dock_visible()                        # 切 .regular
window.show()                               # 显示窗口
window.restore()                            # 若之前被最小化
AppKit.NSApp.activateIgnoringOtherApps_(True)   # 强制抢前台
```

`window.restore()` 在窗口未最小化时是 no-op，不需要额外判断。

### 7.2 Windows（`_tray_windows.py`）

**占位图标**（PIL 动态生成，不引入二进制资源）：

```python
from PIL import Image, ImageDraw
img = Image.new('RGBA', (32, 32), (255, 255, 255, 255))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle((2, 2, 30, 30), radius=6, outline=(0, 0, 0, 255), width=2)
draw.text((9, 5), "剪", fill=(0, 0, 0, 255))   # 字体回落默认
```

**Icon 与 Menu**：

```python
icon = pystray.Icon(
    'capcut_helper',
    icon=img,
    title=f'capcut_helper v{__version__}',
    menu=pystray.Menu(
        pystray.MenuItem(f'v{__version__}', None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('打开面板', on_open, default=True),
        pystray.MenuItem('检查更新...', on_check_update),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('退出', on_quit),
    ),
)
threading.Thread(target=icon.run, daemon=True).start()
```

pystray 必须另开线程（否则 `icon.run()` 阻塞，pywebview 主循环跑不起来）。线程 `daemon=True` —— `teardown()` 里调 `icon.stop()` 让线程优雅退出；即使 `teardown()` 因异常没跑到，daemon 线程也会被主进程退出连带回收。

**Windows 无 Dock 切换**：`set_panel_visible()` 为 no-op，hide/show 窗口本身就处理任务栏与 Alt+Tab。

**Windows 无主菜单需求**：Alt+F4 与 × 按钮走同一 closing 事件，统一隐藏即可。退出只走托盘菜单——这符合 Win 用户对系统托盘应用的心智模型（Telegram、企业微信、Steam 都如此）。

## 8. update_checker 资产匹配扩展

当前 `_asset_name_for_tag()` 硬编码 `capcut_helper-arm64-{tag}.dmg`。改为按平台分支：

```python
def _asset_name_for_tag(tag: str) -> str:
    if sys.platform == 'darwin':
        return f'capcut_helper-arm64-{tag}.dmg'
    if sys.platform == 'win32':
        return f'capcut_helper-x64-{tag}.zip'
    raise NotImplementedError(f'unsupported platform: {sys.platform}')
```

发布时 GitHub Release 同时挂两个资产：`capcut_helper-arm64-v0.2.0.dmg` 和 `capcut_helper-x64-v0.2.0.zip`。任一平台缺资产时，update_checker 只在该平台报「未找到匹配资产」而不影响另一平台。

## 9. 打包

### 9.1 macOS（`capcut_helper.spec` 增量）

- `hiddenimports` 显式加 `AppKit`（实际已被 pywebview 拉，显式声明防 PyInstaller 静态分析丢失）
- **Info.plist 不能加 `LSUIElement = true`**：那样启动时 Dock 就不出现，违背「双击启动弹主窗口」需求。由运行时 `setActivationPolicy_` 动态控制
- `build_mac.sh` 不需改

### 9.2 Windows（新增 `capcut_helper_win.spec` + `scripts/build_win.ps1`）

**spec 关键 hidden imports**（PyInstaller 经典坑）：

```python
hiddenimports = pywebview_hiddenimports + [
    'pystray._win32',
    'PIL._tkinter_finder',
]
```

`pywebview` 的 Windows 后端会拉 `pythonnet` + WebView2 相关包，已被 `collect_all('webview')` 覆盖。

**`build_win.ps1`**：

```powershell
Set-Location $PSScriptRoot/..
Set-Location frontend; npm install; npm run build; Set-Location ..
Set-Location backend
uv run pyinstaller --clean --noconfirm `
    --distpath=../dist --workpath=../build `
    capcut_helper_win.spec
Set-Location ..
$tag = git describe --tags --abbrev=0
Compress-Archive -Path dist/capcut_helper/* `
    -DestinationPath "dist/capcut_helper-x64-$tag.zip" -Force
```

**Windows 用户前置条件**：WebView2 Runtime（Win11 / 最新 Win10 默认预装；老 Win10 需要从微软官网装一次）。README 分发说明补一行。

### 9.3 依赖

`backend/pyproject.toml`：

```toml
dependencies = [
    ...
    'pystray>=0.19 ; sys_platform == "win32"',
    'pillow>=10.0 ; sys_platform == "win32"',
]
```

平台条件依赖避免 macOS 打包多余拉 pystray。

## 10. 测试策略

### 10.1 自动化测试（pytest）

- `_tray_macos.py` 与 `_tray_windows.py` 是 GUI 副作用代码，**不写单测**（强行 mock PyObjC / pystray 收益低于维护成本）
- `tray.py` 公共回调（on_open / on_quit）写单测，mock 掉 `TrayPlatform` 接口验证调用顺序：
  - `on_quit()` 必须 `set_panel_visible(True) → teardown() → window.destroy()` 顺序
  - `on_open()` 必须 `set_panel_visible(True) → show() → restore() → activate()` 顺序
- `update_checker._asset_name_for_tag` 平台分支单测

### 10.2 手动测试矩阵

**macOS**：
- [ ] 双击 .app → 主窗口弹出 + 状态栏出现「剪映」图标 + Dock 有图标
- [ ] 点窗口 × → 窗口消失 + Dock 图标消失 + Cmd+Tab 不再出现 + 状态栏图标在
- [ ] 关窗后 `curl http://127.0.0.1:<port>/api/v1/health` 仍 200
- [ ] 状态栏左键 → 窗口出现 + Dock 出现
- [ ] 状态栏右键 → 菜单含 v0.1.0 / 打开面板 / 检查更新 / 退出
- [ ] 菜单「退出」→ 窗口、Dock、状态栏图标全消失 + 端口释放（`lsof -i :<port>` 无）
- [ ] Cmd+Q → 同「退出」（不是隐藏）
- [ ] 「检查更新」→ 窗口打开 + 复用现有更新流程

**Windows**：
- [ ] 双击 .exe → 主窗口 + 任务栏图标 + 托盘图标
- [ ] 点 × / Alt+F4 → 窗口消失 + 任务栏图标消失 + Alt+Tab 不再出现 + 托盘图标在
- [ ] 关窗后 `curl http://127.0.0.1:<port>/api/v1/health` 仍 200
- [ ] 托盘左键 → 窗口出现
- [ ] 托盘右键 → 菜单含 v0.1.0 / 打开面板 / 检查更新 / 退出
- [ ] 菜单「退出」→ 全消失 + 端口释放，托盘图标无 zombie（无需 hover 触发消失）

## 11. 已知限制 / 后续项

- 占位图标（mac 文字「剪映」、win PIL 动态图）需要替换为正式图标 — follow-up
- 无开机自启动 — follow-up
- 异常退出（kill -9 / 系统强关）不做 graceful shutdown — 文档说明「正常退出请走状态栏『退出』或 ⌘Q」
- Windows 剪映自定义草稿目录：如本次实测拿不到剪映 Win 版的等价配置位置，则保留 `bridge.py` 现有 TODO，README 已知限制章节补一行
- 系统注销 / 关机触发的 NSApp terminate 会走 `applicationShouldTerminate_` → `should_close()` → `closing` event → 被拦截为「隐藏」。这种 corner case macOS 会强 kill，可以接受

## 12. README 增量

- 「运行行为」新增章节：状态栏图标 + 关窗即隐藏的语义
- 「分发」section 增加 Windows 步骤（zip → 解压 → 双击 .exe → SmartScreen 绕过 → WebView2 Runtime 前置说明）
- 「已知限制」section：Windows 自定义草稿目录（如未解决）

## 13. 工作量预估

- `tray.py` 公共抽象 + 回调：~80 行
- `_tray_macos.py`：~150 行（PyObjC 占大头）
- `_tray_windows.py`：~80 行
- `main.py` 改造：~20 行 diff
- update_checker 平台分支：~20 行
- `capcut_helper_win.spec` + `build_win.ps1`：~50 行
- 测试代码：~80 行
- README 改动：~30 行

合计 ~510 行新增 / 修改。
