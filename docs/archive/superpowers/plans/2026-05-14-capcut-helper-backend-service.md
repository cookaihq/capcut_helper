# capcut_helper 后端本地服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 capcut_helper 的后端本地服务——一个 FastAPI 进程，对外暴露「从时间线规格新建剪映草稿」的 HTTP API，素材并发下载进草稿文件夹。

**Architecture:** 单进程 FastAPI 服务（设计文档方案 A）。HTTP 路由层薄，转发给 service 层；service 层编排「建空草稿 → 下素材 → 填轨道片段 → 保存」；jianying 集成层包装 pyJianYingDraft；后台任务用 `asyncio.create_task` 跑，进度存在内存 task registry，前端轮询查询。本计划只做后端，产出的服务可用 curl + pytest 独立验证。

**Tech Stack:** Python 3.11、FastAPI、uvicorn、httpx、pyJianYingDraft 0.2.6、uv（包管理）、pytest + pytest-asyncio + respx（测试）。

**计划范围说明：** 这是 capcut_helper 的 **Plan 1（共 2 个）**。本计划只覆盖后端本地服务，是独立可测的软件。**Plan 2**（后续单独编写）覆盖桌面壳：pywebview 窗口、原生桥（文件夹选择/在访达打开/探测剪映草稿根目录）、React GUI、跨平台打包。设计文档中的「桌面 GUI」「原生桥」「托管 GUI 静态文件」属于 Plan 2。

**前置说明：**
- 所有命令的工作目录为 `capcut_helper/backend/`（除非另行说明）。
- git 提交身份已配置为 repo-local 的 cookaihq（无需在计划里再配）。
- 设计文档：`capcut_helper/docs/superpowers/specs/2026-05-14-capcut-helper-local-service-design.md`。
- 实测已确认的 pyJianYingDraft 0.2.6 API 签名（计划中代码已据此编写）：
  - `DraftFolder(folder_path)` → `.create_draft(name, width, height, fps=30, *, allow_replace=False)` 返回 `ScriptFile`；`allow_replace=True` 时会 `shutil.rmtree` 整个草稿文件夹再重建；`.list_drafts() -> List[str]`
  - `VideoMaterial(path)`、`AudioMaterial(path)`；material 的 `.duration` 为微秒整数
  - `VideoSegment(material, target_timerange, *, source_timerange=None)`、`AudioSegment(material, target_timerange, *, source_timerange=None)`、`TextSegment(text, timerange)`
  - `trange(start, duration)` 接受微秒整数，返回 `Timerange`
  - `TrackType.video / .audio / .text`
  - `ScriptFile.add_track(track_type, track_name=None)`、`.add_segment(segment, track_name=None)`、`.save()`
- 测试素材：仓库已有 `capcut_helper/tests/2-1 (1).mp4`（时长 9160000 微秒）和 `capcut_helper/tests/2-2 (1).mp4`（时长 33320000 微秒），Task 1 会复制为干净命名的 fixture。

---

## File Structure

```
capcut_helper/backend/
├── pyproject.toml                       # uv 项目定义、依赖
├── app/
│   ├── __init__.py                      # __version__
│   ├── main.py                          # 入口：选端口 → create_app → uvicorn.run
│   ├── server.py                        # create_app：FastAPI 实例、CORS、异常处理器、挂路由
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    # Config 模型 + load_config/save_config（JSON 文件）
│   │   ├── exceptions.py                # AppException 体系 + register_exception_handlers
│   │   ├── port.py                      # select_port：端口段内挑空闲端口
│   │   └── tasks.py                     # TaskState + TaskRegistry + registry 单例
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── timeline.py                  # TimelineSpec / Track / Segment / Material / Canvas / TimeRange
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── jianying/
│   │       ├── __init__.py
│   │       └── builder.py               # create_empty_draft / populate_draft / save_draft
│   ├── services/
│   │   ├── __init__.py
│   │   ├── downloader.py                # download_materials：并发下载、按 URL 去重、重试
│   │   └── draft_service.py             # run_draft_task / dispatch_draft_task：编排 + 进度
│   └── api/
│       ├── __init__.py
│       ├── router.py                    # 聚合各路由，prefix /api/v1
│       ├── health.py                    # GET /health
│       ├── drafts.py                    # POST /drafts、GET /drafts
│       ├── tasks.py                     # GET /tasks/{task_id}
│       └── config.py                    # GET /config、PUT /config
└── tests/
    ├── conftest.py                      # 共享 fixture：tmp 配置、fixture 视频路径
    ├── fixtures/
    │   ├── sample1.mp4                  # 由 Task 1 从 capcut_helper/tests/2-1 (1).mp4 复制
    │   └── sample2.mp4                  # 由 Task 1 从 capcut_helper/tests/2-2 (1).mp4 复制
    ├── test_exceptions.py
    ├── test_timeline_schema.py
    ├── test_config.py
    ├── test_task_registry.py
    ├── test_downloader.py
    ├── test_jianying_builder.py
    ├── test_draft_service.py
    ├── test_port.py
    ├── test_api.py
    └── test_e2e_draft.py
```

---

## Task 1: 项目脚手架与测试素材

**Files:**
- Create: `capcut_helper/backend/pyproject.toml`
- Create: `capcut_helper/backend/app/__init__.py`
- Create: 各子包的 `__init__.py`（`app/core/`、`app/schemas/`、`app/integrations/`、`app/integrations/jianying/`、`app/services/`、`app/api/`）
- Create: `capcut_helper/backend/tests/__init__.py`
- Create: `capcut_helper/backend/tests/fixtures/sample1.mp4`、`sample2.mp4`（从仓库已有 mp4 复制）

- [ ] **Step 1: 创建 pyproject.toml**

`capcut_helper/backend/pyproject.toml`:

```toml
[project]
name = "capcut-helper-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
    "pyJianYingDraft>=0.2.6",
    "platformdirs>=4.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 创建包结构与 __init__.py**

`capcut_helper/backend/app/__init__.py`:

```python
__version__ = "0.1.0"
```

其余 `__init__.py` 全部为空文件：`app/core/__init__.py`、`app/schemas/__init__.py`、`app/integrations/__init__.py`、`app/integrations/jianying/__init__.py`、`app/services/__init__.py`、`app/api/__init__.py`、`tests/__init__.py`。

- [ ] **Step 3: 复制测试素材为干净命名**

Run（工作目录 `capcut_helper/backend/`）:

```bash
mkdir -p tests/fixtures
cp "../tests/2-1 (1).mp4" tests/fixtures/sample1.mp4
cp "../tests/2-2 (1).mp4" tests/fixtures/sample2.mp4
```

- [ ] **Step 4: 安装依赖**

Run: `uv sync`
Expected: 创建 `.venv`，安装 fastapi / uvicorn / httpx / pyjianyingdraft / platformdirs 及 dev 依赖，无报错。

- [ ] **Step 5: 验证环境可用**

Run: `uv run python -c "import fastapi, httpx, pyJianYingDraft, platformdirs; import app; print(app.__version__)"`
Expected: 输出 `0.1.0`，无 ImportError。

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/pyproject.toml capcut_helper/backend/uv.lock capcut_helper/backend/app capcut_helper/backend/tests
git commit -m "chore(capcut_helper): 后端项目脚手架与测试素材"
```

---

## Task 2: 响应封装与异常体系

**Files:**
- Create: `capcut_helper/backend/app/core/exceptions.py`
- Test: `capcut_helper/backend/tests/test_exceptions.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_exceptions.py`:

```python
from app.core.exceptions import (
    AppException,
    DraftRootNotConfigured,
    DraftNameConflict,
    TaskNotFound,
    MaterialDownloadError,
)


def test_app_exception_carries_message_and_data():
    exc = AppException("出错了", data={"k": "v"})
    assert exc.message == "出错了"
    assert exc.data == {"k": "v"}
    assert exc.code == 1000
    assert exc.status_code == 400


def test_subclasses_have_distinct_codes_and_status():
    assert (DraftRootNotConfigured("x").code, DraftRootNotConfigured("x").status_code) == (1001, 400)
    assert (DraftNameConflict("x").code, DraftNameConflict("x").status_code) == (1002, 409)
    assert (TaskNotFound("x").code, TaskNotFound("x").status_code) == (1003, 404)
    assert (MaterialDownloadError("x").code, MaterialDownloadError("x").status_code) == (1004, 502)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.exceptions'`

- [ ] **Step 3: 实现异常体系**

`capcut_helper/backend/app/core/exceptions.py`:

```python
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    code = 1000
    status_code = 400

    def __init__(self, message: str, data: Any = None):
        self.message = message
        self.data = data
        super().__init__(message)


class DraftRootNotConfigured(AppException):
    code = 1001
    status_code = 400


class DraftNameConflict(AppException):
    code = 1002
    status_code = 409


class TaskNotFound(AppException):
    code = 1003
    status_code = 404


class MaterialDownloadError(AppException):
    code = 1004
    status_code = 502


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": 422, "message": "时间线规格非法", "data": jsonable_encoder(exc.errors())},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/exceptions.py capcut_helper/backend/tests/test_exceptions.py
git commit -m "feat(capcut_helper): 异常体系与全局异常处理器"
```

---

## Task 3: 时间线规格 Pydantic Schema

**Files:**
- Create: `capcut_helper/backend/app/schemas/timeline.py`
- Test: `capcut_helper/backend/tests/test_timeline_schema.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_timeline_schema.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.timeline import TimelineSpec


def _video_spec():
    return {
        "draft_name": "测试草稿",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {"url": "https://x/a.mp4", "type": "video", "filename": "a.mp4"},
                        "timeline": {"start": 0, "duration": 9160000},
                    }
                ],
            }
        ],
    }


def test_valid_video_spec_parses():
    spec = TimelineSpec.model_validate(_video_spec())
    assert spec.draft_name == "测试草稿"
    assert spec.allow_replace is False
    assert spec.tracks[0].segments[0].material.url == "https://x/a.mp4"


def test_material_urls_dedups_by_url():
    data = _video_spec()
    seg = data["tracks"][0]["segments"][0]
    data["tracks"][0]["segments"].append(dict(seg))  # 同一个 URL 用两次
    spec = TimelineSpec.model_validate(data)
    assert len(spec.material_urls()) == 1


def test_video_segment_without_material_rejected():
    data = _video_spec()
    del data["tracks"][0]["segments"][0]["material"]
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)


def test_text_segment_without_text_rejected():
    data = _video_spec()
    data["tracks"][0]["type"] = "text"
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)


def test_draft_name_with_path_separator_rejected():
    data = _video_spec()
    data["draft_name"] = "bad/name"
    with pytest.raises(ValidationError):
        TimelineSpec.model_validate(data)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_timeline_schema.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.schemas.timeline'`

- [ ] **Step 3: 实现 timeline schema**

`capcut_helper/backend/app/schemas/timeline.py`:

```python
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Canvas(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(default=30, gt=0)


class Material(BaseModel):
    url: str = Field(min_length=1)
    type: Literal["video", "image", "audio"]
    filename: str = Field(min_length=1)


class TimeRange(BaseModel):
    start: int = Field(ge=0)       # 微秒
    duration: int = Field(gt=0)    # 微秒


class TextContent(BaseModel):
    content: str = Field(min_length=1)
    style: dict = Field(default_factory=dict)


class Segment(BaseModel):
    material: Optional[Material] = None
    timeline: TimeRange
    source: Optional[TimeRange] = None
    text: Optional[TextContent] = None


class Track(BaseModel):
    type: Literal["video", "audio", "text"]
    segments: list[Segment] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_segment_payload(self):
        for seg in self.segments:
            if self.type in ("video", "audio") and seg.material is None:
                raise ValueError(f"{self.type} 轨道的片段必须含 material")
            if self.type == "text" and seg.text is None:
                raise ValueError("text 轨道的片段必须含 text")
        return self


class TimelineSpec(BaseModel):
    draft_name: str = Field(min_length=1)
    allow_replace: bool = False
    canvas: Canvas
    tracks: list[Track] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_draft_name(self):
        if "/" in self.draft_name or "\\" in self.draft_name:
            raise ValueError("draft_name 不能包含路径分隔符")
        return self

    def material_urls(self) -> list[Material]:
        """按 URL 去重，返回所有需要下载的素材。"""
        seen: dict[str, Material] = {}
        for track in self.tracks:
            for seg in track.segments:
                if seg.material and seg.material.url not in seen:
                    seen[seg.material.url] = seg.material
        return list(seen.values())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_timeline_schema.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/schemas/timeline.py capcut_helper/backend/tests/test_timeline_schema.py
git commit -m "feat(capcut_helper): 时间线规格 Pydantic schema"
```

---

## Task 4: 配置（Config 模型与读写）

**Files:**
- Create: `capcut_helper/backend/app/core/config.py`
- Test: `capcut_helper/backend/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_config.py`:

```python
from app.core.config import Config, load_config, save_config


def test_default_config_values():
    cfg = Config()
    assert cfg.draft_root is None
    assert cfg.port_range == [9527, 9536]
    assert cfg.cors_origins == ["http://localhost:3182", "http://localhost:3183"]


def test_load_returns_default_when_file_absent(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.draft_root is None


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(draft_root="/some/path", port_range=[9000, 9001]), path)
    loaded = load_config(path)
    assert loaded.draft_root == "/some/path"
    assert loaded.port_range == [9000, 9001]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: 实现 config**

`capcut_helper/backend/app/core/config.py`:

```python
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir
from pydantic import BaseModel, Field

CONFIG_DIR = Path(user_config_dir("capcut_helper"))
CONFIG_PATH = CONFIG_DIR / "config.json"


class Config(BaseModel):
    draft_root: Optional[str] = None
    port_range: list[int] = Field(default_factory=lambda: [9527, 9536])
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3182", "http://localhost:3183"]
    )


def load_config(path: Optional[Path] = None) -> Config:
    path = path or CONFIG_PATH
    if path.exists():
        return Config.model_validate_json(path.read_text("utf-8"))
    return Config()


def save_config(cfg: Config, path: Optional[Path] = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/config.py capcut_helper/backend/tests/test_config.py
git commit -m "feat(capcut_helper): 配置模型与 JSON 文件读写"
```

---

## Task 5: 内存任务注册表

**Files:**
- Create: `capcut_helper/backend/app/core/tasks.py`
- Test: `capcut_helper/backend/tests/test_task_registry.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_task_registry.py`:

```python
from app.core.tasks import TaskRegistry


def test_create_returns_unique_ids():
    reg = TaskRegistry()
    a = reg.create()
    b = reg.create()
    assert a.id != b.id
    assert a.status == "pending"
    assert a.progress == 0


def test_get_returns_state_or_none():
    reg = TaskRegistry()
    st = reg.create()
    assert reg.get(st.id) is st
    assert reg.get("missing") is None


def test_update_mutates_fields():
    reg = TaskRegistry()
    st = reg.create()
    reg.update(st.id, status="done", progress=100, result="/path/to/draft")
    fresh = reg.get(st.id)
    assert fresh.status == "done"
    assert fresh.progress == 100
    assert fresh.result == "/path/to/draft"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_registry.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.tasks'`

- [ ] **Step 3: 实现任务注册表**

`capcut_helper/backend/app/core/tasks.py`:

```python
import uuid
from dataclasses import asdict, dataclass
from typing import Literal, Optional

TaskStatus = Literal["pending", "downloading", "building", "done", "failed"]


@dataclass
class TaskState:
    id: str
    status: TaskStatus = "pending"
    progress: int = 0
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}

    def create(self) -> TaskState:
        task_id = uuid.uuid4().hex
        state = TaskState(id=task_id)
        self._tasks[task_id] = state
        return state

    def get(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **fields) -> TaskState:
        state = self._tasks[task_id]
        for key, value in fields.items():
            setattr(state, key, value)
        return state


# 进程级单例：API 层和后台任务共用同一个注册表
registry = TaskRegistry()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_registry.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/tasks.py capcut_helper/backend/tests/test_task_registry.py
git commit -m "feat(capcut_helper): 内存任务注册表"
```

---

## Task 6: 素材下载器

**Files:**
- Create: `capcut_helper/backend/app/services/downloader.py`
- Test: `capcut_helper/backend/tests/test_downloader.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_downloader.py`:

```python
import httpx
import pytest
import respx

from app.core.exceptions import MaterialDownloadError
from app.schemas.timeline import Material
from app.services import downloader


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # 把重试退避时间设为 0，避免测试变慢
    monkeypatch.setattr(downloader, "_BACKOFF_BASE", 0)


def _material(url, filename="clip.mp4"):
    return Material(url=url, type="video", filename=filename)


@respx.mock
async def test_downloads_files_into_dest_dir(tmp_path):
    respx.get("https://x/a.mp4").mock(return_value=httpx.Response(200, content=b"AAAA"))
    respx.get("https://x/b.mp4").mock(return_value=httpx.Response(200, content=b"BBBB"))
    mats = [_material("https://x/a.mp4", "a.mp4"), _material("https://x/b.mp4", "b.mp4")]
    result = await downloader.download_materials(mats, tmp_path)
    assert set(result.keys()) == {"https://x/a.mp4", "https://x/b.mp4"}
    for path in result.values():
        assert path.parent == tmp_path
        assert path.read_bytes() in (b"AAAA", b"BBBB")


@respx.mock
async def test_skips_redownload_when_file_exists(tmp_path):
    route = respx.get("https://x/a.mp4").mock(return_value=httpx.Response(200, content=b"AAAA"))
    mats = [_material("https://x/a.mp4", "a.mp4")]
    await downloader.download_materials(mats, tmp_path)
    await downloader.download_materials(mats, tmp_path)  # 第二次：文件已存在
    assert route.call_count == 1


@respx.mock
async def test_retries_then_raises_on_persistent_failure(tmp_path):
    respx.get("https://x/bad.mp4").mock(return_value=httpx.Response(500))
    mats = [_material("https://x/bad.mp4", "bad.mp4")]
    with pytest.raises(MaterialDownloadError) as exc:
        await downloader.download_materials(mats, tmp_path, retries=2)
    assert "bad.mp4" in str(exc.value)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.downloader'`

- [ ] **Step 3: 实现下载器**

`capcut_helper/backend/app/services/downloader.py`:

```python
import asyncio
import hashlib
import re
from pathlib import Path

import httpx

from app.core.exceptions import MaterialDownloadError
from app.schemas.timeline import Material

_BACKOFF_BASE = 2  # 重试退避基数（秒）；测试中会被 monkeypatch 为 0
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(material: Material) -> str:
    """用 URL 哈希前缀 + 清洗后的文件名，避免不同 URL 的同名文件互相覆盖。"""
    digest = hashlib.sha256(material.url.encode("utf-8")).hexdigest()[:8]
    cleaned = _UNSAFE_CHARS.sub("_", material.filename) or "material"
    return f"{digest}_{cleaned}"


async def _download_one(
    client: httpx.AsyncClient, material: Material, dest_dir: Path, retries: int
) -> tuple[str, Path]:
    dest = dest_dir / _safe_filename(material)
    if dest.exists():
        return material.url, dest

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.get(material.url, timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return material.url, dest
        except Exception as exc:  # noqa: BLE001 — 下载失败统一兜底重试
            last_error = exc
            await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))

    raise MaterialDownloadError(
        f"素材下载失败: {material.filename} ({material.url}) — {last_error}"
    )


async def download_materials(
    materials: list[Material], dest_dir, retries: int = 3
) -> dict[str, Path]:
    """并发下载素材到 dest_dir，返回 {url: 本地路径}。materials 已按 URL 去重。"""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_download_one(client, m, dest_dir, retries) for m in materials)
        )
    return dict(results)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/services/downloader.py capcut_helper/backend/tests/test_downloader.py
git commit -m "feat(capcut_helper): 素材并发下载器（去重 + 重试）"
```

---

## Task 7: jianying 集成层（包装 pyJianYingDraft）

**Files:**
- Create: `capcut_helper/backend/app/integrations/jianying/builder.py`
- Create: `capcut_helper/backend/tests/conftest.py`
- Test: `capcut_helper/backend/tests/test_jianying_builder.py`

- [ ] **Step 1: 创建共享 conftest.py**

`capcut_helper/backend/tests/conftest.py`:

```python
from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).parent / "fixtures"

# 两个 fixture 视频的已知时长（微秒），实测自仓库已有素材
SAMPLE1_DURATION = 9160000
SAMPLE2_DURATION = 33320000


@pytest.fixture
def fixture_video_1() -> Path:
    return _FIXTURE_DIR / "sample1.mp4"


@pytest.fixture
def fixture_video_2() -> Path:
    return _FIXTURE_DIR / "sample2.mp4"
```

- [ ] **Step 2: 写失败测试**

`capcut_helper/backend/tests/test_jianying_builder.py`:

```python
import json
import shutil

import pytest

from app.core.exceptions import DraftNameConflict
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from tests.conftest import SAMPLE1_DURATION, SAMPLE2_DURATION


def _two_video_spec(allow_replace=False):
    return TimelineSpec.model_validate(
        {
            "draft_name": "builder_test",
            "allow_replace": allow_replace,
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/v1.mp4", "type": "video", "filename": "v1.mp4"},
                            "timeline": {"start": 0, "duration": SAMPLE1_DURATION},
                        },
                        {
                            "material": {"url": "https://x/v2.mp4", "type": "video", "filename": "v2.mp4"},
                            "timeline": {"start": SAMPLE1_DURATION, "duration": SAMPLE2_DURATION},
                        },
                    ],
                }
            ],
        }
    )


def test_create_populate_save_writes_valid_draft(tmp_path, fixture_video_1, fixture_video_2):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec()

    script, draft_dir = builder.create_empty_draft(str(draft_root), spec)
    assert draft_dir == draft_root / "builder_test"
    assert draft_dir.is_dir()

    # 模拟「下素材进草稿文件夹」：把 fixture 复制进去
    v1 = draft_dir / "v1.mp4"
    v2 = draft_dir / "v2.mp4"
    shutil.copy(fixture_video_1, v1)
    shutil.copy(fixture_video_2, v2)
    material_paths = {"https://x/v1.mp4": v1, "https://x/v2.mp4": v2}

    builder.populate_draft(script, spec, material_paths)
    builder.save_draft(script)

    content = json.loads((draft_dir / "draft_content.json").read_text("utf-8"))
    assert content["canvas_config"]["width"] == 1920
    assert content["canvas_config"]["height"] == 1080
    assert len(content["tracks"]) == 1
    assert len(content["tracks"][0]["segments"]) == 2
    assert content["tracks"][0]["segments"][0]["target_timerange"] == {
        "start": 0,
        "duration": SAMPLE1_DURATION,
    }


def test_create_empty_draft_raises_conflict_when_exists(tmp_path):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec(allow_replace=False)

    builder.create_empty_draft(str(draft_root), spec)  # 第一次成功
    with pytest.raises(DraftNameConflict):
        builder.create_empty_draft(str(draft_root), spec)  # 第二次重名且不允许覆盖
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/test_jianying_builder.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.integrations.jianying.builder'`

- [ ] **Step 4: 实现 jianying 集成层**

`capcut_helper/backend/app/integrations/jianying/builder.py`:

```python
from pathlib import Path

import pyJianYingDraft as draft
from pyJianYingDraft import (
    AudioMaterial,
    AudioSegment,
    DraftFolder,
    TextSegment,
    TrackType,
    VideoMaterial,
    VideoSegment,
    trange,
)

from app.core.exceptions import DraftNameConflict
from app.schemas.timeline import TimelineSpec

_TRACK_TYPE = {
    "video": TrackType.video,
    "audio": TrackType.audio,
    "text": TrackType.text,
}


def create_empty_draft(draft_root: str, spec: TimelineSpec):
    """建一个空草稿文件夹。注意：allow_replace=True 时 pyJianYingDraft 会 rmtree
    整个草稿文件夹再重建，所以必须先调本函数、再往文件夹里下素材。
    返回 (ScriptFile, draft_dir)。"""
    folder = DraftFolder(draft_root)
    try:
        script = folder.create_draft(
            spec.draft_name,
            spec.canvas.width,
            spec.canvas.height,
            fps=spec.canvas.fps,
            allow_replace=spec.allow_replace,
        )
    except FileExistsError:
        raise DraftNameConflict(f"草稿已存在且未允许覆盖: {spec.draft_name}")
    draft_dir = Path(draft_root) / spec.draft_name
    return script, draft_dir


def populate_draft(script, spec: TimelineSpec, material_paths: dict[str, Path]) -> None:
    """按时间线规格往草稿里逐轨逐段填内容。material_paths 是 {url: 本地路径}。"""
    for index, track in enumerate(spec.tracks):
        track_name = f"{track.type}_{index}"
        script.add_track(_TRACK_TYPE[track.type], track_name=track_name)
        for seg in track.segments:
            target = trange(seg.timeline.start, seg.timeline.duration)
            source = (
                trange(seg.source.start, seg.source.duration) if seg.source else None
            )
            if track.type == "video":
                material = VideoMaterial(str(material_paths[seg.material.url]))
                script.add_segment(
                    VideoSegment(material, target, source_timerange=source),
                    track_name=track_name,
                )
            elif track.type == "audio":
                material = AudioMaterial(str(material_paths[seg.material.url]))
                script.add_segment(
                    AudioSegment(material, target, source_timerange=source),
                    track_name=track_name,
                )
            else:  # text
                script.add_segment(
                    TextSegment(seg.text.content, target), track_name=track_name
                )


def save_draft(script) -> None:
    script.save()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_jianying_builder.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/integrations capcut_helper/backend/tests/conftest.py capcut_helper/backend/tests/test_jianying_builder.py
git commit -m "feat(capcut_helper): jianying 集成层（建草稿/填轨道/保存）"
```

---

## Task 8: 草稿编排服务

**Files:**
- Create: `capcut_helper/backend/app/services/draft_service.py`
- Test: `capcut_helper/backend/tests/test_draft_service.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_draft_service.py`:

```python
import pytest

from app.core import config as config_mod
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services import draft_service


def _spec():
    return TimelineSpec.model_validate(
        {
            "draft_name": "svc_test",
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/a.mp4", "type": "video", "filename": "a.mp4"},
                            "timeline": {"start": 0, "duration": 1000000},
                        }
                    ],
                }
            ],
        }
    )


async def test_run_draft_task_success_path(tmp_path, monkeypatch):
    # 配置一个存在的草稿根目录
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(draft_root)))

    # 把 jianying 和下载器都换成假实现，只验证编排与进度
    draft_dir = draft_root / "svc_test"
    monkeypatch.setattr(
        draft_service.builder, "create_empty_draft",
        lambda root, spec: ("FAKE_SCRIPT", draft_dir),
    )
    async def _fake_download(materials, dest):
        return {m.url: dest / m.filename for m in materials}
    monkeypatch.setattr(draft_service, "download_materials", _fake_download)
    monkeypatch.setattr(draft_service.builder, "populate_draft", lambda *a, **k: None)
    monkeypatch.setattr(draft_service.builder, "save_draft", lambda *a, **k: None)

    task = registry.create()
    await draft_service.run_draft_task(task.id, _spec())

    state = registry.get(task.id)
    assert state.status == "done"
    assert state.progress == 100
    assert state.result == str(draft_dir)


async def test_run_draft_task_fails_when_draft_root_not_configured(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)  # 不写 config → draft_root 为 None

    task = registry.create()
    await draft_service.run_draft_task(task.id, _spec())

    state = registry.get(task.id)
    assert state.status == "failed"
    assert "草稿根目录" in state.error
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_draft_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.draft_service'`

- [ ] **Step 3: 实现编排服务**

`capcut_helper/backend/app/services/draft_service.py`:

```python
import asyncio
from pathlib import Path

from app.core.config import load_config
from app.core.exceptions import DraftRootNotConfigured
from app.core.tasks import registry
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from app.services.downloader import download_materials


async def run_draft_task(task_id: str, spec: TimelineSpec) -> None:
    """后台任务主体：建空草稿 → 下素材进文件夹 → 填轨道片段 → 保存。
    全程更新 task registry 的状态与进度。"""
    try:
        cfg = load_config()
        if not cfg.draft_root or not Path(cfg.draft_root).is_dir():
            raise DraftRootNotConfigured("剪映草稿根目录未配置或不存在")

        registry.update(task_id, status="building", progress=10)
        # pyJianYingDraft 是同步阻塞库，放线程里跑，避免卡事件循环
        script, draft_dir = await asyncio.to_thread(
            builder.create_empty_draft, cfg.draft_root, spec
        )

        registry.update(task_id, status="downloading", progress=30)
        material_paths = await download_materials(spec.material_urls(), draft_dir)

        registry.update(task_id, status="building", progress=70)
        await asyncio.to_thread(builder.populate_draft, script, spec, material_paths)
        await asyncio.to_thread(builder.save_draft, script)

        registry.update(task_id, status="done", progress=100, result=str(draft_dir))
    except Exception as exc:  # noqa: BLE001 — 任何失败都落到 task 状态上报
        registry.update(task_id, status="failed", error=str(exc))


def dispatch_draft_task(spec: TimelineSpec) -> str:
    """创建 task 并在后台启动 run_draft_task，立即返回 task_id。
    必须在有运行中事件循环的上下文调用（FastAPI async 路由内）。"""
    state = registry.create()
    asyncio.create_task(run_draft_task(state.id, spec))
    return state.id
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_draft_service.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/services/draft_service.py capcut_helper/backend/tests/test_draft_service.py
git commit -m "feat(capcut_helper): 草稿编排服务（建草稿→下素材→填片段→保存）"
```

---

## Task 9: 端口段选择

**Files:**
- Create: `capcut_helper/backend/app/core/port.py`
- Test: `capcut_helper/backend/tests/test_port.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_port.py`:

```python
import socket

import pytest

from app.core.port import select_port


def test_select_port_returns_port_in_range():
    port = select_port([19527, 19536])
    assert 19527 <= port <= 19536


def test_select_port_skips_occupied_port():
    # 先占住端口段里的第一个端口
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", 19600))
    occupied.listen(1)
    try:
        port = select_port([19600, 19601])
        assert port == 19601
    finally:
        occupied.close()


def test_select_port_raises_when_whole_range_occupied():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 19700))
    s.listen(1)
    try:
        with pytest.raises(RuntimeError):
            select_port([19700, 19700])
    finally:
        s.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_port.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.port'`

- [ ] **Step 3: 实现端口选择**

`capcut_helper/backend/app/core/port.py`:

```python
import socket


def select_port(port_range: list[int]) -> int:
    """在 [port_range[0], port_range[1]] 闭区间内挑第一个能绑定的端口。
    整段都被占用则抛 RuntimeError。"""
    start, end = port_range[0], port_range[1]
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口段 {start}-{end} 全部被占用")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_port.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/port.py capcut_helper/backend/tests/test_port.py
git commit -m "feat(capcut_helper): 端口段选择"
```

---

## Task 10: FastAPI 服务、API 路由与入口

**Files:**
- Create: `capcut_helper/backend/app/api/health.py`
- Create: `capcut_helper/backend/app/api/drafts.py`
- Create: `capcut_helper/backend/app/api/tasks.py`
- Create: `capcut_helper/backend/app/api/config.py`
- Create: `capcut_helper/backend/app/api/router.py`
- Create: `capcut_helper/backend/app/server.py`
- Create: `capcut_helper/backend/app/main.py`
- Test: `capcut_helper/backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试**

`capcut_helper/backend/tests/test_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.schemas.timeline import TimelineSpec
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


def _valid_spec_body():
    return {
        "draft_name": "api_test",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {"url": "https://x/a.mp4", "type": "video", "filename": "a.mp4"},
                        "timeline": {"start": 0, "duration": 1000000},
                    }
                ],
            }
        ],
    }


def test_health_returns_service_identity(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["service"] == "capcut_helper"
    assert data["port"] == 9527
    assert "version" in data


def test_get_and_put_config(client, tmp_path):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    assert resp.json()["data"]["port_range"] == [9527, 9536]

    new_root = str(tmp_path / "drafts")
    resp = client.put("/api/v1/config", json={"draft_root": new_root, "port_range": [9527, 9536], "cors_origins": []})
    assert resp.status_code == 200
    assert client.get("/api/v1/config").json()["data"]["draft_root"] == new_root


def test_get_task_404_for_unknown_id(client):
    resp = client.get("/api/v1/tasks/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == 1003


def test_post_drafts_returns_task_id(client, monkeypatch):
    # 不真正跑后台任务，只验证端点校验规格并返回 task_id
    async def _noop(task_id, spec):
        return None
    monkeypatch.setattr("app.api.drafts.run_draft_task", _noop)

    resp = client.post("/api/v1/drafts", json=_valid_spec_body())
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]
    assert task_id
    # 该 task 能被 tasks 端点查到
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 200


def test_post_drafts_422_on_invalid_spec(client):
    bad = _valid_spec_body()
    bad["draft_name"] = ""  # 非法
    resp = client.post("/api/v1/drafts", json=bad)
    assert resp.status_code == 422
    assert resp.json()["code"] == 422


def test_get_drafts_lists_draft_folders(client, tmp_path):
    # config fixture 已把 draft_root 设到 tmp_path/drafts，往里建两个文件夹
    (tmp_path / "drafts" / "草稿A").mkdir()
    (tmp_path / "drafts" / "草稿B").mkdir()
    resp = client.get("/api/v1/drafts")
    assert resp.status_code == 200
    names = resp.json()["data"]
    assert "草稿A" in names and "草稿B" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.server'`

- [ ] **Step 3: 实现 health 路由**

`capcut_helper/backend/app/api/health.py`:

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
        },
    }
```

- [ ] **Step 4: 实现 drafts 路由**

`capcut_helper/backend/app/api/drafts.py`:

```python
import asyncio

from fastapi import APIRouter

from app.core.config import load_config
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services.draft_service import run_draft_task
from pyJianYingDraft import DraftFolder

router = APIRouter()


@router.post("/drafts")
async def create_draft(spec: TimelineSpec):
    state = registry.create()
    asyncio.create_task(run_draft_task(state.id, spec))
    return {"code": 0, "message": "ok", "data": {"task_id": state.id}}


@router.get("/drafts")
async def list_drafts():
    cfg = load_config()
    if not cfg.draft_root:
        return {"code": 0, "message": "ok", "data": []}
    names = DraftFolder(cfg.draft_root).list_drafts()
    return {"code": 0, "message": "ok", "data": names}
```

> 说明：POST 路由内直接 `asyncio.create_task(run_draft_task(...))`，而非调用 `draft_service.dispatch_draft_task`，是为了让测试能直接 monkeypatch `app.api.drafts.run_draft_task`。`dispatch_draft_task` 保留给 Plan 2 的桌面 GUI 复用。

- [ ] **Step 5: 实现 tasks 路由**

`capcut_helper/backend/app/api/tasks.py`:

```python
from fastapi import APIRouter

from app.core.exceptions import TaskNotFound
from app.core.tasks import registry

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    state = registry.get(task_id)
    if state is None:
        raise TaskNotFound(f"任务不存在: {task_id}")
    return {"code": 0, "message": "ok", "data": state.to_dict()}
```

- [ ] **Step 6: 实现 config 路由**

`capcut_helper/backend/app/api/config.py`:

```python
from fastapi import APIRouter

from app.core.config import Config, load_config, save_config

router = APIRouter()


@router.get("/config")
async def get_config():
    return {"code": 0, "message": "ok", "data": load_config().model_dump()}


@router.put("/config")
async def put_config(cfg: Config):
    save_config(cfg)
    return {"code": 0, "message": "ok", "data": cfg.model_dump()}
```

- [ ] **Step 7: 实现路由聚合**

`capcut_helper/backend/app/api/router.py`:

```python
from fastapi import APIRouter

from app.api import config, drafts, health, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(drafts.router)
api_router.include_router(tasks.router)
api_router.include_router(config.router)
```

- [ ] **Step 8: 实现 server.py**

`capcut_helper/backend/app/server.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.exceptions import register_exception_handlers


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__

    cfg = load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app
```

- [ ] **Step 9: 实现 main.py 入口**

`capcut_helper/backend/app/main.py`:

```python
import uvicorn

from app.core.config import load_config
from app.core.port import select_port
from app.server import create_app


def main() -> None:
    cfg = load_config()
    port = select_port(cfg.port_range)
    app = create_app(port)
    print(f"capcut_helper backend running on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 运行测试确认通过**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS（7 passed）

- [ ] **Step 11: 手动验证服务可启动**

Run: `uv run python -m app.main`（后台启动；记下打印的端口，假设 9527）
然后另开终端 Run: `curl -s http://127.0.0.1:9527/api/v1/health`
Expected: 返回 `{"code":0,"message":"ok","data":{"service":"capcut_helper","version":"0.1.0","port":9527}}`
验证后停掉服务进程。

- [ ] **Step 12: Commit**

```bash
git add capcut_helper/backend/app/api capcut_helper/backend/app/server.py capcut_helper/backend/app/main.py capcut_helper/backend/tests/test_api.py
git commit -m "feat(capcut_helper): FastAPI 服务、API 路由与启动入口"
```

---

## Task 11: 端到端集成测试

**Files:**
- Test: `capcut_helper/backend/tests/test_e2e_draft.py`

- [ ] **Step 1: 写端到端测试**

`capcut_helper/backend/tests/test_e2e_draft.py`:

```python
import json

import httpx
import respx

from app.core import config as config_mod
from app.core.tasks import registry
from app.schemas.timeline import TimelineSpec
from app.services.draft_service import run_draft_task
from tests.conftest import SAMPLE1_DURATION, SAMPLE2_DURATION


@respx.mock
async def test_full_draft_creation_flow(tmp_path, monkeypatch, fixture_video_1, fixture_video_2):
    # 真实跑：mock 掉 HTTP 下载，其余（建草稿、填片段、保存）都用真实 pyJianYingDraft
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(draft_root)))

    respx.get("https://x/v1.mp4").mock(
        return_value=httpx.Response(200, content=fixture_video_1.read_bytes())
    )
    respx.get("https://x/v2.mp4").mock(
        return_value=httpx.Response(200, content=fixture_video_2.read_bytes())
    )

    spec = TimelineSpec.model_validate(
        {
            "draft_name": "e2e_draft",
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/v1.mp4", "type": "video", "filename": "v1.mp4"},
                            "timeline": {"start": 0, "duration": SAMPLE1_DURATION},
                        },
                        {
                            "material": {"url": "https://x/v2.mp4", "type": "video", "filename": "v2.mp4"},
                            "timeline": {"start": SAMPLE1_DURATION, "duration": SAMPLE2_DURATION},
                        },
                    ],
                }
            ],
        }
    )

    task = registry.create()
    await run_draft_task(task.id, spec)

    state = registry.get(task.id)
    assert state.status == "done", state.error
    assert state.progress == 100

    draft_dir = draft_root / "e2e_draft"
    # 素材已下载进草稿文件夹（自包含）
    assert len(list(draft_dir.glob("*.mp4"))) == 2

    content = json.loads((draft_dir / "draft_content.json").read_text("utf-8"))
    assert content["canvas_config"]["width"] == 1920
    assert len(content["tracks"]) == 1
    assert len(content["tracks"][0]["segments"]) == 2
    # 素材路径指向草稿文件夹内的副本
    for material in content["materials"]["videos"]:
        assert str(draft_dir) in material["path"]
```

- [ ] **Step 2: 运行端到端测试确认通过**

Run: `uv run pytest tests/test_e2e_draft.py -v`
Expected: PASS（1 passed）

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `uv run pytest -v`
Expected: 全部 PASS（约 31 passed），无 FAIL、无 ERROR。

- [ ] **Step 4: Commit**

```bash
git add capcut_helper/backend/tests/test_e2e_draft.py
git commit -m "test(capcut_helper): 草稿生成端到端集成测试"
```

---

## Task 12: README 与开发说明

**Files:**
- Create: `capcut_helper/backend/README.md`

- [ ] **Step 1: 写 README**

`capcut_helper/backend/README.md`:

```markdown
# capcut_helper 后端本地服务

剪映外挂助手的后端：FastAPI 本地服务，对外提供「从时间线规格新建剪映草稿」的 HTTP API。
设计文档见 `../docs/superpowers/specs/2026-05-14-capcut-helper-local-service-design.md`。

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理

## 开发

\`\`\`bash
uv sync                          # 安装依赖
uv run python -m app.main        # 启动服务（端口段 9527-9536 内自动选）
uv run pytest                    # 跑全部测试
uv run pytest tests/test_api.py  # 跑单个测试文件
\`\`\`

## API

所有响应为 `{code, message, data}` 格式，前缀 `/api/v1`：

- `GET /health` — 健康检查 + 服务身份标识（端口发现用）
- `POST /drafts` — 提交时间线规格，返回 `task_id`
- `GET /tasks/{task_id}` — 查任务进度/状态/结果
- `GET /drafts` — 列出剪映草稿根目录下的草稿
- `GET /config` `PUT /config` — 读写配置（剪映草稿根目录、端口段、CORS 白名单）

## 配置

配置存在用户配置目录（由 `platformdirs` 决定，如 macOS 的 `~/Library/Application Support/capcut_helper/config.json`）。
首次使用需通过 `PUT /config` 设置 `draft_root`（剪映草稿根目录）。

## 已知约束

剪映 6+ 草稿文件加密，本服务只能**新建**草稿，不能读取/修改剪映已保存过的草稿。详见设计文档第 2 节。
\`\`\`
```

- [ ] **Step 2: Commit**

```bash
git add capcut_helper/backend/README.md
git commit -m "docs(capcut_helper): 后端 README 与开发说明"
```

---

## Self-Review

**1. Spec coverage（设计文档逐节核对）：**

- §3.1 核心范围「本地 FastAPI 服务」→ Task 10；「从时间线规格新建剪映草稿」→ Task 7/8/11；「素材并发下载进草稿文件夹」→ Task 6；「桌面 GUI」「pywebview 原生桥」→ 明确划入 Plan 2，本计划开头已说明。
- §5 组件：本地服务 → Task 10；时间线 schema → Task 3；草稿构建 service → Task 8；素材下载器 → Task 6；后台任务运行器 → Task 8（`run_draft_task` + `dispatch_draft_task`）；jianying 集成层 → Task 7;配置 → Task 4。原生桥、React GUI → Plan 2。
- §7 API 契约：health/drafts POST+GET/tasks/config 全部 → Task 10；时间线规格 §7.1 → Task 3；任务状态 §7.2 → Task 5（`TaskState` 字段）；§7.3 health 身份标识 → Task 10（health 路由返回 service/version/port），端口段顺延 → Task 9。注：§7.3 的「ai-canvas 侧探测端口、写 localStorage」属于 ai-canvas 前端，不在 capcut_helper 任何计划内（设计文档亦如此界定）。
- §8 数据流：先建草稿再下素材的顺序坑 → Task 8 代码与注释、Task 7 docstring 均已落实。
- §9 错误处理：端口被占 → Task 9；素材下载失败重试 → Task 6；草稿根目录未配置 → Task 8（`DraftRootNotConfigured`）；规格非法 422 → Task 2（`RequestValidationError` handler）+ Task 10 测试；CORS → Task 10（`CORSMiddleware` + 只绑 `127.0.0.1`）；草稿名重名 → Task 7（`DraftNameConflict`）。「剪映已锁定草稿」检测锁文件：设计文档列为错误处理项，但 Plan 1 未实现 —— **见下方补充任务说明**。
- §10 测试策略：单元（schema/downloader）→ Task 3/6；集成 → Task 11；GUI/跨平台/打包 → Plan 2。

**关于「剪映已锁定草稿」：** 设计文档 §9 列了「检测草稿文件夹内的锁文件」。Plan 1 未单列任务实现它，原因：核心新建流程用 `allow_replace` 控制覆盖，锁文件检测是覆盖已有草稿时的边缘增强。**执行计划时如需补全**，可在 Task 7 `create_empty_draft` 内 `allow_replace=True` 分支前增加锁文件检查（剪映锁文件为草稿文件夹内的 `.locked`）。此处明确标注为已知缺口，留给执行者或后续迭代决定，不静默跳过。

**2. Placeholder scan：** 已通读，无 TBD/TODO/「类似 Task N」/「适当处理错误」等占位。每个改代码的 step 都有完整代码；每个测试 step 都有完整测试代码与预期。

**3. Type consistency：**
- `TimelineSpec` / `Track` / `Segment` / `Material` / `Canvas` / `TimeRange` / `TextContent`：Task 3 定义，Task 6/7/8/10/11 使用一致。
- `Material.material_urls()` → `TimelineSpec.material_urls()`：Task 3 定义为 `TimelineSpec` 方法，Task 8 `spec.material_urls()` 调用一致。
- `TaskState`（`id/status/progress/result/error` + `to_dict()`）：Task 5 定义，Task 8 `registry.update(...)`、Task 10 `state.to_dict()` 一致。
- `registry`（`TaskRegistry` 单例）：Task 5 定义，Task 8/10 import 一致。
- `builder.create_empty_draft / populate_draft / save_draft`：Task 7 定义，Task 8 调用签名一致（`create_empty_draft(draft_root, spec)` → `(script, draft_dir)`）。
- `download_materials(materials, dest_dir, retries=3)`：Task 6 定义，Task 8 `download_materials(spec.material_urls(), draft_dir)` 一致。
- `Config`（`draft_root/port_range/cors_origins`）+ `load_config/save_config`：Task 4 定义，Task 8/10 使用一致。
- `select_port(port_range)`：Task 9 定义，Task 10 `main.py` 使用一致。
- `create_app(port)`：Task 10 定义，`main.py` 与 `test_api.py` 使用一致。
- `register_exception_handlers(app)`：Task 2 定义，Task 10 `server.py` 使用一致。

无签名/命名漂移。
