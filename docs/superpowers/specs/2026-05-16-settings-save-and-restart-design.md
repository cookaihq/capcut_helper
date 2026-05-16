# 设置面板「保存并重启」与 CORS 热生效 — Design

**日期**：2026-05-16
**触发**：用户在 [SettingsView.jsx](../../../frontend/src/views/SettingsView.jsx) 把 `https://app.canvas4me.com` 加入 CORS 白名单并保存，但页面仍报 `No 'Access-Control-Allow-Origin' header`。根因是 [server.py:30-45](../../../backend/app/server.py#L30-L45) 在 `create_app()` 启动时把 `cfg.cors_origins` 烤进 `CORSMiddleware`，运行期 `PUT /api/v1/config` 写盘后中间件不会重读。

## 目标

1. **CORS 白名单改完立即生效**，不需要重启应用。
2. **端口段**改完需要重启进程才能生效（端口由启动时 `select_port` 选定），但重启动作由应用自身完成 —— 用户点一次按钮，不需要去托盘退出再手动启动。
3. 按钮文案根据**实际需要**显示「保存」或「保存并重启」，不要总是恐吓用户「会重启」。

## 现状

| 设置项 | 是否需要重启 | 原因 |
|---|---|---|
| 剪映草稿根目录 (`draft_root`) | 否 | 业务层每次按需读 config |
| CORS 白名单 (`cors_origins`) | **是（当前）** | `CORSMiddleware` 在 `create_app()` 启动时绑死 |
| 端口段 (`port_range`) | 是 | `select_port(cfg.port_range)` 仅在 `main()` 启动时调用一次 |

进程模型：单进程，pywebview 占主线程，uvicorn 在 daemon 线程。退出即整体退出，没有守护进程会自动拉起。

## 设计

### 1. 触发逻辑（智能切换）

按钮文案从 form 的 dirty 状态推导，不弹额外的「重启确认」modal：

```
init_values = 表单加载时的快照（getConfig 返回值）
current_values = 表单当前值
restart_required = (current_values.port_start, current_values.port_end)
                != (init_values.port_start, init_values.port_end)

label = restart_required ? "保存并重启" : "保存"
```

- 改了 CORS / 草稿目录 → `保存`
- 改了端口段（不管 CORS 是否同时改了）→ `保存并重启`
- 都没改 → `保存`（按钮不 disabled，允许重保存幂等动作，符合现状）

保存成功后：

- `restart_required = false`：维持现状（`message.success('已保存')` + `onSaved` 回调）。
- `restart_required = true`：`message.success('已保存，正在重启...')` 然后调 `window.pywebview.api.restart_app()`。

### 2. CORS 热生效

把 `cors_origins` 从「启动时读一次的不可变 list」改成「每个 preflight / 响应**现场读 config**」。

#### 方案：装一个薄壳 middleware

新建 [backend/app/core/cors.py](../../../backend/app/core/cors.py)：

```python
from typing import Callable, Sequence
from starlette.middleware.cors import CORSMiddleware

class HotReloadCORSMiddleware(CORSMiddleware):
    """每次请求重建 allow_origins 集合，让 PUT /config 的改动立即对下一次请求生效。"""

    def __init__(self, app, get_origins: Callable[[], Sequence[str]], **kwargs) -> None:
        # 用一个无意义的初始 origin 进父类构造（仅为通过类型校验，会在每次请求前被覆盖）
        super().__init__(app, allow_origins=[], **kwargs)
        self._get_origins = get_origins

    async def __call__(self, scope, receive, send):
        origins = list(self._get_origins())
        # 复用父类逻辑：现场刷新 self.allow_origins / self.allow_origins_regex 等派生字段
        self.allow_origins = origins
        self.allow_all_origins = "*" in origins
        return await super().__call__(scope, receive, send)
```

`server.py` 改为：

```python
from app.core.cors import HotReloadCORSMiddleware
from app.core.config import load_config

app.add_middleware(
    HotReloadCORSMiddleware,
    get_origins=lambda: load_config().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`load_config()` 每次读 [config.json](../../../backend/app/core/config.py)（同步小文件 IO，本地服务可接受）。**不加 mtime 缓存** —— YAGNI；本地请求量低，性能开销可忽略，省一层缓存失效逻辑。

#### 失败兜底

`get_origins()` 抛异常时（config 文件被破坏）：父类用空 origins → 所有跨域被拒。这是安全的失败模式（fail-closed），不需要额外 try/except。

### 3. 重启机制（端口段变更走这条路）

走 **native bridge**，不走 HTTP（HTTP 自杀有响应竞态）。

#### 关键观察

[tray.py:60-63](../../../backend/app/native/tray.py#L60-L63) 的 `on_quit` 已经完成「`platform.teardown()` + `window.destroy()`」整套退出动作，且 `window.destroy()` 不会触发 `closing` 事件（pywebview 的 `destroy` 是强制销毁，绕过 close intercept）—— 所以**不需要新增 flag，复用 `on_quit` 即可**。

#### Bridge 改造

[backend/app/native/bridge.py](../../../backend/app/native/bridge.py) 的 `NativeBridge` 增加一个可选回调字段，由 `main.py` 在构造时注入：

```python
class NativeBridge:
    def __init__(self) -> None:
        self.window = None
        self.on_quit: Callable[[], None] | None = None  # 由 main.py 注入

    def restart_app(self) -> None:
        """detached 起新实例，再调 on_quit 让当前进程退出。"""
        import subprocess, sys

        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([sys.executable, *sys.argv[1:]],
                             creationflags=flags, close_fds=True)
        else:
            subprocess.Popen([sys.executable, *sys.argv[1:]],
                             start_new_session=True, close_fds=True)

        if self.on_quit:
            self.on_quit()
```

#### main.py 接线

```python
bridge = NativeBridge()
# ... 创建 window, tray, callbacks 之后 ...
bridge.on_quit = callbacks.on_quit
```

这样 bridge 不需要知道 tray / window 的细节，只调由 main.py 装配好的退出闭包。

#### 注意点

- **`sys.executable` + `sys.argv[1:]`**：PyInstaller frozen（one-file / one-dir）下 `sys.executable` 是 bundle exe，`sys.argv` 通常只有 `[exe-path]`，`[1:]` 为空 —— 重启行为正确。
- **开发期限制**：`python -m app.main` 下 `sys.executable` 是 python 解释器，`sys.argv` 是 `[".../app/main.py"]`，`[sys.executable, *sys.argv[1:]]` 等价于 `python` 无参数 —— 无法重启。开发期不支持自动重启，前端调用 `restartApp()` 后会出现「老进程退出但没新进程」。**缓解**：bridge 检测 `getattr(sys, "frozen", False)`，未冻结时跳过 Popen + on_quit，直接 `raise RuntimeError("dev mode 不支持自动重启")`，前端 catch 后 fallback 到 `message.warning('开发模式请手动重启')`。
- **端口释放竞态**：新进程启动后 `select_port` 扫端口段，老进程释放慢也会自然落到下一个端口；不需要显式 sleep。
- **bridge 调用线程**：pywebview js_api 在 pywebview 自己的线程里执行，`on_quit` 内的 `window.destroy()` pywebview 支持跨线程调用 —— 复用现有 tray 「退出」菜单的相同路径。

### 4. 前端集成

在 [frontend/src/api/bridge.js](../../../frontend/src/api/bridge.js) 加：

```js
export async function restartApp() {
  if (!isBridgeAvailable()) return false
  try {
    await window.pywebview.api.restart_app()
    return true
  } catch {
    return false  // dev mode 下 bridge 抛 RuntimeError
  }
}
```

`SettingsView.jsx` `onSave` 改为：

```js
const onSave = async () => {
  const v = await form.validateFields()
  setSaving(true)
  try {
    await putConfig({ ... })
    if (restartRequired) {
      message.success('已保存，正在重启…')
      const ok = await restartApp()
      if (!ok) message.warning('请手动重启应用以使端口段生效')
    } else {
      message.success('已保存')
      onSaved?.()
    }
  } catch (err) { ... }
}
```

`restartRequired` 通过 `Form.useWatch` 监听 `port_start` / `port_end` 与初始值比较。

### 5. 顺带清理

- [SettingsView.jsx:88](../../../frontend/src/views/SettingsView.jsx#L88) 提示文案：`修改端口段需重启应用生效` → `修改端口段会自动重启应用`。
- CORS 字段下方加小字：`修改后立即生效`，与端口段对齐用户预期。

## 测试

| 用例 | 验证点 |
|---|---|
| `backend/tests/test_cors_hot_reload.py`（新增） | 起 TestClient，写 config（CORS=[A]），preflight A 通过；改 config 文件（CORS=[A,B]），preflight B 也通过 |
| `backend/tests/test_request_snapshot.py:69` | 现存 CORS preflight 测试不破 |
| 手动 — Win11 | 桌面应用里把 `https://app.canvas4me.com` 加入 CORS、保存（按钮文案 `保存`）→ canvas4me 页面 fetch `/health` 直接通 |
| 手动 — Win11 | 桌面应用里把端口段改成 `9600-9610`、保存（按钮文案 `保存并重启`）→ 应用窗口消失再重新出现，托盘图标重建，新窗口顶栏显示新端口 |
| 手动 — macOS | 同上两条 |

前端单测覆盖 `restartRequired` 推导（用 Antd Form mock，断言按钮 children 文案随端口字段变化）。

## YAGNI 不做

- mtime 缓存 `load_config()`：本地请求量低，先简单读盘；如未来出现性能问题再加。
- 端口段变化以外的「需重启」场景：当前没有其他启动时绑死的配置；新增时再扩展 `restartRequired` 判定。
- HTTP `/restart` 端点：bridge 已够用；如果未来要支持 webview 外重启再加。
- 重启前的「保存草稿」/「确认未完成操作」flow：设置面板没有未保存的临时状态，不需要。
