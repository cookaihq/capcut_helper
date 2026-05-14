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
