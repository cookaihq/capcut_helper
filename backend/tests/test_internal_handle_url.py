"""POST /api/v1/internal/handle-url 接口测试。

仅供 Windows 第二个 helper 进程把 URL 转交给已运行实例使用，必须满足：
- 只接受 127.0.0.1 / localhost 来源
- URL 格式不对 → 400
- 没装 bridge（如 pytest 环境）→ 200 但 noop
- 装了 bridge → 调 bridge.on_url_received
"""
import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """internal handle-url 校验 client.host ∈ {127.0.0.1, ::1, localhost}，
    所以 TestClient 必须显式声明 client=("127.0.0.1", ...)，否则 starlette
    默认的 ("testclient", 50000) 会被 403。这反映了真实生产场景：Windows
    第二个 helper 进程从 127.0.0.1 转发 URL 给已运行实例。"""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(tmp_path)))
    app = create_app(port=9527)
    return TestClient(app, client=("127.0.0.1", 54321))


@pytest.fixture
def remote_client(tmp_path, monkeypatch):
    """模拟非本机来源（external IP），用于验证 403。"""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    config_mod.save_config(config_mod.Config(draft_root=str(tmp_path)))
    app = create_app(port=9527)
    return TestClient(app, client=("203.0.113.10", 12345))


def test_handle_url_returns_ok_when_bridge_absent(client):
    """pytest 环境没有 bridge：返回 200 但 noop。"""
    resp = client.post(
        "/api/v1/internal/handle-url",
        json={"url": "capcut-helper://trust?origin=https%3A%2F%2Fexample.com"},
    )
    assert resp.status_code == 200
    assert "no bridge" in resp.json()["message"]


def test_handle_url_invokes_bridge_when_present(client):
    """装了 bridge：on_url_received 被调用并收到原始 URL。"""
    received: list[str] = []

    class _FakeBridge:
        def on_url_received(self, url: str) -> None:
            received.append(url)

    client.app.state.bridge = _FakeBridge()
    url = "capcut-helper://trust?origin=https%3A%2F%2Fexample.com"
    resp = client.post("/api/v1/internal/handle-url", json={"url": url})
    assert resp.status_code == 200
    assert received == [url]


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://trust?origin=https%3A%2F%2Fexample.com",       # 错 scheme
        "capcut-helper://unknown?origin=https%3A%2F%2Fexample.com",  # 错 action
        "capcut-helper://trust",                                # 缺 origin
        "capcut-helper://trust?origin=javascript%3Aalert(1)",   # 非法 origin
    ],
)
def test_handle_url_400_on_invalid_url(client, bad_url):
    resp = client.post("/api/v1/internal/handle-url", json={"url": bad_url})
    assert resp.status_code == 400


def test_handle_url_403_for_non_local_client(remote_client):
    """非 127.0.0.1 来源的请求必须被 403 拒绝，防止外部网页通过本接口注入 URL。"""
    resp = remote_client.post(
        "/api/v1/internal/handle-url",
        json={"url": "capcut-helper://trust?origin=https%3A%2F%2Fevil.example"},
    )
    assert resp.status_code == 403
