import httpx
import pytest
import respx

from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseRaw,
    fetch_latest_release,
)


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "## 更新内容\n- 新增了横幅",
    "assets": [
        {
            "name": "capcut_helper.zip",
            "browser_download_url": "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip",
        }
    ],
}


@respx.mock
async def test_fetch_latest_release_happy_path():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper", "capcut_helper.zip")
    assert isinstance(raw, ReleaseRaw)
    assert raw.tag_name == "v0.2.0"
    assert raw.release_url == "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0"
    assert raw.notes == "## 更新内容\n- 新增了横幅"
    assert raw.download_url == "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip"
