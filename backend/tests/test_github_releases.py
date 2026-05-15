import httpx
import pytest
import respx

from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseAsset,
    ReleaseRaw,
    fetch_latest_release,
)


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "## 更新内容\n- 新增了横幅",
    "assets": [
        {
            "name": "capcut_helper-arm64-v0.2.0.dmg",
            "browser_download_url": "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper-arm64-v0.2.0.dmg",
        }
    ],
}


@respx.mock
async def test_fetch_latest_release_happy_path():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper")
    assert isinstance(raw, ReleaseRaw)
    assert raw.tag_name == "v0.2.0"
    assert raw.release_url == "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0"
    assert raw.notes == "## 更新内容\n- 新增了横幅"
    assert raw.assets == [
        ReleaseAsset(
            name="capcut_helper-arm64-v0.2.0.dmg",
            download_url="https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper-arm64-v0.2.0.dmg",
        )
    ]


@respx.mock
async def test_fetch_latest_release_empty_assets():
    response = dict(_VALID_RESPONSE, assets=[])
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=response)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper")
    assert raw.tag_name == "v0.2.0"
    assert raw.assets == []


@respx.mock
async def test_fetch_latest_release_missing_tag_name():
    bad = dict(_VALID_RESPONSE)
    del bad["tag_name"]
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(GitHubReleaseError, match="missing tag_name"):
        await fetch_latest_release("cookaihq", "capcut_helper")


@respx.mock
async def test_fetch_latest_release_404():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(GitHubReleaseError, match="http 404"):
        await fetch_latest_release("cookaihq", "capcut_helper")


@respx.mock
async def test_fetch_latest_release_network_error():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        side_effect=httpx.ConnectError("dns")
    )
    with pytest.raises(GitHubReleaseError, match="network"):
        await fetch_latest_release("cookaihq", "capcut_helper")
