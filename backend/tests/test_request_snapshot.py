import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import request_snapshot


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    """把 SNAPSHOT_DIR 重定向到 tmp_path，避免污染用户真实日志目录。"""
    sd = tmp_path / "requests"
    monkeypatch.setattr(request_snapshot, "SNAPSHOT_DIR", sd)
    return sd


@pytest.fixture
def app(snapshot_dir):
    app = FastAPI()
    request_snapshot.install_request_snapshot(app, prefix="/api")

    @app.post("/api/echo")
    async def echo(payload: dict):
        return {"received": payload}

    @app.get("/api/ping")
    async def ping():
        return {"pong": True}

    @app.get("/non-api")
    async def non_api():
        return {"x": 1}

    return app


def _list_snapshots(snapshot_dir) -> list[dict]:
    files = []
    if snapshot_dir.is_dir():
        for day_dir in snapshot_dir.iterdir():
            for f in day_dir.iterdir():
                files.append(json.loads(f.read_text("utf-8")))
    return files


def test_snapshot_captures_post_body(app, snapshot_dir):
    client = TestClient(app)
    resp = client.post("/api/echo", json={"foo": "bar", "n": 1})
    assert resp.status_code == 200
    snaps = _list_snapshots(snapshot_dir)
    assert len(snaps) == 1
    s = snaps[0]
    assert s["method"] == "POST"
    assert s["path"] == "/api/echo"
    assert s["body_json"] == {"foo": "bar", "n": 1}
    assert s["status_code"] == 200
    assert s["request_id"]


def test_snapshot_skips_non_api_paths(app, snapshot_dir):
    client = TestClient(app)
    client.get("/non-api")
    assert _list_snapshots(snapshot_dir) == []


def test_snapshot_skips_options_preflight(app, snapshot_dir):
    client = TestClient(app)
    client.options("/api/ping", headers={"Origin": "http://x", "Access-Control-Request-Method": "GET"})
    assert _list_snapshots(snapshot_dir) == []


def test_snapshot_redacts_sensitive_headers(app, snapshot_dir):
    client = TestClient(app)
    client.post(
        "/api/echo",
        json={"k": "v"},
        headers={"Authorization": "Bearer secret123", "X-Custom": "ok"},
    )
    snaps = _list_snapshots(snapshot_dir)
    assert snaps[0]["headers"]["authorization"] == "<redacted>"
    assert snaps[0]["headers"]["x-custom"] == "ok"


def test_cleanup_removes_old_day_dirs(tmp_path, monkeypatch):
    sd = tmp_path / "requests"
    sd.mkdir()
    monkeypatch.setattr(request_snapshot, "SNAPSHOT_DIR", sd)
    # 造一个 60 天前的目录和今天的目录
    old = sd / "2020-01-01"
    old.mkdir()
    (old / "x.json").write_text("{}")
    today = sd / "2099-12-31"
    today.mkdir()
    (today / "y.json").write_text("{}")

    request_snapshot.cleanup_old_snapshots(retention_days=30)

    assert not old.exists()
    assert today.exists()
