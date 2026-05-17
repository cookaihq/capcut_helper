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
    # 不带 Origin（curl 风格）：cors_allowed 为 null，your_origin 为 null
    assert data["your_origin"] is None
    assert data["cors_allowed"] is None
    assert data["hint"] is None
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


def test_health_reflects_origin_in_whitelist(client):
    # 默认白名单：localhost:3182 / localhost:3183
    resp = client.get("/api/v1/health", headers={"Origin": "http://localhost:3182"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["your_origin"] == "http://localhost:3182"
    assert data["cors_allowed"] is True
    assert data["hint"] is None
    # health 对白名单内 origin 反射 ACAO
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3182"


def test_health_reflects_origin_not_in_whitelist(client):
    """health 对任意 origin 都放行 ACAO，让调用方 JS 能读到 cors_allowed=false 的提示。"""
    resp = client.get("/api/v1/health", headers={"Origin": "https://example.com"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["your_origin"] == "https://example.com"
    assert data["cors_allowed"] is False
    assert data["hint"] is not None
    assert "https://example.com" in data["hint"]
    # 关键：未在白名单的 origin 也能从 health 拿到 ACAO
    assert resp.headers["access-control-allow-origin"] == "https://example.com"
    assert resp.headers.get("vary") == "Origin"


def test_business_endpoint_does_not_expose_acao_for_off_whitelist_origin(client):
    """与 health 对比：业务接口对未授权 origin 不发 ACAO（浏览器会拦截 JS 读响应）。"""
    resp = client.get("/api/v1/config", headers={"Origin": "https://example.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_hot_reload_after_config_change(client):
    """改完 cors_origins 不重启进程，下一次请求即时生效。"""
    # 初始：example.com 不在白名单
    r = client.get("/api/v1/config", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-origin") is None

    # 通过 PUT /config 加白名单
    cur = client.get("/api/v1/config").json()["data"]
    cur["cors_origins"] = list(cur["cors_origins"]) + ["https://example.com"]
    assert client.put("/api/v1/config", json=cur).status_code == 200

    # 下一次请求立即生效
    r = client.get("/api/v1/config", headers={"Origin": "https://example.com"})
    assert r.headers["access-control-allow-origin"] == "https://example.com"
    # health 的 cors_allowed 也同步反映
    r = client.get("/api/v1/health", headers={"Origin": "https://example.com"})
    assert r.json()["data"]["cors_allowed"] is True
    assert r.json()["data"]["hint"] is None


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
