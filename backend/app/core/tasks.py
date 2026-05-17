from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal, Optional

TaskStatus = Literal["pending", "downloading", "building", "done", "failed"]
SubtaskStatus = Literal["pending", "downloading", "done", "failed"]


@dataclass
class Subtask:
    """一个素材下载的实时状态。每个 Task 在进入 downloading 阶段时按 spec 里
    去重后的素材列表初始化一组 Subtask；downloader 逐 chunk 回报进度，update
    时自动重算 progress 与父任务 progress。"""

    id: str               # 来自 URL 的 sha256 前 8 位，跨任务稳定
    name: str             # 来自 material.filename
    url: str
    status: SubtaskStatus = "pending"
    progress: int = 0
    bytes_downloaded: int = 0
    total_bytes: Optional[int] = None  # 来自 Content-Length，可能没有
    error: Optional[str] = None


@dataclass
class TaskState:
    id: str
    draft_name: str
    created_at: float
    status: TaskStatus = "pending"
    progress: int = 0
    result: Optional[str] = None
    error: Optional[str] = None
    subtasks: list[Subtask] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def subtask_id_for_url(url: str) -> str:
    """从 URL 派生稳定的 subtask id，与 downloader 的 _safe_filename 前缀一致。
    单一来源在此，downloader 和 task registry 都通过本函数算。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


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

    def init_subtasks(self, task_id: str, materials: Iterable) -> list[Subtask]:
        """初始化子任务列表。materials 是 spec.material_urls() 的返回值，已去重。
        必须在 status 切到 'downloading' 之前调用。"""
        state = self._tasks[task_id]
        state.subtasks = [
            Subtask(id=subtask_id_for_url(m.url), name=m.filename, url=m.url)
            for m in materials
        ]
        return state.subtasks

    def update_subtask(
        self,
        task_id: str,
        url: str,
        *,
        status: Optional[SubtaskStatus] = None,
        bytes_downloaded: Optional[int] = None,
        total_bytes: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Optional[Subtask]:
        """downloader 回调入口。按 url 找子任务，更新状态，自动派生 progress
        并重算父任务的整体 progress。找不到对应子任务返回 None。"""
        state = self._tasks.get(task_id)
        if state is None:
            return None
        sub = next((s for s in state.subtasks if s.url == url), None)
        if sub is None:
            return None

        if status is not None:
            sub.status = status
        if bytes_downloaded is not None:
            sub.bytes_downloaded = bytes_downloaded
        if total_bytes is not None:
            sub.total_bytes = total_bytes
        if error is not None:
            sub.error = error

        sub.progress = _derive_subtask_progress(sub)
        _recompute_task_progress(state)
        return sub


def _derive_subtask_progress(sub: Subtask) -> int:
    """根据 status / bytes 算出 0-100 的 progress。

    - done → 100
    - failed → 保留之前的 progress（不归零，便于 UI 显示"卡在哪"）
    - 有 total_bytes → bytes / total_bytes，cap 99（done 时才到 100）
    - 无 total_bytes → 用 bytes 大小估算（每 1MB ~10%，cap 95），适合 chunked 响应
    """
    if sub.status == "done":
        return 100
    if sub.status == "failed":
        return sub.progress
    if sub.total_bytes and sub.total_bytes > 0:
        return min(99, int(sub.bytes_downloaded / sub.total_bytes * 100))
    # 无 Content-Length：用 bytes 数推断
    mb = sub.bytes_downloaded / (1024 * 1024)
    return min(95, int(mb * 10))


def _recompute_task_progress(state: TaskState) -> None:
    """整体 progress 算法：
    - status != downloading：保留 update() 显式写入的值（draft_service 每阶段直接写）
    - status == downloading：10 + 80 * avg(subtask.progress) / 100，下载阶段占 10–90%
    """
    if state.status != "downloading":
        return
    if not state.subtasks:
        return
    avg = sum(s.progress for s in state.subtasks) / len(state.subtasks)
    state.progress = int(10 + 0.8 * avg)


# 进程级单例：API 层和后台任务共用同一个注册表
registry = TaskRegistry()
