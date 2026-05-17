"""POST /api/v1/cors-origins 接口测试：用户授权 origin 后追加到白名单。"""
import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(
        draft_root=str(tmp_path),
        cors_origins=["http://localhost:3182"],
    ))
    app = create_app(port=9527)
    return TestClient(app)


def test_approve_origin_appends_and_returns_added_true(client):
    resp = client.post("/api/v1/cors-origins", json={"origin": "https://example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"origin": "https://example.com", "added": True}
    # 已写入 config
    cfg = client.get("/api/v1/config").json()["data"]
    assert "https://example.com" in cfg["cors_origins"]


def test_approve_origin_is_idempotent(client):
    client.post("/api/v1/cors-origins", json={"origin": "https://example.com"})
    resp = client.post("/api/v1/cors-origins", json={"origin": "https://example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == {"origin": "https://example.com", "added": False}
    cfg = client.get("/api/v1/config").json()["data"]
    # 不重复追加
    assert cfg["cors_origins"].count("https://example.com") == 1


def test_approve_origin_takes_effect_immediately_via_hot_reload(client):
    """CORS 热生效与本接口的契约：POST /cors-origins 后下一次跨域请求即时被信任。"""
    # 初始：example.com 被拦
    r = client.get("/api/v1/config", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-origin") is None
    # 授权
    client.post("/api/v1/cors-origins", json={"origin": "https://example.com"})
    # 立即生效
    r = client.get("/api/v1/config", headers={"Origin": "https://example.com"})
    assert r.headers["access-control-allow-origin"] == "https://example.com"


@pytest.mark.parametrize(
    "bad_origin",
    [
        "example.com",                    # 缺 scheme
        "https://example.com/path",       # 带路径
        "ftp://example.com",              # 非 http(s)
        "javascript:alert(1)",            # 攻击向量
        "https://*.example.com",          # 通配符
    ],
)
def test_approve_origin_422_on_invalid_format(client, bad_origin):
    resp = client.post("/api/v1/cors-origins", json={"origin": bad_origin})
    assert resp.status_code == 422
