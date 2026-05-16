import sys

from packaging.version import InvalidVersion, Version

from app.integrations.github_releases import GitHubReleaseError, fetch_latest_release
from app.schemas.update import UpdateInfo


GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"


def _asset_name_for_tag(tag: str) -> str:
    """根据 release tag 构造期望的资产名。tag 形如 'v0.2.0'。"""
    if sys.platform == "darwin":
        return f"capcut_helper-arm64-{tag}.dmg"
    if sys.platform == "win32":
        return f"capcut_helper-x64-{tag}.exe"
    raise NotImplementedError(f"unsupported platform: {sys.platform}")


def _strip_v_prefix(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _is_newer(latest: str, current: str) -> bool:
    """SemVer 比较；任一不符合 PEP 440 时回退为字符串相等不等判断。"""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


async def check_for_update(current_version: str) -> UpdateInfo:
    try:
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO)
    except GitHubReleaseError as e:
        return UpdateInfo(
            current_version=current_version,
            has_update=False,
            error=str(e),
        )

    expected = _asset_name_for_tag(raw.tag_name)
    download_url = next(
        (a.download_url for a in raw.assets if a.name == expected),
        None,
    )

    latest = _strip_v_prefix(raw.tag_name)
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        has_update=_is_newer(latest, current_version),
        release_url=raw.release_url,
        download_url=download_url,
        notes=raw.notes,
    )
