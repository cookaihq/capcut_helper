from packaging.version import InvalidVersion, Version

from app.integrations.github_releases import GitHubReleaseError, fetch_latest_release
from app.schemas.update import UpdateInfo


GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"
ASSET_NAME = "capcut_helper.zip"


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
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO, ASSET_NAME)
    except GitHubReleaseError as e:
        return UpdateInfo(
            current_version=current_version,
            has_update=False,
            error=str(e),
        )

    latest = _strip_v_prefix(raw.tag_name)
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        has_update=_is_newer(latest, current_version),
        release_url=raw.release_url,
        download_url=raw.download_url,
        notes=raw.notes,
    )
