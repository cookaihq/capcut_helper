# capcut_helper Backend Local Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend local service for capcut_helper — a FastAPI server that accepts a timeline spec over HTTP, concurrently downloads materials into a new 剪映 draft folder, and builds a plaintext 剪映 draft via pyJianYingDraft.

**Architecture:** Single FastAPI app exposing `/api/v1/...`. A `POST /drafts` request validates a timeline spec, registers an in-memory background task, and returns a `task_id` immediately. The background worker creates an empty draft folder (pyJianYingDraft `create_draft`, which wipes the folder), downloads materials into it, then adds tracks/segments and saves. Callers poll `GET /tasks/{task_id}` for progress.

**Tech Stack:** Python 3.11, uv, FastAPI, uvicorn, httpx, Pydantic v2, pyJianYingDraft, platformdirs, pytest + pytest-asyncio + pytest-httpx.

**Scope note:** This is **Plan 1 of 2**. It delivers the backend, which is independently testable via `pytest` and `curl` — no GUI required. **Plan 2** (separate) covers the pywebview desktop shell, the native js_api bridge, and the React GUI. Do not implement GUI/pywebview here.

**Spec:** `capcut_helper/docs/superpowers/specs/2026-05-14-capcut-helper-local-service-design.md`

---

## File Structure

All paths relative to repo root `ai-tools-v2/`.

| File | Responsibility |
|------|----------------|
| `capcut_helper/backend/pyproject.toml` | uv project, dependencies, pytest config |
| `capcut_helper/backend/app/__init__.py` | package marker |
| `capcut_helper/backend/app/core/constants.py` | `SERVICE_NAME`, `VERSION` |
| `capcut_helper/backend/app/core/exceptions.py` | `AppException` hierarchy |
| `capcut_helper/backend/app/core/config.py` | `Config` model, `load_config` / `save_config` (JSON file via platformdirs) |
| `capcut_helper/backend/app/core/tasks.py` | `TaskState`, `TaskRegistry`, module-global `registry` |
| `capcut_helper/backend/app/core/net.py` | `select_port` — first free port in a range |
| `capcut_helper/backend/app/schemas/responses.py` | `Envelope` response wrapper |
| `capcut_helper/backend/app/schemas/timeline.py` | `TimelineSpec` and nested models |
| `capcut_helper/backend/app/services/downloader.py` | concurrent material download with retry |
| `capcut_helper/backend/app/services/draft_service.py` | `build_draft_worker` — orchestrates the background task |
| `capcut_helper/backend/app/services/draft_list.py` | `list_drafts` — drafts under the configured root |
| `capcut_helper/backend/app/integrations/jianying/builder.py` | thin pyJianYingDraft wrapper: create / populate / save |
| `capcut_helper/backend/app/api/router.py` | aggregates sub-routers |
| `capcut_helper/backend/app/api/health.py` | `GET /health` |
| `capcut_helper/backend/app/api/drafts.py` | `POST /drafts`, `GET /drafts` |
| `capcut_helper/backend/app/api/tasks.py` | `GET /tasks/{task_id}` |
| `capcut_helper/backend/app/api/config.py` | `GET /config`, `PUT /config` |
| `capcut_helper/backend/app/server.py` | `create_app` — FastAPI factory, CORS, exception handler |
| `capcut_helper/backend/app/main.py` | entry point — select port, run uvicorn |
| `capcut_helper/backend/tests/conftest.py` | shared fixtures |
| `capcut_helper/backend/tests/fixtures/` | sample video files for builder/integration tests |
| `capcut_helper/backend/tests/test_*.py` | one test module per component |

`__init__.py` files are also created under `app/core/`, `app/schemas/`, `app/services/`, `app/integrations/`, `app/integrations/jianying/`, `app/api/`.

---

## Task 1: Project scaffold and test fixtures

**Files:**
- Create: `capcut_helper/backend/pyproject.toml`
- Create: `capcut_helper/backend/app/__init__.py` and `__init__.py` under `app/core/`, `app/schemas/`, `app/services/`, `app/integrations/`, `app/integrations/jianying/`, `app/api/`
- Create: `capcut_helper/backend/tests/__init__.py`
- Create: `capcut_helper/backend/tests/fixtures/sample_video_1.mp4`, `capcut_helper/backend/tests/fixtures/sample_video_2.mp4` (copied from existing `capcut_helper/tests/2-1 (1).mp4` and `2-2 (1).mp4`)

- [ ] **Step 1: Create `pyproject.toml`**

`capcut_helper/backend/pyproject.toml`:

```toml
[project]
name = "capcut-helper-backend"
version = "0.1.0"
description = "Local service backend for capcut_helper"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pyJianYingDraft>=0.2.6",
    "platformdirs>=4.2",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.30",
]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package directories and `__init__.py` markers**

Run from repo root:

```bash
cd capcut_helper/backend
mkdir -p app/core app/schemas app/services app/integrations/jianying app/api tests/fixtures
touch app/__init__.py app/core/__init__.py app/schemas/__init__.py app/services/__init__.py app/integrations/__init__.py app/integrations/jianying/__init__.py app/api/__init__.py tests/__init__.py
```

- [ ] **Step 3: Copy sample video fixtures**

Run from repo root:

```bash
cp "capcut_helper/tests/2-1 (1).mp4" "capcut_helper/backend/tests/fixtures/sample_video_1.mp4"
cp "capcut_helper/tests/2-2 (1).mp4" "capcut_helper/backend/tests/fixtures/sample_video_2.mp4"
```

- [ ] **Step 4: Install dependencies**

Run from `capcut_helper/backend/`:

```bash
uv sync
```

Expected: creates `.venv/`, installs all dependencies including `pyjianyingdraft`.

- [ ] **Step 5: Verify the environment**

Run from `capcut_helper/backend/`:

```bash
uv run python -c "import fastapi, httpx, pyJianYingDraft, platformdirs; print('env OK')"
```

Expected: prints `env OK`.

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/pyproject.toml capcut_helper/backend/uv.lock capcut_helper/backend/app capcut_helper/backend/tests
git commit -m "chore(capcut_helper): scaffold backend project and test fixtures"
```

---

## Task 2: Constants, response envelope, exceptions

**Files:**
- Create: `capcut_helper/backend/app/core/constants.py`
- Create: `capcut_helper/backend/app/schemas/responses.py`
- Create: `capcut_helper/backend/app/core/exceptions.py`
- Test: `capcut_helper/backend/tests/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_exceptions.py`:

```python
from app.core.exceptions import (
    AppException,
    DraftConflictError,
    DraftRootNotConfiguredError,
    TaskNotFoundError,
)
from app.schemas.responses import Envelope


def test_envelope_defaults():
    env = Envelope(data={"x": 1})
    assert env.code == 0
    assert env.message == "ok"
    assert env.data == {"x": 1}


def test_app_exception_carries_code_and_status():
    exc = DraftConflictError("draft exists")
    assert isinstance(exc, AppException)
    assert exc.message == "draft exists"
    assert exc.code == 4090
    assert exc.status_code == 409


def test_distinct_exception_codes():
    codes = {
        DraftConflictError("a").code,
        DraftRootNotConfiguredError("b").code,
        TaskNotFoundError("c").code,
    }
    assert len(codes) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run from `capcut_helper/backend/`: `uv run pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.exceptions'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/core/constants.py`:

```python
SERVICE_NAME = "capcut_helper"
VERSION = "0.1.0"
```

`capcut_helper/backend/app/schemas/responses.py`:

```python
from typing import Any

from pydantic import BaseModel


class Envelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None
```

`capcut_helper/backend/app/core/exceptions.py`:

```python
class AppException(Exception):
    code = 1
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DraftRootNotConfiguredError(AppException):
    code = 4001
    status_code = 400


class DraftConflictError(AppException):
    code = 4090
    status_code = 409


class TaskNotFoundError(AppException):
    code = 4040
    status_code = 404
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/constants.py capcut_helper/backend/app/schemas/responses.py capcut_helper/backend/app/core/exceptions.py capcut_helper/backend/tests/test_exceptions.py
git commit -m "feat(capcut_helper): add constants, response envelope, exception hierarchy"
```

---

## Task 3: Timeline spec schemas

**Files:**
- Create: `capcut_helper/backend/app/schemas/timeline.py`
- Test: `capcut_helper/backend/tests/test_timeline_schema.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_timeline_schema.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.timeline import TimelineSpec


def _video_spec():
    return {
        "draft_name": "demo",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {
                            "url": "https://example.com/a.mp4",
                            "type": "video",
                            "filename": "a.mp4",
                        },
                        "timeline": {"start": 0, "duration": 9160000},
                    }
                ],
            }
        ],
    }


def test_valid_spec_parses():
    spec = TimelineSpec.model_validate(_video_spec())
    assert spec.draft_name == "demo"
    assert spec.allow_replace is False
    assert spec.canvas.width == 1920
    assert spec.tracks[0].segments[0].material.url == "https://example.com/a.mp4"


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


def test_unique_materials_dedups_by_url():
    data = _video_spec()
    seg = data["tracks"][0]["segments"][0]
    data["tracks"][0]["segments"].append(
        {
            "material": dict(seg["material"]),
            "timeline": {"start": 9160000, "duration": 9160000},
        }
    )
    spec = TimelineSpec.model_validate(data)
    materials = spec.unique_materials()
    assert len(materials) == 1
    assert materials[0].url == "https://example.com/a.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_timeline_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.timeline'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/schemas/timeline.py`:

```python
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Canvas(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(default=30, gt=0)


class Material(BaseModel):
    url: str
    type: Literal["video", "image", "audio"]
    filename: str


class TimeRange(BaseModel):
    start: int = Field(ge=0)       # microseconds on the timeline / within source
    duration: int = Field(gt=0)


class TextSpec(BaseModel):
    content: str


class Segment(BaseModel):
    material: Optional[Material] = None
    timeline: TimeRange
    source: Optional[TimeRange] = None
    text: Optional[TextSpec] = None


class Track(BaseModel):
    type: Literal["video", "audio", "text"]
    segments: list[Segment] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_segment_payload(self) -> "Track":
        for seg in self.segments:
            if self.type == "text":
                if seg.text is None:
                    raise ValueError("text 轨道的片段必须包含 text 字段")
            else:
                if seg.material is None:
                    raise ValueError(f"{self.type} 轨道的片段必须包含 material 字段")
        return self


class TimelineSpec(BaseModel):
    draft_name: str = Field(min_length=1)
    allow_replace: bool = False
    canvas: Canvas
    tracks: list[Track] = Field(min_length=1)

    def unique_materials(self) -> list[Material]:
        seen: set[str] = set()
        out: list[Material] = []
        for track in self.tracks:
            for seg in track.segments:
                if seg.material and seg.material.url not in seen:
                    seen.add(seg.material.url)
                    out.append(seg.material)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_timeline_schema.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/schemas/timeline.py capcut_helper/backend/tests/test_timeline_schema.py
git commit -m "feat(capcut_helper): add timeline spec schemas with segment validation"
```

---

## Task 4: Config load/save

**Files:**
- Create: `capcut_helper/backend/app/core/config.py`
- Create: `capcut_helper/backend/tests/conftest.py`
- Test: `capcut_helper/backend/tests/test_config.py`

- [ ] **Step 1: Write `conftest.py` with shared fixtures**

`capcut_helper/backend/tests/conftest.py`:

```python
from pathlib import Path

import pytest

from app.core import config as config_module

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config persistence to a temp file."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", cfg_path)
    return cfg_path


@pytest.fixture
def draft_root(tmp_path):
    """An empty directory standing in for the 剪映 draft root."""
    root = tmp_path / "drafts"
    root.mkdir()
    return root
```

- [ ] **Step 2: Write the failing test**

`capcut_helper/backend/tests/test_config.py`:

```python
from app.core.config import Config, load_config, save_config


def test_load_returns_defaults_when_no_file(tmp_config):
    cfg = load_config()
    assert cfg.draft_root is None
    assert cfg.port_range == [9527, 9536]
    assert "http://localhost:3182" in cfg.cors_origins


def test_save_then_load_roundtrip(tmp_config):
    save_config(Config(draft_root="/tmp/drafts", port_range=[9000, 9005]))
    cfg = load_config()
    assert cfg.draft_root == "/tmp/drafts"
    assert cfg.port_range == [9000, 9005]
    assert tmp_config.exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'` (or `ImportError` for `CONFIG_PATH`).

- [ ] **Step 4: Write the implementation**

`capcut_helper/backend/app/core/config.py`:

```python
from pathlib import Path

from platformdirs import user_config_dir
from pydantic import BaseModel

from app.core.constants import SERVICE_NAME

CONFIG_PATH = Path(user_config_dir(SERVICE_NAME)) / "config.json"


class Config(BaseModel):
    draft_root: str | None = None
    port_range: list[int] = [9527, 9536]
    cors_origins: list[str] = [
        "http://localhost:3182",
        "http://localhost:3183",
    ]


def load_config() -> Config:
    if CONFIG_PATH.exists():
        return Config.model_validate_json(CONFIG_PATH.read_text(encoding="utf-8"))
    return Config()


def save_config(config: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/core/config.py capcut_helper/backend/tests/conftest.py capcut_helper/backend/tests/test_config.py
git commit -m "feat(capcut_helper): add JSON-file config with platformdirs"
```

---

## Task 5: In-memory task registry

**Files:**
- Create: `capcut_helper/backend/app/core/tasks.py`
- Test: `capcut_helper/backend/tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_tasks.py`:

```python
from app.core.tasks import TaskRegistry


def test_create_returns_pending_task_with_id():
    reg = TaskRegistry()
    task = reg.create()
    assert task.task_id
    assert task.status == "pending"
    assert task.progress == 0
    assert task.result is None
    assert task.error is None


def test_get_unknown_task_returns_none():
    reg = TaskRegistry()
    assert reg.get("does-not-exist") is None


def test_update_mutates_stored_task():
    reg = TaskRegistry()
    task = reg.create()
    reg.update(task.task_id, status="done", progress=100, result="/path/to/draft")
    fetched = reg.get(task.task_id)
    assert fetched.status == "done"
    assert fetched.progress == 100
    assert fetched.result == "/path/to/draft"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.tasks'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/core/tasks.py`:

```python
import uuid
from typing import Literal, Optional

from pydantic import BaseModel

TaskStatus = Literal["pending", "downloading", "building", "done", "failed"]


class TaskState(BaseModel):
    task_id: str
    status: TaskStatus = "pending"
    progress: int = 0
    result: Optional[str] = None
    error: Optional[str] = None


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}

    def create(self) -> TaskState:
        task_id = uuid.uuid4().hex
        state = TaskState(task_id=task_id)
        self._tasks[task_id] = state
        return state

    def get(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **fields) -> None:
        state = self._tasks[task_id]
        for key, value in fields.items():
            setattr(state, key, value)


registry = TaskRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/core/tasks.py capcut_helper/backend/tests/test_tasks.py
git commit -m "feat(capcut_helper): add in-memory task registry"
```

---

## Task 6: Material downloader

**Files:**
- Create: `capcut_helper/backend/app/services/downloader.py`
- Test: `capcut_helper/backend/tests/test_downloader.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_downloader.py`:

```python
import httpx
import pytest

from app.schemas.timeline import Material
from app.services.downloader import download_materials


def _material(url: str, filename: str = "clip.mp4") -> Material:
    return Material(url=url, type="video", filename=filename)


async def test_downloads_content_into_dest_dir(httpx_mock, tmp_path):
    httpx_mock.add_response(url="https://example.com/a.mp4", content=b"AAA")
    result = await download_materials([_material("https://example.com/a.mp4")], tmp_path)
    saved = result["https://example.com/a.mp4"]
    assert saved.parent == tmp_path
    assert saved.read_bytes() == b"AAA"


async def test_distinct_urls_get_distinct_files(httpx_mock, tmp_path):
    httpx_mock.add_response(url="https://example.com/a.mp4", content=b"AAA")
    httpx_mock.add_response(url="https://example.com/b.mp4", content=b"BBB")
    result = await download_materials(
        [
            _material("https://example.com/a.mp4", "same.mp4"),
            _material("https://example.com/b.mp4", "same.mp4"),
        ],
        tmp_path,
    )
    assert result["https://example.com/a.mp4"] != result["https://example.com/b.mp4"]
    assert result["https://example.com/a.mp4"].read_bytes() == b"AAA"
    assert result["https://example.com/b.mp4"].read_bytes() == b"BBB"


async def test_retries_then_succeeds(httpx_mock, tmp_path):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_response(url="https://example.com/a.mp4", content=b"AAA")
    result = await download_materials([_material("https://example.com/a.mp4")], tmp_path)
    assert result["https://example.com/a.mp4"].read_bytes() == b"AAA"


async def test_persistent_failure_raises_with_url(httpx_mock, tmp_path):
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    with pytest.raises(RuntimeError, match="https://example.com/a.mp4"):
        await download_materials([_material("https://example.com/a.mp4")], tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.downloader'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/services/downloader.py`:

```python
import asyncio
import hashlib
from pathlib import Path

import httpx

from app.schemas.timeline import Material

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 60.0


def _safe_name(material: Material) -> str:
    digest = hashlib.sha256(material.url.encode("utf-8")).hexdigest()[:8]
    base = Path(material.filename).name or "material"
    return f"{digest}_{base}"


async def _download_one(
    client: httpx.AsyncClient, material: Material, dest_dir: Path
) -> Path:
    dest = dest_dir / _safe_name(material)
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.get(
                material.url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            response.raise_for_status()
            dest.write_bytes(response.content)
            return dest
        except Exception as error:  # noqa: BLE001 - retried then re-raised below
            last_error = error
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"下载素材失败: {material.url} ({last_error})")


async def download_materials(
    materials: list[Material], dest_dir: Path
) -> dict[str, Path]:
    """Download each material into dest_dir. Returns {url: local Path}."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_download_one(client, m, dest_dir) for m in materials),
            return_exceptions=True,
        )
    paths: dict[str, Path] = {}
    for material, result in zip(materials, results):
        if isinstance(result, Exception):
            raise result
        paths[material.url] = result
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/services/downloader.py capcut_helper/backend/tests/test_downloader.py
git commit -m "feat(capcut_helper): add concurrent material downloader with retry"
```

---

## Task 7: pyJianYingDraft builder integration

**Files:**
- Create: `capcut_helper/backend/app/integrations/jianying/builder.py`
- Test: `capcut_helper/backend/tests/test_jianying_builder.py`

**Background:** `DraftFolder.create_draft(name, w, h, fps=..., allow_replace=...)` does `shutil.rmtree` on the draft folder if it already exists, then recreates it empty — so materials MUST be downloaded **after** `create_empty_draft`. `create_draft` returns a `ScriptFile` whose `save_path` is already set; `script.save()` writes `draft_content.json`.

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_jianying_builder.py`:

```python
import json
import shutil

from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from tests.conftest import FIXTURES


def _spec_two_videos():
    return TimelineSpec.model_validate(
        {
            "draft_name": "builder_demo",
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {
                                "url": "https://example.com/v1.mp4",
                                "type": "video",
                                "filename": "v1.mp4",
                            },
                            "timeline": {"start": 0, "duration": 3000000},
                        },
                        {
                            "material": {
                                "url": "https://example.com/v2.mp4",
                                "type": "video",
                                "filename": "v2.mp4",
                            },
                            "timeline": {"start": 3000000, "duration": 3000000},
                        },
                    ],
                }
            ],
        }
    )


def test_build_writes_plaintext_draft_with_two_segments(draft_root):
    spec = _spec_two_videos()
    script, draft_dir = builder.create_empty_draft(str(draft_root), spec)
    assert draft_dir == draft_root / "builder_demo"

    # Simulate the downloader: copy fixtures into the draft folder.
    p1 = draft_dir / "v1.mp4"
    p2 = draft_dir / "v2.mp4"
    shutil.copy(FIXTURES / "sample_video_1.mp4", p1)
    shutil.copy(FIXTURES / "sample_video_2.mp4", p2)
    material_paths = {
        "https://example.com/v1.mp4": p1,
        "https://example.com/v2.mp4": p2,
    }

    builder.populate_draft(script, spec, material_paths)
    builder.save_draft(script)

    content_path = draft_dir / "draft_content.json"
    assert content_path.exists()
    data = json.loads(content_path.read_text(encoding="utf-8"))  # plaintext JSON
    assert data["canvas_config"]["width"] == 1920
    video_tracks = [t for t in data["tracks"] if t["type"] == "video"]
    assert len(video_tracks) == 1
    assert len(video_tracks[0]["segments"]) == 2
    material_file_paths = {m["path"] for m in data["materials"]["videos"]}
    assert str(p1) in material_file_paths
    assert str(p2) in material_file_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jianying_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.integrations.jianying.builder'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/integrations/jianying/builder.py`:

```python
from pathlib import Path

from pyJianYingDraft import (
    AudioMaterial,
    AudioSegment,
    DraftFolder,
    ScriptFile,
    TextSegment,
    TrackType,
    VideoMaterial,
    VideoSegment,
    trange,
)

from app.schemas.timeline import TimelineSpec

_TRACK_TYPE = {
    "video": TrackType.video,
    "audio": TrackType.audio,
    "text": TrackType.text,
}


def create_empty_draft(
    draft_root: str, spec: TimelineSpec
) -> tuple[ScriptFile, Path]:
    """Create (or replace) an empty draft folder. WARNING: replacing wipes the
    folder, so materials must be downloaded only after this call."""
    folder = DraftFolder(draft_root)
    script = folder.create_draft(
        spec.draft_name,
        spec.canvas.width,
        spec.canvas.height,
        fps=spec.canvas.fps,
        allow_replace=spec.allow_replace,
    )
    draft_dir = Path(draft_root) / spec.draft_name
    return script, draft_dir


def populate_draft(
    script: ScriptFile, spec: TimelineSpec, material_paths: dict[str, Path]
) -> None:
    for index, track in enumerate(spec.tracks):
        track_name = f"{track.type}_{index}"
        script.add_track(_TRACK_TYPE[track.type], track_name=track_name)
        for seg in track.segments:
            target = trange(seg.timeline.start, seg.timeline.duration)
            source = (
                trange(seg.source.start, seg.source.duration)
                if seg.source
                else None
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
            elif track.type == "text":
                script.add_segment(
                    TextSegment(seg.text.content, target),
                    track_name=track_name,
                )


def save_draft(script: ScriptFile) -> None:
    script.save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_jianying_builder.py -v`
Expected: PASS — 1 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/integrations/jianying/builder.py capcut_helper/backend/tests/test_jianying_builder.py
git commit -m "feat(capcut_helper): add pyJianYingDraft builder integration"
```

---

## Task 8: Draft orchestration service and draft listing

**Files:**
- Create: `capcut_helper/backend/app/services/draft_service.py`
- Create: `capcut_helper/backend/app/services/draft_list.py`
- Test: `capcut_helper/backend/tests/test_draft_service.py`

**Background:** `build_draft_worker` is the background coroutine. Order matters: `create_empty_draft` (wipes folder) → `download_materials` (into the folder) → `populate_draft` → `save_draft`. pyJianYingDraft calls are blocking, so run them via `anyio.to_thread.run_sync`. All failures are caught and recorded on the task as `status="failed"`.

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_draft_service.py`:

```python
import shutil

from app.core.config import Config, save_config
from app.core.tasks import TaskRegistry
from app.schemas.timeline import TimelineSpec
from app.services import draft_service
from app.services.draft_list import list_drafts
from tests.conftest import FIXTURES


def _spec():
    return TimelineSpec.model_validate(
        {
            "draft_name": "service_demo",
            "canvas": {"width": 1280, "height": 720, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {
                                "url": "https://example.com/v1.mp4",
                                "type": "video",
                                "filename": "v1.mp4",
                            },
                            "timeline": {"start": 0, "duration": 3000000},
                        }
                    ],
                }
            ],
        }
    )


async def test_worker_builds_draft_and_marks_done(
    tmp_config, draft_root, monkeypatch
):
    save_config(Config(draft_root=str(draft_root)))

    async def fake_download(materials, dest_dir):
        out = {}
        for material in materials:
            target = dest_dir / "v1.mp4"
            shutil.copy(FIXTURES / "sample_video_1.mp4", target)
            out[material.url] = target
        return out

    monkeypatch.setattr(draft_service, "download_materials", fake_download)
    reg = TaskRegistry()
    monkeypatch.setattr(draft_service, "registry", reg)

    task = reg.create()
    await draft_service.build_draft_worker(task.task_id, _spec())

    state = reg.get(task.task_id)
    assert state.status == "done"
    assert state.progress == 100
    assert state.result == str(draft_root / "service_demo")
    assert (draft_root / "service_demo" / "draft_content.json").exists()


async def test_worker_marks_failed_when_draft_root_missing(
    tmp_config, monkeypatch
):
    save_config(Config(draft_root=None))
    reg = TaskRegistry()
    monkeypatch.setattr(draft_service, "registry", reg)

    task = reg.create()
    await draft_service.build_draft_worker(task.task_id, _spec())

    state = reg.get(task.task_id)
    assert state.status == "failed"
    assert state.error


def test_list_drafts_returns_built_drafts(tmp_config, draft_root):
    save_config(Config(draft_root=str(draft_root)))
    built = draft_root / "service_demo"
    built.mkdir()
    (built / "draft_content.json").write_text("{}", encoding="utf-8")
    (draft_root / "not_a_draft").mkdir()

    drafts = list_drafts()
    names = {d["name"] for d in drafts}
    assert "service_demo" in names
    assert "not_a_draft" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_draft_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.draft_service'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/services/draft_service.py`:

```python
import anyio

from app.core.config import load_config
from app.core.exceptions import DraftRootNotConfiguredError
from app.core.tasks import registry
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from app.services.downloader import download_materials


async def build_draft_worker(task_id: str, spec: TimelineSpec) -> None:
    """Background coroutine: create draft folder, download materials into it,
    populate tracks/segments, save. Records progress and failures on the task."""
    try:
        config = load_config()
        if not config.draft_root:
            raise DraftRootNotConfiguredError("剪映草稿根目录未配置")

        registry.update(task_id, status="building", progress=10)
        script, draft_dir = await anyio.to_thread.run_sync(
            builder.create_empty_draft, config.draft_root, spec
        )

        registry.update(task_id, status="downloading", progress=30)
        material_paths = await download_materials(spec.unique_materials(), draft_dir)

        registry.update(task_id, status="building", progress=70)
        await anyio.to_thread.run_sync(
            builder.populate_draft, script, spec, material_paths
        )
        await anyio.to_thread.run_sync(builder.save_draft, script)

        registry.update(
            task_id, status="done", progress=100, result=str(draft_dir)
        )
    except Exception as error:  # noqa: BLE001 - recorded on the task
        registry.update(task_id, status="failed", error=str(error))
```

`capcut_helper/backend/app/services/draft_list.py`:

```python
from pathlib import Path

from app.core.config import load_config


def list_drafts() -> list[dict]:
    """List draft folders under the configured 剪映 draft root."""
    config = load_config()
    if not config.draft_root:
        return []
    root = Path(config.draft_root)
    if not root.exists():
        return []
    drafts: list[dict] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "draft_content.json").exists():
            drafts.append({"name": child.name, "path": str(child)})
    return drafts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_draft_service.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/services/draft_service.py capcut_helper/backend/app/services/draft_list.py capcut_helper/backend/tests/test_draft_service.py
git commit -m "feat(capcut_helper): add draft orchestration worker and draft listing"
```

---

## Task 9: FastAPI server and API routes

**Files:**
- Create: `capcut_helper/backend/app/api/health.py`
- Create: `capcut_helper/backend/app/api/drafts.py`
- Create: `capcut_helper/backend/app/api/tasks.py`
- Create: `capcut_helper/backend/app/api/config.py`
- Create: `capcut_helper/backend/app/api/router.py`
- Create: `capcut_helper/backend/app/server.py`
- Test: `capcut_helper/backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from app.core.config import Config, load_config
from app.server import create_app


def _client():
    app = create_app()
    app.state.port = 9527
    return TestClient(app)


def test_health_returns_service_identity():
    client = _client()
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["service"] == "capcut_helper"
    assert body["data"]["port"] == 9527


def test_post_drafts_returns_task_id(tmp_config, draft_root):
    client = _client()
    spec = {
        "draft_name": "api_demo",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {
                            "url": "https://example.com/a.mp4",
                            "type": "video",
                            "filename": "a.mp4",
                        },
                        "timeline": {"start": 0, "duration": 3000000},
                    }
                ],
            }
        ],
    }
    resp = client.post("/api/v1/drafts", json=spec)
    assert resp.status_code == 200
    assert resp.json()["data"]["task_id"]


def test_post_drafts_rejects_invalid_spec():
    client = _client()
    resp = client.post("/api/v1/drafts", json={"draft_name": ""})
    assert resp.status_code == 422


def test_get_unknown_task_returns_404():
    client = _client()
    resp = client.get("/api/v1/tasks/nope")
    assert resp.status_code == 404
    assert resp.json()["code"] == 4040


def test_config_get_and_put_roundtrip(tmp_config):
    client = _client()
    new_config = Config(draft_root="/tmp/x", port_range=[9000, 9001]).model_dump()
    put_resp = client.put("/api/v1/config", json=new_config)
    assert put_resp.status_code == 200
    get_resp = client.get("/api/v1/config")
    assert get_resp.json()["data"]["draft_root"] == "/tmp/x"
    assert load_config().draft_root == "/tmp/x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.server'`.

- [ ] **Step 3: Write the route modules**

`capcut_helper/backend/app/api/health.py`:

```python
from fastapi import APIRouter, Request

from app.core.constants import SERVICE_NAME, VERSION
from app.schemas.responses import Envelope

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> Envelope:
    return Envelope(
        data={
            "service": SERVICE_NAME,
            "version": VERSION,
            "port": getattr(request.app.state, "port", None),
        }
    )
```

`capcut_helper/backend/app/api/drafts.py`:

```python
import asyncio

from fastapi import APIRouter

from app.core.tasks import registry
from app.schemas.responses import Envelope
from app.schemas.timeline import TimelineSpec
from app.services.draft_list import list_drafts
from app.services.draft_service import build_draft_worker

router = APIRouter()


@router.post("/drafts")
async def create_draft(spec: TimelineSpec) -> Envelope:
    task = registry.create()
    asyncio.create_task(build_draft_worker(task.task_id, spec))
    return Envelope(data={"task_id": task.task_id})


@router.get("/drafts")
async def get_drafts() -> Envelope:
    return Envelope(data=list_drafts())
```

`capcut_helper/backend/app/api/tasks.py`:

```python
from fastapi import APIRouter

from app.core.exceptions import TaskNotFoundError
from app.core.tasks import registry
from app.schemas.responses import Envelope

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> Envelope:
    state = registry.get(task_id)
    if state is None:
        raise TaskNotFoundError(f"任务不存在: {task_id}")
    return Envelope(data=state.model_dump())
```

`capcut_helper/backend/app/api/config.py`:

```python
from fastapi import APIRouter

from app.core.config import Config, load_config, save_config
from app.schemas.responses import Envelope

router = APIRouter()


@router.get("/config")
async def get_config() -> Envelope:
    return Envelope(data=load_config().model_dump())


@router.put("/config")
async def put_config(config: Config) -> Envelope:
    save_config(config)
    return Envelope(data=config.model_dump())
```

`capcut_helper/backend/app/api/router.py`:

```python
from fastapi import APIRouter

from app.api import config, drafts, health, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(drafts.router)
api_router.include_router(tasks.router)
api_router.include_router(config.router)
```

- [ ] **Step 4: Write the server factory**

`capcut_helper/backend/app/server.py`:

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import load_config
from app.core.constants import SERVICE_NAME
from app.core.exceptions import AppException


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_NAME)
    config = load_config()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.exception_handler(AppException)
    async def _handle_app_exception(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/api capcut_helper/backend/app/server.py capcut_helper/backend/tests/test_api.py
git commit -m "feat(capcut_helper): add FastAPI server and API routes"
```

---

## Task 10: Port selection and entry point

**Files:**
- Create: `capcut_helper/backend/app/core/net.py`
- Create: `capcut_helper/backend/app/main.py`
- Test: `capcut_helper/backend/tests/test_net.py`

- [ ] **Step 1: Write the failing test**

`capcut_helper/backend/tests/test_net.py`:

```python
import socket

import pytest

from app.core.net import select_port


def test_select_port_returns_a_port_in_range():
    port = select_port([20000, 20010])
    assert 20000 <= port <= 20010


def test_select_port_skips_occupied_port():
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    occupied.bind(("127.0.0.1", 20020))
    try:
        port = select_port([20020, 20021])
        assert port == 20021
    finally:
        occupied.close()


def test_select_port_raises_when_range_exhausted():
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 20030))
    try:
        with pytest.raises(RuntimeError, match="端口段"):
            select_port([20030, 20030])
    finally:
        occupied.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_net.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.net'`.

- [ ] **Step 3: Write the implementation**

`capcut_helper/backend/app/core/net.py`:

```python
import socket


def select_port(port_range: list[int]) -> int:
    """Return the first bindable port in [start, end] on 127.0.0.1."""
    start, end = port_range[0], port_range[1]
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口段 {start}-{end} 全部被占用")
```

`capcut_helper/backend/app/main.py`:

```python
import uvicorn

from app.core.config import load_config
from app.core.net import select_port
from app.server import create_app


def main() -> None:
    config = load_config()
    port = select_port(config.port_range)
    app = create_app()
    app.state.port = port
    print(f"capcut_helper 本地服务启动: http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_net.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Manually verify the server boots**

Run from `capcut_helper/backend/`:

```bash
uv run python -m app.main
```

Expected: prints `capcut_helper 本地服务启动: http://127.0.0.1:9527` and serves. In another terminal:

```bash
curl http://127.0.0.1:9527/api/v1/health
```

Expected: `{"code":0,"message":"ok","data":{"service":"capcut_helper","version":"0.1.0","port":9527}}`. Stop the server with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add capcut_helper/backend/app/core/net.py capcut_helper/backend/app/main.py capcut_helper/backend/tests/test_net.py
git commit -m "feat(capcut_helper): add port selection and server entry point"
```

---

## Task 11: End-to-end integration test

**Files:**
- Test: `capcut_helper/backend/tests/test_integration.py`

**Background:** Drives the full flow through ASGI: `POST /drafts` → poll `GET /tasks/{id}` until terminal → assert the draft folder and its plaintext `draft_content.json` are correct. `httpx_mock` serves the fixture video bytes for the material URLs. The background worker (`asyncio.create_task`) runs during the polling `await asyncio.sleep` calls.

- [ ] **Step 1: Write the integration test**

`capcut_helper/backend/tests/test_integration.py`:

```python
import asyncio
import json

import httpx

from app.core.config import Config, save_config
from app.server import create_app
from tests.conftest import FIXTURES


async def test_post_drafts_builds_plaintext_draft(
    tmp_config, draft_root, httpx_mock
):
    save_config(Config(draft_root=str(draft_root)))

    video_bytes = (FIXTURES / "sample_video_1.mp4").read_bytes()
    httpx_mock.add_response(
        url="https://example.com/clip.mp4", content=video_bytes
    )

    app = create_app()
    app.state.port = 9527
    spec = {
        "draft_name": "integration_demo",
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "tracks": [
            {
                "type": "video",
                "segments": [
                    {
                        "material": {
                            "url": "https://example.com/clip.mp4",
                            "type": "video",
                            "filename": "clip.mp4",
                        },
                        "timeline": {"start": 0, "duration": 3000000},
                    }
                ],
            }
        ],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        post_resp = await client.post("/api/v1/drafts", json=spec)
        assert post_resp.status_code == 200
        task_id = post_resp.json()["data"]["task_id"]

        status = "pending"
        for _ in range(50):
            await asyncio.sleep(0.1)
            task_resp = await client.get(f"/api/v1/tasks/{task_id}")
            status = task_resp.json()["data"]["status"]
            if status in ("done", "failed"):
                break

        assert status == "done", task_resp.json()["data"].get("error")

        drafts_resp = await client.get("/api/v1/drafts")
        names = {d["name"] for d in drafts_resp.json()["data"]}
        assert "integration_demo" in names

    draft_dir = draft_root / "integration_demo"
    content = json.loads(
        (draft_dir / "draft_content.json").read_text(encoding="utf-8")
    )
    assert content["canvas_config"]["width"] == 1920
    video_tracks = [t for t in content["tracks"] if t["type"] == "video"]
    assert len(video_tracks) == 1
    assert len(video_tracks[0]["segments"]) == 1
    saved_material = content["materials"]["videos"][0]["path"]
    assert saved_material.startswith(str(draft_dir))
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS — 1 passed. (If it fails with the task stuck at `pending`/`downloading`, the worker is not progressing — check that `asyncio.create_task` in `drafts.py` is scheduling on the same loop.)

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS — all tests from Tasks 2–11 pass.

- [ ] **Step 4: Commit**

```bash
git add capcut_helper/backend/tests/test_integration.py
git commit -m "test(capcut_helper): add end-to-end draft build integration test"
```

---

## Self-Review Notes

- **Spec coverage:** §7 API contract → Tasks 3, 9 (all five endpoints). §7.1 timeline spec → Task 3. §7.2 task status → Tasks 5, 9. §7.3 health identity + port range → Tasks 9, 10. §8 data flow (create→download→populate→save, ordering pitfall) → Tasks 7, 8. §9 error handling: invalid spec (422) → Task 9; draft root missing → Task 8; port occupied → Task 10; draft name conflict → `allow_replace` in Tasks 3/7 (pyJianYingDraft raises `FileExistsError` when `allow_replace=False`, surfaced as task failure). §10 testing: unit + integration + plaintext-JSON assertion → Tasks 6–11. **Out of scope here (Plan 2):** pywebview shell, native bridge, React GUI, system notification fallback, "已连接/未连接" status, cross-platform packaging.
- **Placeholder scan:** none — every step has full code or exact commands.
- **Type consistency:** `Envelope`, `TimelineSpec`/`Material`/`TimeRange`, `TaskRegistry`/`TaskState`, `download_materials(materials, dest_dir) -> dict[str, Path]`, `create_empty_draft`/`populate_draft`/`save_draft`, `build_draft_worker(task_id, spec)`, `select_port(port_range)`, `create_app()` — names and signatures are consistent across tasks.
- **Known follow-ups for Plan 2:** `app/main.py` will be extended to launch the pywebview window; `app/server.py` will gain a static-file mount for the built React GUI; `app/native/` will be added for the js_api bridge.
