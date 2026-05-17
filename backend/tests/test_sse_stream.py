"""GET /api/v1/tasks/{id}/stream SSE 端到端测试。

TestClient 的 stream 模式是同步迭代器（背后跑一个独立线程跑 ASGI），所以可以
在主线程里一边读 stream，一边在另一个线程触发 registry 状态变化。
"""
import json
import threading
import time
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.tasks import registry
from app.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """SSE 的 idle ping 间隔生产是 15s，测试里太长——TestClient 的同步 stream
    在 generator return 后会再等一次 wait_for 才彻底关连接，让每个 SSE 测试
    卡 15s。降到 200ms 不影响生产逻辑。"""
    monkeypatch.setattr("app.api.tasks._IDLE_PING_INTERVAL_S", 0.2)
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(tmp_path)))
    app = create_app(port=9527)
    return TestClient(app)


def _parse_sse(line_iter: Iterator[str]) -> list[tuple[str, dict]]:
    """从行迭代器解析 SSE 事件。遇到 done 事件就停止收集。
    格式：
        event: progress
        data: {"...": "..."}
        (空行)
    """
    events: list[tuple[str, dict]] = []
    current_event = None
    for raw in line_iter:
        line = raw.rstrip("\n").rstrip("\r")
        if line.startswith(":"):
            # 注释（如 ": ping"），忽略
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            payload = line[5:].strip()
            data = json.loads(payload)
            events.append((current_event, data))
            if current_event == "done":
                return events
        # 空行 / 别的：忽略
    return events


def test_stream_404_for_unknown_task(client):
    resp = client.get("/api/v1/tasks/does-not-exist/stream")
    assert resp.status_code == 404


def test_stream_emits_initial_snapshot_then_progress_then_done(client):
    """SSE 上来立刻收到 progress 快照；后台触发 status 变化收到对应事件；
    任务 done 后服务端主动关闭，客户端 iter 结束。"""
    state = registry.create("sse_test")

    # 后台线程：等 SSE 连接稳定后推进 task 状态
    def _drive():
        time.sleep(0.05)  # 给 SSE handler 一点时间订阅
        registry.update(state.id, status="downloading", progress=20)
        time.sleep(0.05)
        registry.update(state.id, status="done", progress=100, result="/tmp/draft")

    threading.Thread(target=_drive, daemon=True).start()

    with client.stream("GET", f"/api/v1/tasks/{state.id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.iter_lines())

    statuses = [(evt, data["status"]) for evt, data in events]
    # 初始快照（pending） → downloading → done(progress) → done(close)
    assert statuses[0] == ("progress", "pending")
    assert ("progress", "downloading") in statuses
    assert ("progress", "done") in statuses
    assert events[-1][0] == "done"
    assert events[-1][1]["result"] == "/tmp/draft"


def test_stream_for_already_finished_task_closes_immediately(client):
    """订阅一个已结束的 task：先收一条 progress 快照，再立刻收 done，连接关闭。"""
    state = registry.create("sse_done_test")
    registry.update(state.id, status="done", progress=100, result="/tmp/d")

    with client.stream("GET", f"/api/v1/tasks/{state.id}/stream") as resp:
        events = _parse_sse(resp.iter_lines())

    assert [e[0] for e in events] == ["progress", "done"]
    assert events[1][1]["status"] == "done"


def test_stream_includes_subtasks_in_payload(client):
    """SSE payload 必须含 subtasks 字段，调用方据此渲染每个素材的下载进度。"""
    from app.schemas.timeline import Material

    state = registry.create("sse_subtask_test")
    registry.init_subtasks(state.id, [
        Material(url="https://x/a.mp4", type="video", filename="a.mp4"),
        Material(url="https://x/b.mp4", type="video", filename="b.mp4"),
    ])

    def _drive():
        time.sleep(0.05)
        registry.update(state.id, status="downloading", progress=10)
        time.sleep(0.05)
        registry.update_subtask(state.id, "https://x/a.mp4",
                                status="done", bytes_downloaded=1000, total_bytes=1000)
        time.sleep(0.05)
        registry.update(state.id, status="done", progress=100)

    threading.Thread(target=_drive, daemon=True).start()

    with client.stream("GET", f"/api/v1/tasks/{state.id}/stream") as resp:
        events = _parse_sse(resp.iter_lines())

    # 至少一条事件的 subtasks 里 a.mp4 status=done progress=100
    a_done_seen = any(
        any(s["name"] == "a.mp4" and s["status"] == "done" for s in data.get("subtasks", []))
        for _, data in events
    )
    assert a_done_seen
