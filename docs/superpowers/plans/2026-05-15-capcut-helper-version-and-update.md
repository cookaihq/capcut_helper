# capcut_helper 版本号与更新提示 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前散落 3 处的版本号收拢到 `backend/app/__init__.py::__version__` 单一来源；在 GUI 状态栏显示当前版本；启动时调 GitHub Releases API 检查新版，发现新版用横幅提示用户「查看说明」/「直接下载」。

**Architecture:** 后端用一个 GitHub adapter（`integrations/github_releases.py`）封装 HTTP，service 层（`services/update_checker.py`）做版本比较与归一化，API 端点（`api/update.py`）暴露 `GET /api/v1/update/check`；前端在 `UpdateBanner.jsx` 组件挂载时调一次，按返回的 `has_update` 决定是否渲染。任何错误静默吃掉、不打扰用户。

**Tech Stack:** FastAPI、httpx、respx、packaging（版本比较）、hatchling（dynamic version）、React + antd Alert、pywebview NativeBridge、`webbrowser.open()`。

**Spec 来源:** `docs/superpowers/specs/2026-05-15-capcut-helper-version-and-update-design.md`

**重要前提（与 spec §7.2 的偏差）：** spec 列出了 `src/components/UpdateBanner.test.jsx` 组件渲染测试，但项目目前未引入 `@testing-library/react`，且 `DraftRootBanner.jsx` 也无组件测试——这是项目既定模式（"前端只测纯逻辑/API client"）。本 plan 不引入新的测试基建，UpdateBanner 的点击行为通过 spec §8 验收清单的手动测试覆盖。

---

## 文件结构总览

**后端（新增）：**
- `backend/app/integrations/github_releases.py` — GitHub Releases HTTP 适配器 + `ReleaseRaw` 数据类 + `GitHubReleaseError`
- `backend/app/services/update_checker.py` — 版本比较与归一化（含模块常量 `GITHUB_OWNER/REPO/ASSET_NAME`）
- `backend/app/schemas/update.py` — `UpdateInfo` Pydantic 模型
- `backend/app/api/update.py` — `GET /api/v1/update/check` 路由
- `backend/tests/test_github_releases.py`
- `backend/tests/test_update_checker.py`
- `backend/tests/test_update_api.py`

**后端（修改）：**
- `backend/pyproject.toml` — 加 `[build-system]`、`dynamic = ["version"]`、`packaging` 依赖、`[tool.hatch.version]`
- `backend/app/api/router.py` — 挂载 update 子路由
- `backend/app/native/bridge.py` — 加 `open_url(url)` 方法
- `backend/tests/test_native_bridge.py` — 加 `open_url` 测试

**前端（新增）：**
- `frontend/src/components/UpdateBanner.jsx`

**前端（修改）：**
- `frontend/package.json` — 删 `"version"` 字段
- `frontend/src/api/client.js` — 加 `getUpdateInfo`
- `frontend/src/api/bridge.js` — 加 `openUrl`
- `frontend/src/api/client.test.js` — 加 `getUpdateInfo` 测试
- `frontend/src/api/bridge.test.js` — 加 `openUrl` 测试
- `frontend/src/components/StatusBar.jsx` — 显示当前版本号
- `frontend/src/App.jsx` — 挂载 `<UpdateBanner/>`

**文档：**
- `README.md`（项目根）— 加「发版」小节

---

## Task 1: 把版本号收拢到 backend `__version__` 单一来源

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `frontend/package.json`

- [ ] **Step 1: 改 backend/pyproject.toml**

把整个文件改成：

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

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "pyinstaller>=6.10",
]

[tool.hatch.version]
path = "app/__init__.py"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

要点：
- 加 `[build-system]` 启用 hatchling（dynamic version 必需）
- `version = "0.1.0"` 改为 `dynamic = ["version"]`
- 加 `packaging>=24.0` 到 dependencies（供 update_checker 比较版本）
- 加 `[tool.hatch.version] path = "app/__init__.py"` 让 hatchling 从 `__init__.py` 提取版本号

- [ ] **Step 2: 改 frontend/package.json，删除 version 字段**

打开 `frontend/package.json`，删掉 `"version": "0.1.0"` 这一行（包括末尾逗号要保留前一行末逗号正确）。

改完后开头几行应为：

```json
{
  "name": "capcut-helper-frontend",
  "private": true,
  "type": "module",
  ...
```

> 该包 `private: true`，npm 允许缺省 version。

- [ ] **Step 3: 跑 `uv sync` 确认锁文件正常**

Run: `cd backend && uv sync`
Expected: 安装成功，`uv.lock` 被更新（packaging 进入锁文件，hatchling 进入 build-system 依赖）。无报错。

- [ ] **Step 4: 验证 importlib.metadata 能取到版本**

Run: `cd backend && uv run python -c "import importlib.metadata; print(importlib.metadata.version('capcut-helper-backend'))"`
Expected: 输出 `0.1.0`

- [ ] **Step 5: 验证前端构建未受影响**

Run: `cd frontend && npm install && npm run build`
Expected: 构建成功，`frontend/dist/` 生成。

- [ ] **Step 6: 跑后端现有测试，确认零回归**

Run: `cd backend && uv run pytest`
Expected: 全部通过。

- [ ] **Step 7: 跑前端现有测试**

Run: `cd frontend && npm run test`
Expected: 全部通过。

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
refactor(capcut_helper): 版本号收拢到 backend __version__ 单一来源

- pyproject.toml: dynamic version + hatchling 读 app/__init__.py
- pyproject.toml: 加 packaging 依赖（供 update_checker 比较）
- frontend/package.json: 删悬空的 version 字段（私有包，无人引用）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: UpdateInfo schema

**Files:**
- Create: `backend/app/schemas/update.py`
- Create: `backend/tests/test_update_schema.py`

- [ ] **Step 1: 写测试**

`backend/tests/test_update_schema.py`:

```python
from app.schemas.update import UpdateInfo


def test_update_info_minimal_fields():
    info = UpdateInfo(current_version="0.1.0", has_update=False)
    assert info.current_version == "0.1.0"
    assert info.has_update is False
    assert info.latest_version is None
    assert info.release_url is None
    assert info.download_url is None
    assert info.notes is None
    assert info.error is None


def test_update_info_full_fields():
    info = UpdateInfo(
        current_version="0.1.0",
        latest_version="0.2.0",
        has_update=True,
        release_url="https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
        download_url="https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip",
        notes="- 新增...",
    )
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && uv run pytest tests/test_update_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.update'`

- [ ] **Step 3: 实现 schema**

`backend/app/schemas/update.py`:

```python
from pydantic import BaseModel


class UpdateInfo(BaseModel):
    current_version: str
    latest_version: str | None = None
    has_update: bool
    release_url: str | None = None
    download_url: str | None = None
    notes: str | None = None
    error: str | None = None
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && uv run pytest tests/test_update_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/update.py backend/tests/test_update_schema.py
git commit -m "$(cat <<'EOF'
feat(capcut_helper): UpdateInfo schema

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: GitHub Releases 适配器 — 正常路径 TDD

**Files:**
- Create: `backend/app/integrations/github_releases.py`
- Create: `backend/tests/test_github_releases.py`

- [ ] **Step 1: 写正常响应的测试**

`backend/tests/test_github_releases.py`:

```python
import httpx
import pytest
import respx

from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseRaw,
    fetch_latest_release,
)


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "## 更新内容\n- 新增了横幅",
    "assets": [
        {
            "name": "capcut_helper.zip",
            "browser_download_url": "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip",
        }
    ],
}


@respx.mock
async def test_fetch_latest_release_happy_path():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")
    assert isinstance(raw, ReleaseRaw)
    assert raw.tag_name == "v0.2.0"
    assert raw.release_url == "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0"
    assert raw.notes == "## 更新内容\n- 新增了横幅"
    assert raw.download_url == "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip"
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && uv run pytest tests/test_github_releases.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 adapter（最小可用）**

`backend/app/integrations/github_releases.py`:

```python
from dataclasses import dataclass

import httpx


_TIMEOUT = 5.0
_USER_AGENT = "capcut_helper"


@dataclass
class ReleaseRaw:
    tag_name: str
    release_url: str
    notes: str
    download_url: str | None


class GitHubReleaseError(Exception):
    """GitHub Releases API 调用失败或响应异常。统一兜底类型，供 service 层 catch。"""


async def fetch_latest_release(owner: str, repo: str, asset_name: str) -> ReleaseRaw:
    """GET https://api.github.com/repos/{owner}/{repo}/releases/latest

    任何错误（网络异常、超时、HTTP 非 2xx、JSON 解析失败、缺 tag_name）→ 抛 GitHubReleaseError。
    成功但 assets 里找不到 asset_name → download_url=None，其余字段照常返回。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
    except httpx.HTTPError as e:
        raise GitHubReleaseError(f"network: {e}") from e

    if resp.status_code != 200:
        raise GitHubReleaseError(f"http {resp.status_code}")

    try:
        body = resp.json()
    except ValueError as e:
        raise GitHubReleaseError(f"invalid json: {e}") from e

    tag_name = body.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        raise GitHubReleaseError("missing tag_name")

    download_url = None
    for asset in body.get("assets") or []:
        if asset.get("name") == asset_name:
            download_url = asset.get("browser_download_url")
            break

    return ReleaseRaw(
        tag_name=tag_name,
        release_url=body.get("html_url") or "",
        notes=body.get("body") or "",
        download_url=download_url,
    )
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && uv run pytest tests/test_github_releases.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/github_releases.py backend/tests/test_github_releases.py
git commit -m "$(cat <<'EOF'
feat(capcut_helper): GitHub Releases 适配器（happy path）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: GitHub adapter — 错误与边界用例

**Files:**
- Modify: `backend/tests/test_github_releases.py`

- [ ] **Step 1: 加错误路径测试（append 到现有文件）**

```python
@respx.mock
async def test_fetch_latest_release_missing_asset():
    response = dict(_VALID_RESPONSE, assets=[{"name": "other.txt", "browser_download_url": "x"}])
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=response)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")
    assert raw.tag_name == "v0.2.0"
    assert raw.download_url is None


@respx.mock
async def test_fetch_latest_release_missing_tag_name():
    bad = dict(_VALID_RESPONSE)
    del bad["tag_name"]
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(GitHubReleaseError, match="missing tag_name"):
        await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")


@respx.mock
async def test_fetch_latest_release_404():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(GitHubReleaseError, match="http 404"):
        await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")


@respx.mock
async def test_fetch_latest_release_network_error():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        side_effect=httpx.ConnectError("dns")
    )
    with pytest.raises(GitHubReleaseError, match="network"):
        await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")
```

- [ ] **Step 2: 跑测试，确认全部通过**

Run: `cd backend && uv run pytest tests/test_github_releases.py -v`
Expected: PASS（4 个新测试 + 1 个旧测试，共 5 通过）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_github_releases.py
git commit -m "$(cat <<'EOF'
test(capcut_helper): GitHub adapter 错误与边界用例

- 资产名不匹配 → download_url=None
- 缺 tag_name / HTTP 404 / 网络异常 → GitHubReleaseError

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: update_checker service — 版本比较与错误兜底

**Files:**
- Create: `backend/app/services/update_checker.py`
- Create: `backend/tests/test_update_checker.py`

- [ ] **Step 1: 写测试**

`backend/tests/test_update_checker.py`:

```python
import pytest

from app.integrations import github_releases
from app.integrations.github_releases import GitHubReleaseError, ReleaseRaw
from app.services import update_checker
from app.services.update_checker import check_for_update


def _release(tag="v0.2.0", download_url="https://x/zip"):
    return ReleaseRaw(
        tag_name=tag,
        release_url="https://x/release",
        notes="notes",
        download_url=download_url,
    )


async def _patch_fetch(monkeypatch, *, returns=None, raises=None):
    async def fake(owner, repo, asset_name):
        if raises is not None:
            raise raises
        return returns
    monkeypatch.setattr(update_checker, "fetch_latest_release", fake)


async def test_has_update_when_remote_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.current_version == "0.1.0"
    assert info.download_url == "https://x/zip"


async def test_no_update_when_versions_equal(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.latest_version == "0.1.0"


async def test_no_update_when_local_is_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.2.0")
    assert info.has_update is False


async def test_strips_v_prefix(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.latest_version == "0.2.0"   # 不含 v


async def test_non_semver_fallback_to_string_inequality(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("0.1.0")
    # 非 SemVer 走字符串相等回退；不等 → has_update=True
    assert info.has_update is True


async def test_non_semver_equal_string_means_no_update(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("release-2026-05")
    assert info.has_update is False


async def test_adapter_error_returns_no_update_with_error_field(monkeypatch):
    await _patch_fetch(monkeypatch, raises=GitHubReleaseError("network: dns"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.error == "network: dns"
    assert info.current_version == "0.1.0"
    assert info.latest_version is None
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && uv run pytest tests/test_update_checker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.update_checker'`

- [ ] **Step 3: 实现 service**

`backend/app/services/update_checker.py`:

```python
from packaging.version import InvalidVersion, Version

from app.integrations.github_releases import GitHubReleaseError, fetch_latest_release
from app.schemas.update import UpdateInfo


GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"
ASSET_NAME = "capcut_helper.zip"


def _strip_v_prefix(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _is_newer(latest: str, current: str) -> bool:
    """SemVer 比较；任一不符合 PEP 440 时回退为字符串相等不等判断。"""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


async def check_for_update(current_version: str) -> UpdateInfo:
    try:
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO, ASSET_NAME)
    except GitHubReleaseError as e:
        return UpdateInfo(
            current_version=current_version,
            has_update=False,
            error=str(e),
        )

    latest = _strip_v_prefix(raw.tag_name)
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        has_update=_is_newer(latest, current_version),
        release_url=raw.release_url,
        download_url=raw.download_url,
        notes=raw.notes,
    )
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && uv run pytest tests/test_update_checker.py -v`
Expected: PASS（7 个测试全部绿）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/update_checker.py backend/tests/test_update_checker.py
git commit -m "$(cat <<'EOF'
feat(capcut_helper): update_checker service（版本比较 + 错误兜底）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `/api/v1/update/check` 端点

**Files:**
- Create: `backend/app/api/update.py`
- Modify: `backend/app/api/router.py`
- Create: `backend/tests/test_update_api.py`

- [ ] **Step 1: 写测试**

`backend/tests/test_update_api.py`:

```python
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    config_mod.save_config(config_mod.Config(draft_root=str(draft_root)))
    app = create_app(port=9527)
    return TestClient(app)


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "notes",
    "assets": [
        {
            "name": "capcut_helper.zip",
            "browser_download_url": "https://x/zip",
        }
    ],
}


@respx.mock
def test_update_check_returns_envelope(client):
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    resp = client.get("/api/v1/update/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    data = body["data"]
    assert data["has_update"] is True
    assert data["latest_version"] == "0.2.0"
    assert data["download_url"] == "https://x/zip"


@respx.mock
def test_update_check_returns_200_on_network_error(client):
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        side_effect=httpx.ConnectError("dns")
    )
    resp = client.get("/api/v1/update/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["has_update"] is False
    assert data["error"] is not None
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && uv run pytest tests/test_update_api.py -v`
Expected: FAIL — 路由 404，因为 `/update/check` 还没挂

- [ ] **Step 3: 实现端点**

`backend/app/api/update.py`:

```python
from fastapi import APIRouter, Request

from app.services.update_checker import check_for_update

router = APIRouter()


@router.get("/update/check")
async def check_update(request: Request):
    info = await check_for_update(request.app.state.version)
    return {"code": 0, "message": "ok", "data": info.model_dump()}
```

- [ ] **Step 4: 挂载子路由**

修改 `backend/app/api/router.py`：

```python
from fastapi import APIRouter

from app.api import config, drafts, health, tasks, update

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(drafts.router)
api_router.include_router(tasks.router)
api_router.include_router(config.router)
api_router.include_router(update.router)
```

- [ ] **Step 5: 跑测试，确认通过**

Run: `cd backend && uv run pytest tests/test_update_api.py -v`
Expected: PASS（2 个测试绿）

- [ ] **Step 6: 跑完整后端测试套件，确认零回归**

Run: `cd backend && uv run pytest`
Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/update.py backend/app/api/router.py backend/tests/test_update_api.py
git commit -m "$(cat <<'EOF'
feat(capcut_helper): GET /api/v1/update/check 端点

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: NativeBridge.open_url

**Files:**
- Modify: `backend/app/native/bridge.py`
- Modify: `backend/tests/test_native_bridge.py`

- [ ] **Step 1: 在 test_native_bridge.py 末尾追加测试**

```python
def test_open_url_invokes_webbrowser(monkeypatch):
    from app.native.bridge import NativeBridge

    called = []
    monkeypatch.setattr("webbrowser.open", lambda url: called.append(url))

    bridge = NativeBridge()
    bridge.open_url("https://example.com/foo")
    assert called == ["https://example.com/foo"]
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && uv run pytest tests/test_native_bridge.py::test_open_url_invokes_webbrowser -v`
Expected: FAIL — `AttributeError: 'NativeBridge' object has no attribute 'open_url'`

- [ ] **Step 3: 实现 open_url**

修改 `backend/app/native/bridge.py`，在 `NativeBridge` 类里加方法（放在 `detect_draft_root` 后面即可）：

```python
    def open_url(self, url: str) -> None:
        """用系统默认浏览器打开 URL（跳出 pywebview 窗口）。"""
        import webbrowser
        webbrowser.open(url)
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && uv run pytest tests/test_native_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/native/bridge.py backend/tests/test_native_bridge.py
git commit -m "$(cat <<'EOF'
feat(capcut_helper): NativeBridge.open_url 跳系统默认浏览器

供 UpdateBanner 的「查看说明」/「直接下载」按钮使用，避免在 pywebview 窗口内打开链接。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 前端 `getUpdateInfo` API client

**Files:**
- Modify: `frontend/src/api/client.js`
- Modify: `frontend/src/api/client.test.js`

- [ ] **Step 1: 追加测试到 client.test.js**

在 `frontend/src/api/client.test.js` 的 `describe('client', ...)` block 内追加：

```js
  it('getUpdateInfo unwraps update info', async () => {
    mockFetch({
      code: 0,
      message: 'ok',
      data: {
        current_version: '0.1.0',
        latest_version: '0.2.0',
        has_update: true,
        release_url: 'https://x/release',
        download_url: 'https://x/zip',
        notes: 'notes',
        error: null,
      },
    })
    const { getUpdateInfo } = await import('./client.js')
    const data = await getUpdateInfo()
    expect(data.has_update).toBe(true)
    expect(data.latest_version).toBe('0.2.0')
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/update/check', undefined)
  })
```

> 注意：动态 import 是因为已经在文件顶部 import 了 `getHealth/getTasks/putConfig`。也可以改顶部 import 把 `getUpdateInfo` 一起 import 进来；动态写法更不易出错（不依赖 import 顺序）。

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd frontend && npm run test`
Expected: FAIL — `getUpdateInfo is not a function`

- [ ] **Step 3: 在 client.js 加 getUpdateInfo**

修改 `frontend/src/api/client.js`，在文件末尾追加：

```js
export const getUpdateInfo = () => request('/update/check')
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd frontend && npm run test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.js frontend/src/api/client.test.js
git commit -m "$(cat <<'EOF'
feat(capcut_helper): 前端 getUpdateInfo API client

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 前端 `openUrl` bridge

**Files:**
- Modify: `frontend/src/api/bridge.js`
- Modify: `frontend/src/api/bridge.test.js`

- [ ] **Step 1: 追加测试到 bridge.test.js**

在 `frontend/src/api/bridge.test.js` 的 `describe('bridge', ...)` block 内追加：

```js
  it('openUrl falls back to window.open without bridge', async () => {
    const { openUrl } = await import('./bridge.js')
    const spy = vi.spyOn(window, 'open').mockImplementation(() => null)
    await openUrl('https://x/foo')
    expect(spy).toHaveBeenCalledWith('https://x/foo', '_blank')
    spy.mockRestore()
  })

  it('openUrl delegates to pywebview.api when available', async () => {
    window.pywebview = {
      api: {
        open_url: vi.fn().mockResolvedValue(undefined),
      },
    }
    const { openUrl } = await import('./bridge.js')
    await openUrl('https://x/bar')
    expect(window.pywebview.api.open_url).toHaveBeenCalledWith('https://x/bar')
  })
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd frontend && npm run test`
Expected: FAIL — `openUrl is not exported`

- [ ] **Step 3: 在 bridge.js 加 openUrl**

修改 `frontend/src/api/bridge.js`，在文件末尾追加：

```js
export async function openUrl(url) {
  if (!isBridgeAvailable()) {
    // 浏览器开发态降级：vite dev server 跑前端时没有 pywebview
    window.open(url, '_blank')
    return
  }
  await window.pywebview.api.open_url(url)
}
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd frontend && npm run test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/bridge.js frontend/src/api/bridge.test.js
git commit -m "$(cat <<'EOF'
feat(capcut_helper): 前端 openUrl bridge（含浏览器开发态降级）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: UpdateBanner 组件

**Files:**
- Create: `frontend/src/components/UpdateBanner.jsx`

> 不写组件测试文件。理由：项目目前未引入 `@testing-library/react`，`DraftRootBanner.jsx` 也无测试。点击/渲染行为通过 spec §8 手动验收覆盖。

- [ ] **Step 1: 写组件**

`frontend/src/components/UpdateBanner.jsx`:

```jsx
import { Alert, Button, Space, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import { getUpdateInfo } from '../api/client.js'
import { openUrl } from '../api/bridge.js'

const NO_ASSET_TOOLTIP = '该 release 未提供下载资产，请用「查看说明」到 release 页查看'

export default function UpdateBanner() {
  const [info, setInfo] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    getUpdateInfo()
      .then((data) => {
        if (data && data.has_update) setInfo(data)
      })
      .catch(() => {
        // 静默：网络失败或本地端点异常都不打扰用户
      })
  }, [])

  if (!info || dismissed) return null

  const downloadDisabled = !info.download_url
  const downloadBtn = (
    <Button
      size="small"
      type="primary"
      disabled={downloadDisabled}
      onClick={() => openUrl(info.download_url)}
    >
      直接下载
    </Button>
  )

  return (
    <Alert
      type="info"
      showIcon
      closable
      onClose={() => setDismissed(true)}
      message={`发现新版本 v${info.latest_version}（当前 v${info.current_version}）`}
      action={
        <Space>
          <Button size="small" onClick={() => openUrl(info.release_url)}>
            查看说明
          </Button>
          {downloadDisabled ? (
            <Tooltip title={NO_ASSET_TOOLTIP}>{downloadBtn}</Tooltip>
          ) : (
            downloadBtn
          )}
        </Space>
      }
    />
  )
}
```

- [ ] **Step 2: 跑前端测试套件确认无回归**

Run: `cd frontend && npm run test`
Expected: 现有测试全绿（本任务不引入新测试）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UpdateBanner.jsx
git commit -m "$(cat <<'EOF'
feat(capcut_helper): UpdateBanner 横幅组件

启动时调 /api/v1/update/check；has_update=true 才渲染。
横幅含「查看说明」（跳 release 页）+「直接下载」（跳 zip 资产直链）两个按钮，
download_url 为 null 时下载按钮 disabled + tooltip。可关闭，本次启动内不再显示。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: StatusBar 显示版本号

**Files:**
- Modify: `frontend/src/components/StatusBar.jsx`

- [ ] **Step 1: 修改 StatusBar.jsx**

把左侧 span 的内容从：

```jsx
        {online ? `服务运行中 · 端口 ${health.port}` : '连接本地服务中…'}
```

改为：

```jsx
        {online
          ? `服务运行中 · 端口 ${health.port}${health.version ? ` · v${health.version}` : ''}`
          : '连接本地服务中…'}
```

> 用条件拼接：health.version 缺失时不显示该片段（防御老后端没返回 version）。

- [ ] **Step 2: 手动验证渲染（先跑一遍前端测试套件确保未破坏）**

Run: `cd frontend && npm run test`
Expected: 全部通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StatusBar.jsx
git commit -m "$(cat <<'EOF'
feat(capcut_helper): StatusBar 显示当前版本号

从 /api/v1/health 的 version 字段拼到左侧文案，无新增网络请求。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: App.jsx 挂载 UpdateBanner

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: 修改 App.jsx**

在 `import` 区追加：

```jsx
import UpdateBanner from './components/UpdateBanner.jsx'
```

在 `return` 的 JSX 中，把 `<DraftRootBanner ... />` 后面加一行 `<UpdateBanner />`：

```jsx
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <StatusBar />
      <DraftRootBanner
        key={bannerKey}
        onGoToSettings={() => setActiveTab('settings')}
        onConfigured={() => setBannerKey((k) => k + 1)}
      />
      <UpdateBanner />
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
      </div>
    </div>
  )
```

- [ ] **Step 2: 跑前端构建确认无语法错误**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "$(cat <<'EOF'
feat(capcut_helper): App 壳挂载 UpdateBanner

放在 DraftRootBanner 下方：硬性引导优先，软性更新提示其次。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: README 加「发版」小节

**Files:**
- Modify: `README.md`（项目根，不是 backend/README.md）

- [ ] **Step 1: 在「打包成 .app 分发」小节前插入「发版」小节**

打开项目根 `README.md`，找到这一行：

```
## 打包成 .app 分发
```

在它**之前**插入：

```markdown
## 发版

1. 改 `backend/app/__init__.py::__version__` 为新版本号（例如 `"0.1.1"`）。这是版本号的唯一手写处，hatchling 会让 `pyproject.toml` 的元数据自动跟上。
2. `git commit -m "chore: bump to 0.1.1"`
3. `git tag v0.1.1 && git push --tags`（tag 必须用 `v` + SemVer，update_checker 按这个格式解析）
4. `bash scripts/build_mac.sh` 生成 `dist/capcut_helper.app` 和 `dist/capcut_helper.zip`
5. 在 GitHub 上创建 release（tag 选 `v0.1.1`），**上传 `dist/capcut_helper.zip` 作为资产，资产名必须是 `capcut_helper.zip`**（与 `scripts/build_mac.sh` 一致，update_checker 按这个名字匹配）
6. release 的 body 写更新说明——这就是横幅「查看说明」按钮跳的页面内容

发布后，已装上旧版的同事下次启动 helper 时会自动看到「发现新版本 v0.1.1」横幅。

```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(capcut_helper): README 加「发版」小节

约定唯一手写版本号位置、tag 格式（v + SemVer）、zip 资产命名。
与 update_checker 的 GITHUB_OWNER/REPO/ASSET_NAME 常量对齐。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: 端到端手动验收

**Files:** 无代码改动；按 spec §8 走一遍验收清单。

- [ ] **Step 1: 把当前 `__version__` 改成 `0.1.1` 临时验证 hatchling 联动**

```bash
cd backend
# 临时把 app/__init__.py 改成 __version__ = "0.1.1"
uv run python -c "import importlib.metadata; print(importlib.metadata.version('capcut-helper-backend'))"
```

Expected: 输出 `0.1.1`。验证完**改回** `__version__ = "0.1.0"`。

- [ ] **Step 2: 跑完整测试套件**

```bash
cd backend && uv run pytest
cd ../frontend && npm run test
```

Expected: 全部通过。

- [ ] **Step 3: 构建并启动 helper**

```bash
cd frontend && npm run build
cd ../backend && uv run python -m app.main
```

Expected: pywebview 窗口打开，状态栏左侧能看到 `v0.1.0`。

- [ ] **Step 4: 验证「无网络」路径**

在没有互联网（拔网线或断 WiFi）的情况下启动 helper。

Expected: 状态栏正常显示版本号；无任何报错弹窗；无横幅；主流程（活动/草稿/设置）正常。

- [ ] **Step 5: 验证「有新版本」路径（需要先在 GitHub 打一个高版本 tag/release）**

操作：
1. 在 GitHub 仓库 `cookaihq/capcut_helper` 打一个 tag `v9.9.9` 用于测试
2. 创建对应 release，附带一份名为 `capcut_helper.zip` 的资产（可用任意小文件改名）
3. 重启 helper

Expected：
- 横幅出现：「发现新版本 v9.9.9（当前 v0.1.0）」
- 点「查看说明」→ 系统默认浏览器打开 release 页
- 点「直接下载」→ 系统默认浏览器开始下载 zip
- 点「×」→ 横幅消失
- 重启 helper → 横幅再次出现

验收完后**删掉 v9.9.9 测试 release 和 tag**。

- [ ] **Step 6: 验证「无下载资产」路径**

操作：临时把上一步的 `v9.9.9` release 编辑掉 zip 资产、保留 release 本身，再重启 helper。

Expected：横幅出现，「直接下载」按钮 disabled，hover 看到 tooltip。

- [ ] **Step 7: 验证 CALLER_GUIDE 字段一致性**

`curl -s http://127.0.0.1:9527/api/v1/health` 的响应字段应当与 `backend/docs/CALLER_GUIDE.md` §5.1 列出的字段完全一致（含 `last_draft_request_at`）。

- [ ] **Step 8: 全部通过则收尾**

无新增 commit；如发现回归 bug，按 TDD 补测 + 修复 + commit。

---

## 自检结论（写作时已做）

- **Spec 覆盖**：spec §3（单一版本源）→ Task 1；§4.1 adapter → Task 3-4；§4.2 service → Task 5；§4.3 API → Task 6；§4.4 schema → Task 2；§4.5 native bridge → Task 7；§5.1-5.6 前端 → Task 8-12；§3.3 README → Task 13；§8 验收 → Task 14
- **占位符**：无 TBD / TODO / "类似前面"
- **类型一致性**：`ReleaseRaw` 在 Task 3 定义并被 Task 5 引用；`UpdateInfo` 在 Task 2 定义并被 Task 5、6 引用；前端 `getUpdateInfo`/`openUrl` 在 Task 8、9 定义并被 Task 10 引用——签名一致
- **偏离 spec 处**：spec §7.2 列出 UpdateBanner 组件测试，本 plan 不做（项目无 `@testing-library/react`，DraftRootBanner 也无组件测试——遵循项目既定模式），由 Task 14 手动验收覆盖。这是显式决策，已在 plan 头部声明
