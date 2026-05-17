"""restart 模块单元 + API 集成测试。

不能真去 Popen / os._exit；用 monkeypatch 替换底层调用，验证：
1. _build_spawn_command 在 dev / frozen 两种态下命令构造正确
2. _popen_kwargs 在 win32 / posix 下的 detach flag 正确
3. POST /api/v1/system/restart 立即返回 200 且把后台任务排到 spawn + _exit
"""
from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.api import system as system_api
from app.core import restart


@pytest.fixture
def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(system_api.router, prefix="/api/v1")
    return TestClient(app)


def test_build_spawn_command_dev_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["unused", "--flag"])
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert restart._build_spawn_command() == ["/usr/bin/python3", "-m", "app", "--flag"]


def test_build_spawn_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["unused", "capcut-helper://trust?origin=x"])
    monkeypatch.setattr(sys, "executable", "/Applications/CapcutHelper.app/Contents/MacOS/CapcutHelper")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert restart._build_spawn_command() == [
        "/Applications/CapcutHelper.app/Contents/MacOS/CapcutHelper",
        "capcut-helper://trust?origin=x",
    ]


def test_popen_kwargs_posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    kwargs = restart._popen_kwargs()
    assert kwargs["start_new_session"] is True
    assert kwargs["close_fds"] is True
    assert "creationflags" not in kwargs


def test_popen_kwargs_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    # subprocess 在非 Windows 平台上没有这俩常量，临时塞进去免 AttributeError
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    kwargs = restart._popen_kwargs()
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200
    assert "start_new_session" not in kwargs


def test_spawn_new_instance_invokes_popen(monkeypatch):
    calls: list[tuple] = []

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sys, "argv", ["unused"])
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.delattr(sys, "frozen", raising=False)

    restart.spawn_new_instance()

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["/usr/bin/python3", "-m", "app"]
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_restart_endpoint_returns_ok_and_schedules(client, monkeypatch):
    """接口立即返回 200；BackgroundTasks 在 TestClient 里同步执行，所以要
    把 _restart_now 替换成可观测的桩，避免真的 os._exit 把 pytest 进程干掉。"""
    invoked = []
    monkeypatch.setattr(system_api, "_restart_now", lambda: invoked.append(True))

    resp = client.post("/api/v1/system/restart")
    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "ok", "data": None}
    # TestClient 在响应返回后会跑 BackgroundTasks
    assert invoked == [True]


def test_restart_now_spawns_then_exits(monkeypatch):
    """_restart_now：成功 spawn 时调 os._exit(0)；spawn 失败时不退出。"""
    monkeypatch.setattr(system_api, "_RESPONSE_GRACE_SECONDS", 0)

    # 成功路径
    spawn_called = []
    exit_called = []
    monkeypatch.setattr(system_api, "spawn_new_instance", lambda: spawn_called.append(True))
    monkeypatch.setattr(system_api.os, "_exit", lambda code: exit_called.append(code))
    system_api._restart_now()
    assert spawn_called == [True]
    assert exit_called == [0]

    # 失败路径：spawn 抛异常，os._exit 不应被调
    spawn_called.clear()
    exit_called.clear()

    def boom():
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(system_api, "spawn_new_instance", boom)
    system_api._restart_now()
    assert exit_called == []
