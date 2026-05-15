import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core import config as config_mod
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


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "notes",
    "assets": [
        {
            "name": "capcut_helper-arm64-v0.2.0.dmg",
            "browser_download_url": "https://x/asset",
        }
    ],
}


@respx.mock
def test_update_check_returns_envelope(client):
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    resp = client.get("/api/v1/update/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    data = body["data"]
    assert data["has_update"] is True
    assert data["latest_version"] == "0.2.0"
    assert data["download_url"] == "https://x/asset"


@respx.mock
def test_update_check_returns_200_on_network_error(client):
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        side_effect=httpx.ConnectError("dns")
    )
    resp = client.get("/api/v1/update/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["has_update"] is False
    assert data["error"] is not None
