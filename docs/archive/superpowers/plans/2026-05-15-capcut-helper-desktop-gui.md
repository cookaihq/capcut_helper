# capcut_helper 桌面 GUI Implementation Plan（Plan 2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 capcut_helper 加上桌面 GUI——一个跑在 pywebview 窗口里的 React 监控/设置面板，并补齐 GUI 所需的后端接口。

**Architecture:** 后端先补 6 项（`GET /tasks` 列表接口、`TaskState` 加 `draft_name`/`created_at`、`/health` 加 `last_draft_request_at`、`server.py` 静态托管、`main.py` 重构为「uvicorn 后台守护线程 + pywebview 主线程窗口」、`app/native/bridge.py` 原生桥）。前端是 `capcut_helper/frontend/` 下的 React + Vite + Ant Design 5 应用：顶部标签三视图（活动/草稿/设置）+ 常驻状态栏 + 引导横幅，纯通过 `/api/v1` HTTP API 与后端通信，系统外壳操作走 pywebview js_api 桥。

**Tech Stack:** 后端 Python 3.11+ / FastAPI / pywebview / pytest（沿用 Plan 1）。前端 React 18 / Vite / Ant Design 5 / Vitest。包管理：后端 uv，前端 npm。

**Plan scope:** 这是 capcut_helper 的 **Plan 2（共 3 个）**。Plan 1（后端本地服务）已实现并合入 `main`。本计划覆盖设计文档第 12 节「桌面 GUI 设计」。**Plan 3**（跨平台打包：PyInstaller、Windows 实测、分发）是后续单独计划，不在本计划内。

**前置说明：**
- 设计文档：`capcut_helper/docs/superpowers/specs/2026-05-14-capcut-helper-local-service-design.md`，重点是第 12 节。
- git 提交身份已配置为 repo-local 的 cookaihq，正常 `git commit` 即可。直接在 `main` 分支上做（Plan 1 已合入 main，无独立分支）。
- 后端命令工作目录为 `capcut_helper/backend/`；前端命令工作目录为 `capcut_helper/frontend/`。
- 后端 `pytest-asyncio` 配了 `asyncio_mode = "auto"`，`async def test_...` 无需显式 marker。
- 已确认的 pyJianYingDraft / pywebview / 剪映路径事实：
  - pywebview API：`webview.create_window(title, url, js_api=None, width, height, ...)`；`webview.start(func=None, args=None, debug=False)` 在主线程跑 GUI 循环；`js_api` 对象的方法经 `window.pywebview.api.<方法>()` 调用、返回值为 Promise，只能返回基本类型；`window.create_file_dialog(dialog_type=webview.FOLDER_DIALOG)` 返回选中路径元组或 `None`。
  - 剪映默认草稿目录：macOS `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`；Windows `%USERPROFILE%\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`。两者都可用 `Path.home()` 拼出。
- 后端现有相关代码（Plan 1 产物，本计划会改）：`app/core/tasks.py`（`TaskState` dataclass：`id/status/progress/result/error` + `to_dict()`；`TaskRegistry.create()/get()/update()`；模块级单例 `registry`）、`app/api/tasks.py`（`GET /tasks/{task_id}`）、`app/api/drafts.py`（`POST/GET /drafts`）、`app/api/health.py`、`app/server.py`（`create_app(port)`）、`app/main.py`（`uvicorn.run` 阻塞）。

---

## File Structure

### 后端改动（`capcut_helper/backend/`）

| 文件 | 改动 |
|------|------|
| `pyproject.toml` | 新增依赖 `pywebview` |
| `app/core/tasks.py` | 改：`TaskState` 加 `draft_name`/`created_at`；`TaskRegistry.create(draft_name)` 签名变更并设 `created_at`；新增 `TaskRegistry.list()` |
| `app/api/tasks.py` | 改：新增 `GET /tasks` 列表路由（与现有 `GET /tasks/{task_id}` 同文件） |
| `app/api/drafts.py` | 改：`registry.create(spec.draft_name)`；`POST /drafts` 记录 `app.state.last_draft_request_at` |
| `app/api/health.py` | 改：响应 `data` 加 `last_draft_request_at` |
| `app/server.py` | 改：`create_app` 初始化 `app.state.last_draft_request_at=None`；若 `frontend/dist` 存在则 `StaticFiles` 挂载到 `/` |
| `app/native/__init__.py` | 新建：空包标记 |
| `app/native/bridge.py` | 新建：`NativeBridge` pywebview js_api 类（`pick_folder`/`reveal_in_os`/`detect_draft_root`） |
| `app/main.py` | 改：重构为 uvicorn 后台守护线程 + 主线程 pywebview 窗口 |
| `tests/test_task_registry.py` | 改：适配 `create(draft_name)` 新签名，加 `list()` 测试 |
| `tests/test_api.py` | 改：加 `GET /tasks`、`/health` 新字段的测试 |
| `tests/test_native_bridge.py` | 新建：`detect_draft_root` 路径推断逻辑测试 |

### 前端（`capcut_helper/frontend/`，全新）

```
capcut_helper/frontend/
├── package.json              # React 18 / Vite / AntD 5 / Vitest
├── vite.config.js            # React 插件、dev server 端口、/api 代理、Vitest 配置
├── index.html                # Vite 入口 HTML
├── src/
│   ├── main.jsx              # React 挂载入口
│   ├── App.jsx               # 外壳：状态栏 + 引导横幅 + 顶部标签
│   ├── api/
│   │   ├── client.js         # /api/v1 fetch 封装
│   │   └── client.test.js    # Vitest
│   │   ├── bridge.js         # window.pywebview.api 封装 + 特性检测
│   │   └── bridge.test.js    # Vitest
│   ├── utils/
│   │   ├── time.js           # 相对时间格式化
│   │   ├── time.test.js      # Vitest
│   │   ├── taskCard.js       # 任务卡片状态派生
│   │   └── taskCard.test.js  # Vitest
│   ├── components/
│   │   ├── StatusBar.jsx     # 常驻状态栏
│   │   └── DraftRootBanner.jsx  # 引导横幅
│   └── views/
│       ├── ActivityView.jsx  # 活动视图（轮询 GET /tasks）
│       ├── DraftsView.jsx    # 草稿视图（GET /drafts）
│       └── SettingsView.jsx  # 设置视图（GET/PUT /config）
```

---

## Task 1: TaskState 扩展与任务注册表

**Files:**
- Modify: `capcut_helper/backend/app/core/tasks.py`
- Modify: `capcut_helper/backend/app/api/drafts.py`
- Test: `capcut_helper/backend/tests/test_task_registry.py`

`TaskState` 增加 `draft_name` 和 `created_at`；`TaskRegistry.create` 接收 `draft_name` 并自动记 `created_at`；新增 `list()` 返回所有任务。`api/drafts.py` 是 `create()` 的调用方，同步更新。

- [ ] **Step 1: 改写失败测试**

把 `capcut_helper/backend/tests/test_task_registry.py` 整体替换为：

```python
from app.core.tasks import TaskRegistry


def test_create_returns_unique_ids_and_records_metadata():
    reg = TaskRegistry()
    a = reg.create("草稿A")
    b = reg.create("草稿B")
    assert a.id != b.id
    assert a.status == "pending"
    assert a.progress == 0
    assert a.draft_name == "草稿A"
    assert isinstance(a.created_at, float)
    assert a.created_at > 0


def test_get_returns_state_or_none():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    assert reg.get(st.id) is st
    assert reg.get("missing") is None


def test_update_mutates_fields():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    reg.update(st.id, status="done", progress=100, result="/path/to/draft")
    fresh = reg.get(st.id)
    assert fresh.status == "done"
    assert fresh.progress == 100
    assert fresh.result == "/path/to/draft"


def test_list_returns_all_tasks():
    reg = TaskRegistry()
    a = reg.create("草稿A")
    b = reg.create("草稿B")
    tasks = reg.list()
    assert {t.id for t in tasks} == {a.id, b.id}


def test_to_dict_includes_new_fields():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    d = st.to_dict()
    assert d["draft_name"] == "草稿A"
    assert "created_at" in d
    assert set(d.keys()) == {"id", "status", "progress", "result", "error", "draft_name", "created_at"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/backend && uv run pytest tests/test_task_registry.py -v`
Expected: FAIL，`TypeError: create() missing 1 required positional argument` 或 `AttributeError`（`draft_name` 不存在）

- [ ] **Step 3: 改 tasks.py**

把 `capcut_helper/backend/app/core/tasks.py` 整体替换为：

```python
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

TaskStatus = Literal["pending", "downloading", "building", "done", "failed"]


@dataclass
class TaskState:
    id: str
    draft_name: str
    created_at: float
    status: TaskStatus = "pending"
    progress: int = 0
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}

    def create(self, draft_name: str) -> TaskState:
        task_id = uuid.uuid4().hex
        state = TaskState(id=task_id, draft_name=draft_name, created_at=time.time())
        self._tasks[task_id] = state
        return state

    def get(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def list(self) -> list[TaskState]:
        return list(self._tasks.values())

    def update(self, task_id: str, **fields) -> TaskState:
        state = self._tasks[task_id]
        for key, value in fields.items():
            setattr(state, key, value)
        return state


# 进程级单例：API 层和后台任务共用同一个注册表
registry = TaskRegistry()
```

> 注：`field` 在最终代码里未直接用到，可不导入；若 linter 报未使用，删掉 `field` 即可。为避免歧义，这里直接给不含 `field` 的版本——把上面 `from dataclasses import asdict, dataclass, field` 改为 `from dataclasses import asdict, dataclass`。

- [ ] **Step 4: 改 api/drafts.py 的 create 调用**

`capcut_helper/backend/app/api/drafts.py` 里 `POST /drafts` 处理函数中，把 `state = registry.create()` 改为 `state = registry.create(spec.draft_name)`。其余不动。改完后该函数为：

```python
@router.post("/drafts")
async def create_draft(spec: TimelineSpec):
    state = registry.create(spec.draft_name)
    task = asyncio.create_task(run_draft_task(state.id, spec))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"code": 0, "message": "ok", "data": {"task_id": state.id}}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd capcut_helper/backend && uv run pytest tests/test_task_registry.py tests/test_api.py tests/test_draft_service.py tests/test_e2e_draft.py -v`
Expected: PASS（全部通过——`create` 新签名只有 `api/drafts.py` 一处调用方，已同步）

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/core/tasks.py capcut_helper/backend/app/api/drafts.py capcut_helper/backend/tests/test_task_registry.py
git commit -m "feat(capcut_helper): TaskState 加 draft_name/created_at,registry 加 list()"
```

---

## Task 2: GET /api/v1/tasks 列表接口

**Files:**
- Modify: `capcut_helper/backend/app/api/tasks.py`
- Test: `capcut_helper/backend/tests/test_api.py`

新增 `GET /api/v1/tasks`——列出所有任务，按 `created_at` 时间倒序。

- [ ] **Step 1: 加失败测试**

在 `capcut_helper/backend/tests/test_api.py` 末尾追加：

```python
def test_get_tasks_lists_all_descending(client, monkeypatch):
    # 直接往 registry 塞两个任务，验证列表接口按 created_at 倒序返回
    from app.core.tasks import registry
    older = registry.create("旧草稿")
    newer = registry.create("新草稿")
    # 确保 newer 的 created_at 更大
    registry.update(newer.id, status="done", progress=100)

    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 200
    data = resp.json()["data"]
    ids = [t["id"] for t in data]
    # 倒序：newer 在 older 前面
    assert ids.index(newer.id) < ids.index(older.id)
    # 每个任务对象字段齐全
    sample = next(t for t in data if t["id"] == newer.id)
    assert sample["draft_name"] == "新草稿"
    assert sample["status"] == "done"
    assert "created_at" in sample
```

> 说明：`client` fixture 和 `registry` 是进程级单例，测试间会累积任务——本测试只断言相对顺序和自己塞进去的任务，不假设总数，因此不受其他测试污染。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/backend && uv run pytest tests/test_api.py::test_get_tasks_lists_all_descending -v`
Expected: FAIL，HTTP 404（`GET /tasks` 路由还不存在，被 `/tasks/{task_id}` 也匹配不上）

- [ ] **Step 3: 加 GET /tasks 路由**

把 `capcut_helper/backend/app/api/tasks.py` 整体替换为：

```python
from fastapi import APIRouter

from app.core.exceptions import TaskNotFound
from app.core.tasks import registry

router = APIRouter()


@router.get("/tasks")
async def list_tasks():
    tasks = sorted(registry.list(), key=lambda t: t.created_at, reverse=True)
    return {"code": 0, "message": "ok", "data": [t.to_dict() for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    state = registry.get(task_id)
    if state is None:
        raise TaskNotFound(f"任务不存在: {task_id}")
    return {"code": 0, "message": "ok", "data": state.to_dict()}
```

> 路由顺序：`/tasks` 在 `/tasks/{task_id}` 之前注册，FastAPI 会优先精确匹配 `/tasks`，不会被 `{task_id}` 抢走。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd capcut_helper/backend && uv run pytest tests/test_api.py -v`
Expected: PASS（含新测试和原有的 `test_get_task_404_for_unknown_id` 等）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/api/tasks.py capcut_helper/backend/tests/test_api.py
git commit -m "feat(capcut_helper): 新增 GET /api/v1/tasks 任务列表接口"
```

---

## Task 3: /health 加 last_draft_request_at

**Files:**
- Modify: `capcut_helper/backend/app/server.py`
- Modify: `capcut_helper/backend/app/api/drafts.py`
- Modify: `capcut_helper/backend/app/api/health.py`
- Test: `capcut_helper/backend/tests/test_api.py`

`POST /drafts` 被调用时在 `app.state.last_draft_request_at` 记一个 epoch 时间戳；`GET /health` 返回它。

- [ ] **Step 1: 加失败测试**

在 `capcut_helper/backend/tests/test_api.py` 末尾追加：

```python
def test_health_last_draft_request_at_updates_after_post(client, monkeypatch):
    # 初始为 None
    assert client.get("/api/v1/health").json()["data"]["last_draft_request_at"] is None

    # POST 一次 drafts（monkeypatch 掉后台任务，只关心时间戳被记上）
    async def _noop(task_id, spec):
        return None
    monkeypatch.setattr("app.api.drafts.run_draft_task", _noop)
    client.post("/api/v1/drafts", json=_valid_spec_body())

    ts = client.get("/api/v1/health").json()["data"]["last_draft_request_at"]
    assert isinstance(ts, (int, float))
    assert ts > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/backend && uv run pytest tests/test_api.py::test_health_last_draft_request_at_updates_after_post -v`
Expected: FAIL，`KeyError: 'last_draft_request_at'`（health 响应里还没这个字段）

- [ ] **Step 3: server.py 初始化 app.state**

`capcut_helper/backend/app/server.py` 的 `create_app` 里，在 `app.state.version = __version__` 后面加一行 `app.state.last_draft_request_at = None`。改完后 `create_app` 开头为：

```python
def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None
    ...
```

（`...` 表示 `create_app` 后续 CORS、异常处理、路由那部分**保持不动**。）

- [ ] **Step 4: drafts.py 记录时间戳**

`capcut_helper/backend/app/api/drafts.py`：给 `POST /drafts` 处理函数加 `request: Request` 参数并记录时间戳。需要 `from fastapi import APIRouter, Request` 和 `import time`。改完后该函数为：

```python
@router.post("/drafts")
async def create_draft(spec: TimelineSpec, request: Request):
    request.app.state.last_draft_request_at = time.time()
    state = registry.create(spec.draft_name)
    task = asyncio.create_task(run_draft_task(state.id, spec))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"code": 0, "message": "ok", "data": {"task_id": state.id}}
```

文件顶部 import 区相应改为（保留原有其他 import）：

```python
import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Request
```

- [ ] **Step 5: health.py 返回字段**

把 `capcut_helper/backend/app/api/health.py` 整体替换为：

```python
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "service": "capcut_helper",
            "version": request.app.state.version,
            "port": request.app.state.port,
            "last_draft_request_at": request.app.state.last_draft_request_at,
        },
    }
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd capcut_helper/backend && uv run pytest tests/test_api.py -v`
Expected: PASS（含新测试；原有 `test_health_returns_service_identity` 也仍通过——它只断言 `service`/`port`/`version` 存在，不排斥新字段）

- [ ] **Step 7: Commit**

```bash
git add capcut_helper/backend/app/server.py capcut_helper/backend/app/api/drafts.py capcut_helper/backend/app/api/health.py capcut_helper/backend/tests/test_api.py
git commit -m "feat(capcut_helper): /health 暴露最近导入请求时间"
```

---

## Task 4: 原生桥 app/native/bridge.py

**Files:**
- Modify: `capcut_helper/backend/pyproject.toml`
- Create: `capcut_helper/backend/app/native/__init__.py`
- Create: `capcut_helper/backend/app/native/bridge.py`
- Test: `capcut_helper/backend/tests/test_native_bridge.py`

pywebview js_api 桥类：`pick_folder`、`reveal_in_os`、`detect_draft_root`。其中 `detect_draft_root` 是纯路径推断逻辑，可单测；另两个是薄 OS 调用，手动验证。

- [ ] **Step 1: 加 pywebview 依赖**

`capcut_helper/backend/pyproject.toml` 的 `dependencies` 数组加一行 `"pywebview>=5.0"`。改完后：

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
    "pyJianYingDraft>=0.2.6",
    "platformdirs>=4.0",
    "pywebview>=5.0",
]
```

然后 Run: `cd capcut_helper/backend && uv sync`
Expected: 成功安装 pywebview（macOS 上会带上 pyobjc 相关依赖），无报错。

- [ ] **Step 2: 建 native 包标记**

创建空文件 `capcut_helper/backend/app/native/__init__.py`（内容为空）。

- [ ] **Step 3: 写失败测试**

`capcut_helper/backend/tests/test_native_bridge.py`：

```python
import sys
from pathlib import Path

from app.native.bridge import NativeBridge


def test_detect_draft_root_returns_path_when_dir_exists(tmp_path, monkeypatch):
    # 伪造 macOS 下的剪映默认目录存在
    fake_home = tmp_path
    draft_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    draft_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(draft_dir)


def test_detect_draft_root_returns_none_when_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # 空目录，剪映目录不存在
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() is None


def test_detect_draft_root_windows_path(tmp_path, monkeypatch):
    fake_home = tmp_path
    draft_dir = fake_home / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
    draft_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "win32")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(draft_dir)


def test_detect_draft_root_unsupported_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() is None
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd capcut_helper/backend && uv run pytest tests/test_native_bridge.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.native.bridge'`

- [ ] **Step 5: 实现 bridge.py**

`capcut_helper/backend/app/native/bridge.py`：

```python
import subprocess
import sys
from pathlib import Path
from typing import Optional

import webview

# 各平台剪映默认草稿目录（相对 Path.home()）
_DRAFT_ROOT_RELATIVE = {
    "darwin": "Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
    "win32": "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft",
}


class NativeBridge:
    """pywebview js_api 桥：暴露给前端 window.pywebview.api.* 的系统外壳操作。
    window 在 create_window 之后由 main.py 赋值。"""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> Optional[str]:
        """打开文件夹选择对话框，返回选中目录路径；用户取消返回 None。"""
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def reveal_in_os(self, path: str) -> None:
        """在系统文件管理器里定位该路径。"""
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", path], check=False)

    def detect_draft_root(self) -> Optional[str]:
        """按平台推断剪映默认草稿目录，存在则返回路径字符串，否则 None。"""
        relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
        if relative is None:
            return None
        candidate = Path.home() / relative
        return str(candidate) if candidate.is_dir() else None
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd capcut_helper/backend && uv run pytest tests/test_native_bridge.py -v`
Expected: PASS（4 passed）

- [ ] **Step 7: Commit**

```bash
git add capcut_helper/backend/pyproject.toml capcut_helper/backend/uv.lock capcut_helper/backend/app/native capcut_helper/backend/tests/test_native_bridge.py
git commit -m "feat(capcut_helper): pywebview 原生桥(选目录/在访达打开/探测草稿目录)"
```

---

## Task 5: 前端脚手架

**Files:**
- Create: `capcut_helper/frontend/package.json`
- Create: `capcut_helper/frontend/vite.config.js`
- Create: `capcut_helper/frontend/index.html`
- Create: `capcut_helper/frontend/src/main.jsx`
- Create: `capcut_helper/frontend/src/App.jsx`（占位版，Task 9 替换为真外壳）
- Create: `capcut_helper/frontend/.gitignore`

- [ ] **Step 1: package.json**

`capcut_helper/frontend/package.json`：

```json
{
  "name": "capcut-helper-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "antd": "^5.21.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: vite.config.js**

`capcut_helper/frontend/vite.config.js`：

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3176,
    proxy: {
      // 开发期把 /api 代理到本地后端（后端默认端口 9527）
      '/api': 'http://127.0.0.1:9527',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
  },
})
```

- [ ] **Step 3: index.html**

`capcut_helper/frontend/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>capcut_helper</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: main.jsx**

`capcut_helper/frontend/src/main.jsx`：

```jsx
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(<App />)
```

- [ ] **Step 5: App.jsx（占位版）**

`capcut_helper/frontend/src/App.jsx`：

```jsx
export default function App() {
  return <div>capcut_helper</div>
}
```

- [ ] **Step 6: .gitignore**

`capcut_helper/frontend/.gitignore`：

```
node_modules/
dist/
```

- [ ] **Step 7: 安装依赖并验证**

Run: `cd capcut_helper/frontend && npm install`
Expected: 成功安装，无报错。

Run: `cd capcut_helper/frontend && npm run build`
Expected: 成功构建到 `dist/`。

Run: `cd capcut_helper/frontend && npm test`
Expected: vitest 运行，报「no test files found」（此时还没测试文件）——这是预期的，说明 vitest 配好了。

- [ ] **Step 8: Commit**

```bash
git add capcut_helper/frontend/package.json capcut_helper/frontend/package-lock.json capcut_helper/frontend/vite.config.js capcut_helper/frontend/index.html capcut_helper/frontend/src capcut_helper/frontend/.gitignore
git commit -m "chore(capcut_helper): 前端脚手架(Vite + React 18 + AntD 5 + Vitest)"
```

---

## Task 6: API client 模块

**Files:**
- Create: `capcut_helper/frontend/src/api/client.js`
- Test: `capcut_helper/frontend/src/api/client.test.js`

`/api/v1` 的 fetch 封装：统一拆 `{code,message,data}` 信封，`code !== 0` 抛错。

- [ ] **Step 1: 写失败测试**

`capcut_helper/frontend/src/api/client.test.js`：

```js
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getHealth, getTasks, putConfig } from './client.js'

afterEach(() => {
  vi.restoreAllMocks()
})

function mockFetch(body, ok = true) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    json: async () => body,
  })
}

describe('client', () => {
  it('unwraps data on success', async () => {
    mockFetch({ code: 0, message: 'ok', data: { service: 'capcut_helper' } })
    const data = await getHealth()
    expect(data).toEqual({ service: 'capcut_helper' })
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/health', undefined)
  })

  it('throws when code is non-zero', async () => {
    mockFetch({ code: 1003, message: '任务不存在', data: null })
    await expect(getTasks()).rejects.toMatchObject({ message: '任务不存在', code: 1003 })
  })

  it('putConfig sends JSON body', async () => {
    mockFetch({ code: 0, message: 'ok', data: { draft_root: '/x' } })
    await putConfig({ draft_root: '/x', port_range: [9527, 9536], cors_origins: [] })
    const [url, options] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/v1/config')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({
      draft_root: '/x',
      port_range: [9527, 9536],
      cors_origins: [],
    })
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/frontend && npx vitest run src/api/client.test.js`
Expected: FAIL，无法解析 `./client.js`

- [ ] **Step 3: 实现 client.js**

`capcut_helper/frontend/src/api/client.js`：

```js
const BASE = '/api/v1'

async function request(path, options) {
  const resp = await fetch(BASE + path, options)
  const body = await resp.json()
  if (body.code !== 0) {
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    err.data = body.data
    throw err
  }
  return body.data
}

export const getHealth = () => request('/health')
export const getTasks = () => request('/tasks')
export const getDrafts = () => request('/drafts')
export const getConfig = () => request('/config')
export const putConfig = (cfg) =>
  request('/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd capcut_helper/frontend && npx vitest run src/api/client.test.js`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/frontend/src/api/client.js capcut_helper/frontend/src/api/client.test.js
git commit -m "feat(capcut_helper): 前端 API client 封装"
```

---

## Task 7: 原生桥前端封装

**Files:**
- Create: `capcut_helper/frontend/src/api/bridge.js`
- Test: `capcut_helper/frontend/src/api/bridge.test.js`

封装 `window.pywebview.api`，带特性检测——浏览器开发环境（无 pywebview）下不报错、降级。

- [ ] **Step 1: 写失败测试**

`capcut_helper/frontend/src/api/bridge.test.js`：

```js
import { afterEach, describe, expect, it, vi } from 'vitest'
import { detectDraftRoot, isBridgeAvailable, pickFolder, revealInOs } from './bridge.js'

afterEach(() => {
  delete window.pywebview
})

describe('bridge', () => {
  it('isBridgeAvailable is false without pywebview', () => {
    expect(isBridgeAvailable()).toBe(false)
  })

  it('pickFolder returns null without bridge', async () => {
    expect(await pickFolder()).toBeNull()
  })

  it('revealInOs is a no-op without bridge', async () => {
    await expect(revealInOs('/x')).resolves.toBeUndefined()
  })

  it('delegates to window.pywebview.api when available', async () => {
    window.pywebview = {
      api: {
        pick_folder: vi.fn().mockResolvedValue('/picked'),
        reveal_in_os: vi.fn().mockResolvedValue(undefined),
        detect_draft_root: vi.fn().mockResolvedValue('/detected'),
      },
    }
    expect(isBridgeAvailable()).toBe(true)
    expect(await pickFolder()).toBe('/picked')
    await revealInOs('/some/path')
    expect(window.pywebview.api.reveal_in_os).toHaveBeenCalledWith('/some/path')
    expect(await detectDraftRoot()).toBe('/detected')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/frontend && npx vitest run src/api/bridge.test.js`
Expected: FAIL，无法解析 `./bridge.js`

- [ ] **Step 3: 实现 bridge.js**

`capcut_helper/frontend/src/api/bridge.js`：

```js
// 封装 pywebview js_api 桥。浏览器开发环境下 window.pywebview 不存在，做特性检测降级。

export function isBridgeAvailable() {
  return typeof window !== 'undefined' && !!(window.pywebview && window.pywebview.api)
}

export async function pickFolder() {
  if (!isBridgeAvailable()) return null
  return window.pywebview.api.pick_folder()
}

export async function revealInOs(path) {
  if (!isBridgeAvailable()) return
  await window.pywebview.api.reveal_in_os(path)
}

export async function detectDraftRoot() {
  if (!isBridgeAvailable()) return null
  return window.pywebview.api.detect_draft_root()
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd capcut_helper/frontend && npx vitest run src/api/bridge.test.js`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/frontend/src/api/bridge.js capcut_helper/frontend/src/api/bridge.test.js
git commit -m "feat(capcut_helper): 前端原生桥封装(带特性检测降级)"
```

---

## Task 8: 纯逻辑工具（相对时间 + 任务卡片状态）

**Files:**
- Create: `capcut_helper/frontend/src/utils/time.js`
- Test: `capcut_helper/frontend/src/utils/time.test.js`
- Create: `capcut_helper/frontend/src/utils/taskCard.js`
- Test: `capcut_helper/frontend/src/utils/taskCard.test.js`

- [ ] **Step 1: 写失败测试**

`capcut_helper/frontend/src/utils/time.test.js`：

```js
import { describe, expect, it } from 'vitest'
import { relativeTime } from './time.js'

describe('relativeTime', () => {
  const now = 1_000_000 // 任意 now（秒）

  it('shows 刚刚 within a minute', () => {
    expect(relativeTime(now - 30, now)).toBe('刚刚')
  })
  it('shows minutes', () => {
    expect(relativeTime(now - 120, now)).toBe('2 分钟前')
  })
  it('shows hours', () => {
    expect(relativeTime(now - 7200, now)).toBe('2 小时前')
  })
  it('shows days', () => {
    expect(relativeTime(now - 172800, now)).toBe('2 天前')
  })
  it('clamps future timestamps to 刚刚', () => {
    expect(relativeTime(now + 100, now)).toBe('刚刚')
  })
})
```

`capcut_helper/frontend/src/utils/taskCard.test.js`：

```js
import { describe, expect, it } from 'vitest'
import { taskDisplay } from './taskCard.js'

describe('taskDisplay', () => {
  it('marks downloading as in-progress', () => {
    const d = taskDisplay({ status: 'downloading' })
    expect(d.inProgress).toBe(true)
    expect(d.isDone).toBe(false)
    expect(d.isFailed).toBe(false)
    expect(d.label).toBe('下载素材中')
  })
  it('marks done', () => {
    const d = taskDisplay({ status: 'done' })
    expect(d.inProgress).toBe(false)
    expect(d.isDone).toBe(true)
    expect(d.label).toBe('已完成')
  })
  it('marks failed', () => {
    const d = taskDisplay({ status: 'failed' })
    expect(d.isFailed).toBe(true)
    expect(d.label).toBe('失败')
  })
  it('handles pending and building', () => {
    expect(taskDisplay({ status: 'pending' }).inProgress).toBe(true)
    expect(taskDisplay({ status: 'building' }).label).toBe('生成草稿中')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/frontend && npx vitest run src/utils/`
Expected: FAIL，无法解析 `./time.js` / `./taskCard.js`

- [ ] **Step 3: 实现 time.js**

`capcut_helper/frontend/src/utils/time.js`：

```js
// 把 epoch 秒数格式化成中文相对时间。now 默认取当前时间（秒），可注入便于测试。
export function relativeTime(epochSeconds, now = Date.now() / 1000) {
  const diff = Math.max(0, now - epochSeconds)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}
```

- [ ] **Step 4: 实现 taskCard.js**

`capcut_helper/frontend/src/utils/taskCard.js`：

```js
// 从后端任务对象派生「活动」视图卡片要用的展示状态。

const STATUS_LABEL = {
  pending: '等待中',
  downloading: '下载素材中',
  building: '生成草稿中',
  done: '已完成',
  failed: '失败',
}

const IN_PROGRESS = ['pending', 'downloading', 'building']

export function taskDisplay(task) {
  return {
    label: STATUS_LABEL[task.status] || task.status,
    inProgress: IN_PROGRESS.includes(task.status),
    isDone: task.status === 'done',
    isFailed: task.status === 'failed',
  }
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd capcut_helper/frontend && npx vitest run src/utils/`
Expected: PASS（9 passed）

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/frontend/src/utils
git commit -m "feat(capcut_helper): 前端纯逻辑工具(相对时间 + 任务卡片状态派生)"
```

---

## Task 9: App 外壳（状态栏 + 引导横幅 + 顶部标签）

**Files:**
- Create: `capcut_helper/frontend/src/components/StatusBar.jsx`
- Create: `capcut_helper/frontend/src/components/DraftRootBanner.jsx`
- Modify: `capcut_helper/frontend/src/App.jsx`
- Create: `capcut_helper/frontend/src/views/ActivityView.jsx`（占位，Task 10 实现）
- Create: `capcut_helper/frontend/src/views/DraftsView.jsx`（占位，Task 11 实现）
- Create: `capcut_helper/frontend/src/views/SettingsView.jsx`（占位，Task 12 实现）

这是 UI 组件任务——不走 TDD，按「实现 → dev server 手动验证 → 提交」。

- [ ] **Step 1: 三个视图占位文件**

`capcut_helper/frontend/src/views/ActivityView.jsx`：

```jsx
export default function ActivityView() {
  return <div>活动</div>
}
```

`capcut_helper/frontend/src/views/DraftsView.jsx`：

```jsx
export default function DraftsView() {
  return <div>草稿</div>
}
```

`capcut_helper/frontend/src/views/SettingsView.jsx`：

```jsx
export default function SettingsView() {
  return <div>设置</div>
}
```

- [ ] **Step 2: StatusBar.jsx**

`capcut_helper/frontend/src/components/StatusBar.jsx`：

```jsx
import { useEffect, useState } from 'react'
import { getHealth } from '../api/client.js'
import { relativeTime } from '../utils/time.js'

export default function StatusBar() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const load = () => getHealth().then(setHealth).catch(() => setHealth(null))
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const online = !!health
  const lastReq = health && health.last_draft_request_at

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 16px',
        background: '#1f1f1f',
        color: '#bbb',
        fontSize: 12,
      }}
    >
      <span>
        <span style={{ color: online ? '#52c41a' : '#ff4d4f' }}>●</span>{' '}
        {online ? `服务运行中 · 端口 ${health.port}` : '连接本地服务中…'}
      </span>
      <span>
        {lastReq
          ? `最近导入请求：${relativeTime(lastReq)}`
          : '尚无导入请求'}
      </span>
    </div>
  )
}
```

- [ ] **Step 3: DraftRootBanner.jsx**

`capcut_helper/frontend/src/components/DraftRootBanner.jsx`：

```jsx
import { Alert, Button, Space } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, putConfig } from '../api/client.js'
import { detectDraftRoot } from '../api/bridge.js'

// draft_root 未配置时显示引导横幅。配好后回调 onConfigured 通知父组件并自行隐藏。
export default function DraftRootBanner({ onGoToSettings, onConfigured }) {
  const [needsSetup, setNeedsSetup] = useState(false)
  const [detected, setDetected] = useState(null)

  useEffect(() => {
    getConfig()
      .then(async (cfg) => {
        if (cfg.draft_root) {
          setNeedsSetup(false)
          return
        }
        setNeedsSetup(true)
        const path = await detectDraftRoot()
        if (path) setDetected(path)
      })
      .catch(() => setNeedsSetup(false))
  }, [])

  if (!needsSetup) return null

  const useDetected = async () => {
    const cfg = await getConfig()
    await putConfig({ ...cfg, draft_root: detected })
    setNeedsSetup(false)
    onConfigured && onConfigured()
  }

  if (detected) {
    return (
      <Alert
        type="info"
        showIcon
        message={`检测到剪映草稿目录：${detected}`}
        action={
          <Space>
            <Button size="small" type="primary" onClick={useDetected}>
              使用
            </Button>
            <Button size="small" onClick={onGoToSettings}>
              手动选择
            </Button>
          </Space>
        }
      />
    )
  }

  return (
    <Alert
      type="warning"
      showIcon
      message="还没设置剪映草稿目录，导入会失败"
      action={
        <Button size="small" onClick={onGoToSettings}>
          去设置
        </Button>
      }
    />
  )
}
```

- [ ] **Step 4: App.jsx（真外壳）**

把 `capcut_helper/frontend/src/App.jsx` 整体替换为：

```jsx
import { Tabs } from 'antd'
import { useState } from 'react'
import StatusBar from './components/StatusBar.jsx'
import DraftRootBanner from './components/DraftRootBanner.jsx'
import ActivityView from './views/ActivityView.jsx'
import DraftsView from './views/DraftsView.jsx'
import SettingsView from './views/SettingsView.jsx'

export default function App() {
  const [activeTab, setActiveTab] = useState('activity')
  // bannerKey 变化时强制 DraftRootBanner 重挂载（保存配置后重新评估是否还要显示）
  const [bannerKey, setBannerKey] = useState(0)

  const items = [
    { key: 'activity', label: '活动', children: <ActivityView /> },
    { key: 'drafts', label: '草稿', children: <DraftsView /> },
    {
      key: 'settings',
      label: '设置',
      children: <SettingsView onSaved={() => setBannerKey((k) => k + 1)} />,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <StatusBar />
      <DraftRootBanner
        key={bannerKey}
        onGoToSettings={() => setActiveTab('settings')}
        onConfigured={() => setBannerKey((k) => k + 1)}
      />
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
      </div>
    </div>
  )
}
```

> 说明：`SettingsView` 在 Task 12 会接受 `onSaved` prop；Task 9 的占位版忽略 props 即可，不影响。

- [ ] **Step 5: dev server 手动验证**

先确保后端在跑：另开终端 Run `cd capcut_helper/backend && uv run python -m app.main`（Task 13 之前 `main.py` 还是 Plan 1 的阻塞版 uvicorn，能正常起在 9527；若已做 Task 13 则会开窗口，关掉窗口或直接用此服务即可）。

Run: `cd capcut_helper/frontend && npm run dev`，浏览器打开 `http://localhost:3176`。
Expected: 顶部黑色状态栏显示「● 服务运行中 · 端口 9527」和「尚无导入请求」；下面是引导横幅（若后端 draft_root 未配置）；再下面是「活动 / 草稿 / 设置」三个标签，点击能切换，内容分别是占位文字。

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/frontend/src/App.jsx capcut_helper/frontend/src/components capcut_helper/frontend/src/views
git commit -m "feat(capcut_helper): App 外壳(状态栏 + 引导横幅 + 顶部标签)"
```

---

## Task 10: 活动视图

**Files:**
- Modify: `capcut_helper/frontend/src/views/ActivityView.jsx`

轮询 `GET /tasks`，时间倒序的任务卡片列表。UI 组件任务——实现 → 手动验证 → 提交。

- [ ] **Step 1: 实现 ActivityView.jsx**

把 `capcut_helper/frontend/src/views/ActivityView.jsx` 整体替换为：

```jsx
import { Button, Card, Empty, Progress, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { getTasks } from '../api/client.js'
import { revealInOs } from '../api/bridge.js'
import { relativeTime } from '../utils/time.js'
import { taskDisplay } from '../utils/taskCard.js'

export default function ActivityView() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    const load = () => getTasks().then(setTasks).catch(() => {})
    load()
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [])

  if (tasks.length === 0) {
    return (
      <Empty description="还没有导入任务。在 ai-canvas 里排好时间线点导入，这里会显示进度。" />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {tasks.map((task) => {
        const d = taskDisplay(task)
        return (
          <Card key={task.id} size="small">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 600 }}>{task.draft_name}</span>
              <Tag color={d.isDone ? 'success' : d.isFailed ? 'error' : 'processing'}>
                {d.label}
              </Tag>
            </div>
            {d.inProgress && (
              <Progress percent={task.progress} size="small" status="active" />
            )}
            {d.isDone && (
              <div style={{ marginTop: 6, fontSize: 12 }}>
                <span style={{ color: '#999' }}>{task.result}</span>
                <Button
                  size="small"
                  type="link"
                  onClick={() => revealInOs(task.result)}
                >
                  在访达/资源管理器打开
                </Button>
              </div>
            )}
            {d.isFailed && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#ff4d4f' }}>
                {task.error}
              </div>
            )}
            <div style={{ marginTop: 4, fontSize: 12, color: '#999' }}>
              {relativeTime(task.created_at)}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: 手动验证**

后端在跑（9527）。`cd capcut_helper/frontend && npm run dev`，打开 `http://localhost:3176`，停在「活动」标签。

先验证空状态：刚启动、没任务时显示 Empty 提示。

再造一个任务验证卡片：另开终端 Run（需要后端已配置 `draft_root`，没配的话先在「设置」标签配一个存在的空目录）：

```bash
curl -X POST http://127.0.0.1:9527/api/v1/drafts -H 'Content-Type: application/json' -d '{
  "draft_name": "活动视图测试",
  "canvas": {"width": 1920, "height": 1080, "fps": 30},
  "tracks": [{"type": "video", "segments": [{"material": {"url": "https://invalid.example/x.mp4", "type": "video", "filename": "x.mp4"}, "timeline": {"start": 0, "duration": 1000000}}]}]
}'
```

Expected: 「活动」视图里 1.5 秒内出现「活动视图测试」卡片；因为素材 URL 不可达，任务会经历 进行中（进度条）→ 失败（红色错误信息）。验证：卡片显示草稿名、状态 Tag、失败时的红色 error 文本、相对时间。

- [ ] **Step 3: Commit**

```bash
git add capcut_helper/frontend/src/views/ActivityView.jsx
git commit -m "feat(capcut_helper): 活动视图(轮询任务列表 + 进度/结果卡片)"
```

---

## Task 11: 草稿视图

**Files:**
- Modify: `capcut_helper/frontend/src/views/DraftsView.jsx`

`GET /drafts` 列出草稿文件夹名，每行一个 + 「在访达打开」按钮。

- [ ] **Step 1: 实现 DraftsView.jsx**

把 `capcut_helper/frontend/src/views/DraftsView.jsx` 整体替换为：

```jsx
import { Button, Empty, List } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, getDrafts } from '../api/client.js'
import { revealInOs } from '../api/bridge.js'

export default function DraftsView() {
  const [drafts, setDrafts] = useState([])
  const [draftRoot, setDraftRoot] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([getDrafts(), getConfig()])
      .then(([names, cfg]) => {
        setDrafts(names)
        setDraftRoot(cfg.draft_root)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div>
      <Button size="small" onClick={load} loading={loading} style={{ marginBottom: 8 }}>
        刷新
      </Button>
      {drafts.length === 0 ? (
        <Empty
          description={
            draftRoot ? '草稿根目录下还没有草稿' : '未配置剪映草稿目录'
          }
        />
      ) : (
        <List
          size="small"
          bordered
          dataSource={drafts}
          renderItem={(name) => (
            <List.Item
              actions={[
                <Button
                  key="reveal"
                  size="small"
                  type="link"
                  onClick={() => revealInOs(`${draftRoot}/${name}`)}
                >
                  在访达/资源管理器打开
                </Button>,
              ]}
            >
              {name}
            </List.Item>
          )}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: 手动验证**

后端在跑（9527），且「设置」里配了一个存在的 `draft_root`。在该目录下手动建两个文件夹（`mkdir 草稿X 草稿Y`）。

`npm run dev` → 打开 `http://localhost:3176` → 切到「草稿」标签。
Expected: 列出「草稿X」「草稿Y」两行，各带「在访达/资源管理器打开」按钮；点「刷新」会重新拉取。把 `draft_root` 清空（设置页）后刷新，显示「未配置剪映草稿目录」空状态。

- [ ] **Step 3: Commit**

```bash
git add capcut_helper/frontend/src/views/DraftsView.jsx
git commit -m "feat(capcut_helper): 草稿视图(列出草稿 + 在访达打开)"
```

---

## Task 12: 设置视图

**Files:**
- Modify: `capcut_helper/frontend/src/views/SettingsView.jsx`

`GET /config` 拉表单，编辑后 `PUT /config`。`draft_root` 配「选择目录」「自动探测」按钮（走原生桥）。

- [ ] **Step 1: 实现 SettingsView.jsx**

把 `capcut_helper/frontend/src/views/SettingsView.jsx` 整体替换为：

```jsx
import { Button, Form, Input, InputNumber, Select, Space, message } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, putConfig } from '../api/client.js'
import { detectDraftRoot, isBridgeAvailable, pickFolder } from '../api/bridge.js'

export default function SettingsView({ onSaved }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const bridgeOn = isBridgeAvailable()

  useEffect(() => {
    getConfig()
      .then((cfg) =>
        form.setFieldsValue({
          draft_root: cfg.draft_root || '',
          port_start: cfg.port_range[0],
          port_end: cfg.port_range[1],
          cors_origins: cfg.cors_origins,
        }),
      )
      .catch(() => {})
  }, [form])

  const pickDir = async () => {
    const path = await pickFolder()
    if (path) form.setFieldsValue({ draft_root: path })
  }

  const autoDetect = async () => {
    const path = await detectDraftRoot()
    if (path) {
      form.setFieldsValue({ draft_root: path })
      message.success('已探测到剪映草稿目录')
    } else {
      message.warning('未探测到剪映默认草稿目录，请手动选择')
    }
  }

  const onSave = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      await putConfig({
        draft_root: v.draft_root || null,
        port_range: [v.port_start, v.port_end],
        cors_origins: v.cors_origins || [],
      })
      message.success('已保存')
      onSaved && onSaved()
    } catch (err) {
      message.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Form form={form} layout="vertical" style={{ maxWidth: 560 }}>
      <Form.Item label="剪映草稿根目录" name="draft_root">
        <Input
          addonAfter={
            <Space size={4}>
              <a onClick={pickDir} style={{ pointerEvents: bridgeOn ? 'auto' : 'none', opacity: bridgeOn ? 1 : 0.4 }}>
                选择目录
              </a>
              <span style={{ color: '#ddd' }}>|</span>
              <a onClick={autoDetect} style={{ pointerEvents: bridgeOn ? 'auto' : 'none', opacity: bridgeOn ? 1 : 0.4 }}>
                自动探测
              </a>
            </Space>
          }
        />
      </Form.Item>
      {!bridgeOn && (
        <div style={{ marginTop: -16, marginBottom: 12, fontSize: 12, color: '#999' }}>
          （浏览器开发环境下「选择目录 / 自动探测」不可用，请手动输入路径）
        </div>
      )}
      <Form.Item label="端口段">
        <Space>
          <Form.Item name="port_start" noStyle>
            <InputNumber min={1} max={65535} />
          </Form.Item>
          <span>—</span>
          <Form.Item name="port_end" noStyle>
            <InputNumber min={1} max={65535} />
          </Form.Item>
          <span style={{ color: '#999', fontSize: 12 }}>修改端口段需重启应用生效</span>
        </Space>
      </Form.Item>
      <Form.Item label="CORS 白名单" name="cors_origins">
        <Select mode="tags" placeholder="输入 origin 后回车，如 http://localhost:3182" />
      </Form.Item>
      <Button type="primary" loading={saving} onClick={onSave}>
        保存
      </Button>
    </Form>
  )
}
```

- [ ] **Step 2: 手动验证**

后端在跑（9527）。`npm run dev` → `http://localhost:3176` → 切到「设置」标签。
Expected: 表单显示当前配置（`draft_root`、端口段两个数字框、CORS 白名单标签）。改 `draft_root` 为一个存在的目录路径 → 点「保存」→ 提示「已保存」。刷新页面（或切走再切回）确认值持久化了。浏览器环境下「选择目录/自动探测」是灰的、下面有灰字说明（这是预期——桥只在 pywebview 窗口里可用，Task 13 会在窗口里验证）。故意把端口段填成非法（如 start 填 0）→ 后端返回 422 → 提示「保存失败」。

- [ ] **Step 3: Commit**

```bash
git add capcut_helper/frontend/src/views/SettingsView.jsx
git commit -m "feat(capcut_helper): 设置视图(配置表单 + 选目录/自动探测)"
```

---

## Task 13: 静态托管 + main.py pywebview 集成

**Files:**
- Modify: `capcut_helper/backend/app/server.py`
- Modify: `capcut_helper/backend/app/main.py`

后端托管前端构建产物，`main.py` 重构为「uvicorn 后台守护线程 + 主线程 pywebview 窗口」。这是把整个桌面应用拼起来的收尾任务，手动冒烟测试。

- [ ] **Step 1: server.py 加静态托管**

把 `capcut_helper/backend/app/server.py` 整体替换为：

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.exceptions import register_exception_handlers

# 前端构建产物目录：capcut_helper/frontend/dist
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None

    cfg = load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    # 先挂 API 路由，再挂前端静态文件到 /（StaticFiles 是兜底匹配）。
    # dist 不存在时（如只跑后端 pytest、还没构建前端）跳过，不影响后端测试。
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

    return app
```

> `parents[2]`：`server.py` 在 `capcut_helper/backend/app/server.py`，`parents[0]=app`、`parents[1]=backend`、`parents[2]=capcut_helper`，再 `/ "frontend" / "dist"`。

- [ ] **Step 2: 跑后端全量测试确认没回归**

Run: `cd capcut_helper/backend && uv run pytest -v`
Expected: 全部 PASS（`_FRONTEND_DIST` 此刻可能不存在，`is_dir()` 为假，静态挂载被跳过，后端测试不受影响）

- [ ] **Step 3: main.py 重构**

把 `capcut_helper/backend/app/main.py` 整体替换为：

```python
import threading
import time
import urllib.request

import uvicorn
import webview

from app.core.config import load_config
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
    cfg = load_config()
    port = select_port(cfg.port_range)
    app = create_app(port)

    # uvicorn 跑在后台守护线程，pywebview GUI 循环必须在主线程
    threading.Thread(target=_run_server, args=(app, port), daemon=True).start()
    if not _wait_for_server(port):
        raise RuntimeError(f"本地服务在端口 {port} 启动超时")

    bridge = NativeBridge()
    window = webview.create_window(
        "capcut_helper",
        f"http://127.0.0.1:{port}/",
        js_api=bridge,
        width=900,
        height=640,
    )
    bridge.window = window
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 构建前端**

Run: `cd capcut_helper/frontend && npm run build`
Expected: 构建到 `capcut_helper/frontend/dist/`，无报错。

- [ ] **Step 5: 手动冒烟测试整个桌面应用**

Run: `cd capcut_helper/backend && uv run python -m app.main`
Expected:
- 弹出一个原生窗口（标题 capcut_helper，约 900×640），加载出 React GUI。
- 顶部状态栏显示「● 服务运行中 · 端口 9527」。
- 若 `draft_root` 未配置：引导横幅出现；因为现在在 pywebview 窗口里、原生桥可用，若本机装了剪映且默认目录存在，横幅会显示「检测到剪映草稿目录：…」。
- 三个标签可切换。「设置」里「选择目录」按钮能弹出系统文件夹选择对话框（原生桥 `pick_folder` 生效）。
- 「活动」「草稿」视图能正常拉数据。
- 关闭窗口，进程退出。

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/server.py capcut_helper/backend/app/main.py
git commit -m "feat(capcut_helper): 后端托管前端 + main.py 拉起 pywebview 窗口"
```

---

## Self-Review

**1. Spec coverage（设计文档第 12 节逐项核对）：**

- §12.1 定位 / §12.2 技术栈与运行方式 → Task 5（Vite+React+AntD 脚手架）、Task 13（main.py uvicorn 后台线程 + pywebview、server.py 静态托管）
- §12.3 整体布局：常驻状态栏 → Task 9（StatusBar）；引导横幅 → Task 9（DraftRootBanner）；顶部标签 → Task 9（App.jsx Tabs）
- §12.4 视图 1 活动 → Task 10；视图 2 草稿 → Task 11；视图 3 设置 → Task 12
- §12.5 后端补充：① `GET /tasks` → Task 2；② `TaskState` 加 `draft_name`/`created_at` → Task 1；③ `/health` 加 `last_draft_request_at` → Task 3；④ `server.py` 静态托管 → Task 13；⑤ `main.py` 重构 → Task 13；⑥ `app/native/bridge.py` → Task 4
- §12.6 数据流（轮询）→ Task 10（活动 1.5s 轮询）、Task 9（状态栏 5s 轮询）、Task 11/12（按需拉取）
- §12.7 原生桥接口 `pick_folder`/`reveal_in_os`/`detect_draft_root` → Task 4（后端实现）、Task 7（前端封装）
- §12.8 错误处理：启动竞态「连接本地服务中…」→ Task 9 StatusBar；`GET /drafts` 空状态 → Task 11；`PUT /config` 422 → Task 12；原生桥取消返回 None → Task 4 + Task 7；任务失败卡片展示 → Task 10
- §12.9 测试：后端 6 项 pytest（Task 1/2/3/4 有测试；Task 13 静态托管+main.py 是手动冒烟，与 spec「pywebview 集成=手动冒烟」一致）；前端纯逻辑 Vitest → Task 6/7/8；UI 手动验证 → Task 9/10/11/12 的手动验证步骤；`detect_draft_root` 路径逻辑单测 → Task 4

无遗漏。打包（Plan 3）明确排除。

**2. 占位符扫描：** 无 TBD/TODO。所有代码步骤给了完整代码；UI 组件任务（Task 9-13）按 spec §12.9 不走 TDD，改为「实现 + 手动验证」并给了具体验证步骤与预期，非占位。Task 5/9 的「占位文件」是有意的脚手架中间态、内容完整且后续任务明确替换，非计划占位符。

**3. 类型一致性：**
- 后端：`TaskState`（`id/draft_name/created_at/status/progress/result/error` + `to_dict()`）Task 1 定义，Task 2 `to_dict()`、Task 10 前端消费字段一致；`TaskRegistry.create(draft_name)`/`list()` Task 1 定义，Task 1（drafts.py）、Task 2（tasks.py）调用一致；`app.state.last_draft_request_at` Task 3 在 server.py 初始化、drafts.py 写、health.py 读，名字一致；`NativeBridge.pick_folder/reveal_in_os/detect_draft_root` Task 4 定义，Task 13 main.py 用 `NativeBridge()` 一致。
- 前端：`client.js` 导出 `getHealth/getTasks/getDrafts/getConfig/putConfig` Task 6 定义，Task 9/10/11/12 import 一致；`bridge.js` 导出 `isBridgeAvailable/pickFolder/revealInOs/detectDraftRoot` Task 7 定义，Task 9/10/11/12 用一致；`relativeTime` Task 8 定义、Task 9/10 用；`taskDisplay` Task 8 定义、Task 10 用；`SettingsView` 的 `onSaved` prop Task 9（App.jsx 传）与 Task 12（接收）一致；`DraftRootBanner` 的 `onGoToSettings`/`onConfigured` Task 9 定义并自洽。

无签名/命名漂移。
