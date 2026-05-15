# capcut_helper 版本号与更新提示 — 设计文档

> 创建日期：2026-05-15
> 状态：brainstorming 完成，待写实现计划
> 范围：把当前散落的版本号收拢到单一来源，并在 GUI 里展示当前版本 + 启动时向 GitHub Releases 检查新版本、用横幅提示用户去下载。
> 前置：Plan 1（本地服务）+ Plan 2（桌面 GUI）+ Plan 3（macOS 打包）已合入 `main`，`bash scripts/build_mac.sh` 能打出可分发的 `.app`。

## 1. 项目目标

- **版本号有单一来源**，避免「3 个文件手抄数字、发版漏改」
- **GUI 状态栏显示当前版本号**，同事知道自己在跑哪个版本
- **启动时检查 GitHub Releases**，发现新版本就用横幅提示，提供「查看说明」+「直接下载」两个入口
- **调用方（ai-canvas 等）能拿到 `version`** 自己做兼容性判断（已通过 `/api/v1/health` 实现，本设计不动接口、只补文档）

## 2. 范围

### 2.1 核心范围（本 spec）

- 单一版本源：`backend/app/__init__.py::__version__`
  - `backend/pyproject.toml` 改 `dynamic = ["version"]` + hatchling 读 `__init__.py`
  - `frontend/package.json` 删 `version` 字段
- 后端新增：
  - `app/integrations/github_releases.py` — GitHub Releases 适配器
  - `app/services/update_checker.py` — 编排与版本比较
  - `app/api/update.py` — `GET /api/v1/update/check` 端点
  - `app/schemas/update.py` — Pydantic 响应模型
  - `app/native/bridge.py` — 加 `open_url(url)` 方法（`webbrowser.open()`）
- 前端新增 / 扩展：
  - `src/components/UpdateBanner.jsx` — 仿 `DraftRootBanner` 的横幅
  - `src/components/StatusBar.jsx` — 加版本号显示
  - `src/api/client.js` — 加 `getUpdateInfo()`
  - `src/api/bridge.js` — 加 `openUrl()`（含浏览器开发态降级）
  - `src/App.jsx` — 挂载 UpdateBanner
- 文档：
  - `backend/docs/CALLER_GUIDE.md` §5.1 已更新（补 `last_draft_request_at` + `version` 使用建议）
  - `README.md` 加「发版」流程小节

### 2.2 非目标

- **自动下载 / 自动替换 `.app`**：同事手动下载 zip、覆盖 `.app`（沿用当前分发模式）
- **「跳过此版本」持久化**：每次启动重新评估，关闭横幅只在本次启动内有效
- **后端缓存 GitHub API 响应**：helper 启动只查一次，无必要
- **多平台资产匹配**：当前只有 macOS arm64，资产名硬编码 `capcut_helper.zip`
- **GitHub 鉴权 / token**：仓库 `cookaihq/capcut_helper` 是公开的，匿名 60 req/h 足够单机用户
- **CI 自动打 tag / 自动 release**：发版流程仍人工
- **修改 `/api/v1/health` 接口形态**：现有字段不动；CALLER_GUIDE 补字段说明只是描述既有事实

## 3. 单一版本源

### 3.1 事实

grep 确认运行时唯一被读取的版本号是 `backend/app/__init__.py::__version__`：

```
backend/app/__init__.py:1:__version__ = "0.1.0"
backend/app/server.py:8:from app import __version__
backend/app/server.py:32:    app.state.version = __version__
backend/app/api/health.py:13:            "version": request.app.state.version,
```

`backend/pyproject.toml::version` 和 `frontend/package.json::version` 没有任何代码读取，是悬空元数据。

### 3.2 改动

**`backend/pyproject.toml`** — 加 build-system，把 `version` 改 dynamic：

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

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
]

[tool.hatch.version]
path = "app/__init__.py"
```

注：
- `packaging` 显式声明为依赖（用于版本比较，避免依赖 httpx 的间接引入）
- hatchling 是显式加的 build backend，因为 dynamic version 需要它来读 `__init__.py`。该包不发 PyPI，`[build-system]` 不会改变 `uv sync` / `uv run` 现有行为，只让 `tool.hatch.version` 生效
- 需要回归测试：`uv sync` 仍可正常装包；`uv run python -c "import importlib.metadata; print(importlib.metadata.version('capcut-helper-backend'))"` 输出与 `app.__version__` 一致

**`frontend/package.json`** — 删除 `"version": "0.1.0"` 这一行。前端不发 npm 包，version 字段没人读；GUI 显示版本号从 `/api/v1/health` 拿。

**`backend/app/__init__.py`** — 维持现状作为唯一手写处：

```python
__version__ = "0.1.0"   # 唯一手写处。发版前手动 bump。
```

### 3.3 发版流程（README 新增小节）

- 改 `backend/app/__init__.py::__version__` 为新版本号（例如 `"0.1.1"`）
- 提交 commit
- 打 tag `v0.1.1`，推到 GitHub
- 执行 `bash scripts/build_mac.sh`
- 在 GitHub Releases 页面创建 release，**上传 `dist/capcut_helper.zip` 作为资产，资产名必须保持 `capcut_helper.zip`**（与 build_mac.sh 一致，update_checker 按这个名字匹配）
- release 的 body 即为「更新说明」（横幅「查看说明」按钮跳的就是这个页面）

## 4. 后端实现

### 4.1 `app/integrations/github_releases.py`

**职责**：调 GitHub Releases API，返回归一化的「原始 release 信息」。不做版本比较、不做业务判断。

**接口**：

```python
class ReleaseRaw:
    tag_name: str          # 形如 "v0.2.0"
    release_url: str       # html_url
    notes: str             # body（Markdown 原文）
    download_url: str | None  # assets[] 中 name == ASSET_NAME 的 browser_download_url；找不到则 None

class GitHubReleaseError(Exception): ...

async def fetch_latest_release(owner: str, repo: str, asset_name: str) -> ReleaseRaw:
    """GET https://api.github.com/repos/{owner}/{repo}/releases/latest
    超时 5s，无认证。
    HTTP 4xx/5xx、网络错误、超时、解析异常 → 抛 GitHubReleaseError。
    200 但 tag_name 缺失 → 抛 GitHubReleaseError。
    200 但 assets 里没有 asset_name → 返回 ReleaseRaw，download_url=None。
    """
```

**鲁棒性**：
- 用 `httpx.AsyncClient(timeout=5.0)`，不复用全局 client（启动期一次性请求，无必要）
- 不传 token（公开仓库），User-Agent 显式设为常量 `capcut_helper`（GitHub API 要求设 UA，不强制要求版本号）

### 4.2 `app/services/update_checker.py`

**职责**：编排「取最新 release → 比较版本 → 归一化业务字段」，统一兜底错误。

```python
GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"
ASSET_NAME = "capcut_helper.zip"

async def check_for_update(current_version: str) -> UpdateInfo:
    try:
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO, ASSET_NAME)
    except GitHubReleaseError as e:
        return UpdateInfo(
            current_version=current_version,
            has_update=False,
            error=str(e),
        )

    latest = _strip_v_prefix(raw.tag_name)   # "v0.2.0" → "0.2.0"
    has_update = _is_newer(latest, current_version)

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        has_update=has_update,
        release_url=raw.release_url,
        download_url=raw.download_url,
        notes=raw.notes,
    )
```

**版本比较算法 `_is_newer(latest, current)`**：

1. 尝试 `packaging.version.Version(latest) > Version(current)`
2. 任一参数不符合 PEP 440 / SemVer → `packaging.version.InvalidVersion` → 回退到字符串相等比较：`latest != current` 即认为有更新

> 字符串回退的语义偏宽松（任何不等都视为更新），目的是「极端命名情况下不崩溃」而不是「精确判断」。发版规范要求 tag 用 `v{semver}`，正常情况走不到回退路径。

### 4.3 `app/api/update.py`

```python
@router.get("/update/check", response_model=UpdateCheckResponse)
async def check_update(request: Request):
    info = await check_for_update(request.app.state.version)
    return {"code": 0, "message": "ok", "data": info}
```

挂到 `app/api/router.py`，前缀 `/api/v1`。**任何错误都不应让 FastAPI 返回 5xx**——service 已经把异常吃掉、返回带 `error` 字段的 `UpdateInfo`，端点永远 200。

### 4.4 `app/schemas/update.py`

```python
class UpdateInfo(BaseModel):
    current_version: str
    latest_version: str | None = None
    has_update: bool
    release_url: str | None = None
    download_url: str | None = None
    notes: str | None = None
    error: str | None = None

class UpdateCheckResponse(BaseModel):
    code: int
    message: str
    data: UpdateInfo
```

### 4.5 `app/native/bridge.py` — 加 `open_url`

```python
def open_url(self, url: str) -> None:
    """用系统默认浏览器打开 URL。"""
    import webbrowser
    webbrowser.open(url)
```

`webbrowser` 是 Python 标准库，跨平台自动选默认浏览器。

**为什么不让前端用 `<a target="_blank">`？** pywebview 默认在 webview 窗口内打开链接，不会跳系统浏览器；统一走 NativeBridge 保证体验一致（点了链接 → 系统浏览器开新标签）。

## 5. 前端实现

### 5.1 `src/api/client.js` — 加 `getUpdateInfo`

```js
export const getUpdateInfo = () => request('/update/check')
```

返回结构与后端 `UpdateInfo` 一一对应。失败时（请求异常或 `code !== 0`）按现有 `request()` 约定抛 Error，调用方 catch 后视作「无更新」、不挂横幅。

### 5.2 `src/api/bridge.js` — 加 `openUrl`

```js
export async function openUrl(url) {
  if (!isBridgeAvailable()) {
    window.open(url, '_blank')   // 浏览器开发态降级（npm run dev）
    return
  }
  await window.pywebview.api.open_url(url)
}
```

降级路径保证 `npm run dev` 在 Vite dev server 里也能调试 UpdateBanner。

### 5.3 `src/components/UpdateBanner.jsx`（新）

**渲染规则**：

- mount 时调 `getUpdateInfo()`
- `has_update === true` → 渲染横幅
- 其它任何情况（`has_update === false`、抛错）→ 返回 `null`，不渲染

**横幅形态**（antd `Alert` + action，仿 `DraftRootBanner`）：

```
┌─────────────────────────────────────────────────────────────┐
│ ℹ 发现新版本 v0.2.0（当前 v0.1.0）                          │
│                              [查看说明] [直接下载] [×]      │
└─────────────────────────────────────────────────────────────┘
```

按钮行为：
- 「查看说明」→ `openUrl(release_url)`
- 「直接下载」→ `openUrl(download_url)`
  - `download_url == null`（release 没传 zip 资产）→ 按钮 disabled，hover tooltip：「该 release 未提供下载资产，请用『查看说明』到 release 页查看」
- 「×」→ 组件内 `useState` 控制本次启动隐藏，不持久化

主按钮：「直接下载」`type="primary"`，「查看说明」default。

### 5.4 `src/components/StatusBar.jsx` — 加版本号

现有左侧文案 `● 服务运行中 · 端口 9527`，扩展为：

```
● 服务运行中 · 端口 9527 · v0.1.0    最近导入请求：3 分钟前
```

实现：从已有 `health` state 读 `health.version` 拼字符串。**零新增网络请求**（已经在 5s 轮询 `getHealth`）。`health == null`（服务未就绪）时不显示版本号片段。

### 5.5 `src/App.jsx` — 挂载 UpdateBanner

```jsx
<StatusBar />
<DraftRootBanner ... />
<UpdateBanner />            {/* 新增 */}
<div style={{ flex: 1, overflow: 'auto', padding: '8px 16px' }}>
  <Tabs ... />
</div>
```

**顺序**：DraftRootBanner 是「必须先配草稿目录」的硬性引导，优先级最高；UpdateBanner 是软性提示，放下一行。两者都能消失，不挤压主内容时整体扁平。

### 5.6 启动时调用时序

```
App mount
  ├── StatusBar mount → getHealth() (持续 5s 轮询)
  ├── DraftRootBanner mount → 自检逻辑
  └── UpdateBanner mount → getUpdateInfo() (单次)
                              │
                              ├── 成功 has_update=true → 渲染横幅
                              ├── 成功 has_update=false → 返回 null
                              └── 失败 → console.warn + 返回 null
```

UpdateBanner 自处理所有错误状态，不向上抛，App.jsx 不感知失败。

## 6. 错误处理矩阵

| 失败场景 | 后端行为 | 前端行为 | 用户感知 |
|---|---|---|---|
| 无网络 / GitHub DNS 失败 | `httpx.ConnectError` → service 返回 `{has_update:false, error:"network"}` | catch 后不渲染横幅 | 无（静默） |
| GitHub API 5xx / 超时 | 同上，`error` 记原因 | 同上 | 无 |
| GitHub API 429（限速） | 同上 | 同上 | 无 |
| 200 但 `tag_name` 非 SemVer | service 回退到字符串相等比较 | 不等就提示 has_update | 可能误报「有更新」（罕见，发版规范可控） |
| 200 + 有更新 + 无 `capcut_helper.zip` 资产 | `download_url=None`，`has_update=true` | 渲染横幅，禁用「直接下载」按钮 | 看到横幅，只能点「查看说明」 |
| 本地端点 `/api/v1/update/check` 5xx（不应发生） | —— | catch 后不渲染横幅 | 无 |

**核心原则**：任何错误都不打扰用户、不阻塞主流程。helper 的主用途是接收外部草稿请求，更新提示是锦上添花。

## 7. 测试范围

### 7.1 后端（pytest + respx）

- `tests/integrations/test_github_releases.py`
  - 200 正常响应 → 解析正确
  - 200 但 assets 数组里没有 `capcut_helper.zip` → `download_url=None`
  - 200 但响应体缺 `tag_name` → 抛 `GitHubReleaseError`
  - 404 / 500 / timeout / 网络错误 → 抛 `GitHubReleaseError`
- `tests/services/test_update_checker.py`
  - 当前版本 < 远端 → `has_update=true`
  - 当前版本 == 远端 → `has_update=false`
  - 当前版本 > 远端（本地比线上新）→ `has_update=false`
  - 远端 tag 带 `v` 前缀正常去除
  - 远端 tag 不符合 SemVer（如 `release-2026-05`）→ 回退字符串比较
  - `fetch_latest_release` 抛错 → 返回 `has_update=false, error=...`
- `tests/api/test_update.py`
  - 端点返回 `{code:0, message:"ok", data:UpdateInfo}` 信封格式
  - service 抛任何错都返回 HTTP 200（不应让 FastAPI 5xx）

### 7.2 前端（Vitest + jsdom）

- `src/components/UpdateBanner.test.jsx`
  - `has_update=true` → 渲染横幅文本和两个按钮
  - `has_update=false` → 不渲染
  - `getUpdateInfo` 抛错 → 不渲染
  - `download_url=null` → 「直接下载」按钮 disabled
  - 点「×」→ 横幅消失
  - 点按钮 → 触发 `openUrl` mock，参数正确
- `src/api/client.test.js` 加一条 `getUpdateInfo` 快速断言
- StatusBar 若有现有测试，更新断言包含 `v0.1.0` 字段；无则不补

## 8. 验收标准

1. 改 `app/__init__.py::__version__ = "0.1.1"` 后：
   - `uv run python -c "import importlib.metadata; print(importlib.metadata.version('capcut-helper-backend'))"` 输出 `0.1.1`
   - 启动 helper，`/api/v1/health` 返回的 `version` 是 `0.1.1`
2. 启动 helper，状态栏左侧可见 `v0.1.x`
3. GitHub Release 打一个比当前高的 tag（如本地 0.1.0 → release `v0.2.0`），并附 `capcut_helper.zip` 资产，启动 helper → 横幅显示「发现新版本 v0.2.0（当前 v0.1.0）」
4. 点「查看说明」→ 系统默认浏览器打开 release 页
5. 点「直接下载」→ 系统默认浏览器开始下载 `capcut_helper.zip`
6. 点「×」→ 横幅消失；重启 helper 后横幅再次出现（不持久化「跳过」）
7. 拔网线后启动 helper → 无横幅、无报错弹窗，主流程（草稿提交、列表）正常
8. release 没传 `capcut_helper.zip` 资产 → 横幅出现，「直接下载」disabled + tooltip
9. 所有新增测试在 `uv run pytest` 和 `npm run test` 中绿
10. CALLER_GUIDE.md §5.1 字段说明与代码实际返回字段一致

## 9. 已知后续项（不在本 spec）

- 多平台资产（`capcut_helper-mac-arm64.zip` / `-mac-x64.zip` / `-win.zip`）：等 Plan 3 §9 中 Intel Mac / Windows 打包推进后再扩展资产名匹配规则
- CI 自动打包 + 自动发 release：手动流程稳定后再做
- 「跳过此版本」持久化（localStorage）：等真实使用反馈再决定是否补
