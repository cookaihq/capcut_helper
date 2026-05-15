from dataclasses import dataclass

import httpx


_TIMEOUT = 5.0
_USER_AGENT = "capcut_helper"


@dataclass
class ReleaseRaw:
    tag_name: str
    release_url: str
    notes: str
    download_url: str | None


class GitHubReleaseError(Exception):
    """GitHub Releases API 调用失败或响应异常。统一兜底类型，供 service 层 catch。"""


async def fetch_latest_release(owner: str, repo: str, asset_name: str) -> ReleaseRaw:
    """GET https://api.github.com/repos/{owner}/{repo}/releases/latest

    任何错误（网络异常、超时、HTTP 非 2xx、JSON 解析失败、缺 tag_name）→ 抛 GitHubReleaseError。
    成功但 assets 里找不到 asset_name → download_url=None，其余字段照常返回。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
    except httpx.HTTPError as e:
        raise GitHubReleaseError(f"network: {e}") from e

    if resp.status_code != 200:
        raise GitHubReleaseError(f"http {resp.status_code}")

    try:
        body = resp.json()
    except ValueError as e:
        raise GitHubReleaseError(f"invalid json: {e}") from e

    tag_name = body.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        raise GitHubReleaseError("missing tag_name")

    download_url = None
    for asset in body.get("assets") or []:
        if asset.get("name") == asset_name:
            download_url = asset.get("browser_download_url")
            break

    return ReleaseRaw(
        tag_name=tag_name,
        release_url=body.get("html_url") or "",
        notes=body.get("body") or "",
        download_url=download_url,
    )
