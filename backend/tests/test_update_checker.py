import pytest

from app.integrations import github_releases
from app.integrations.github_releases import GitHubReleaseError, ReleaseRaw
from app.services import update_checker
from app.services.update_checker import check_for_update


def _release(tag="v0.2.0", download_url="https://x/zip"):
    return ReleaseRaw(
        tag_name=tag,
        release_url="https://x/release",
        notes="notes",
        download_url=download_url,
    )


async def _patch_fetch(monkeypatch, *, returns=None, raises=None):
    async def fake(owner, repo, asset_name):
        if raises is not None:
            raise raises
        return returns
    monkeypatch.setattr(update_checker, "fetch_latest_release", fake)


async def test_has_update_when_remote_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.current_version == "0.1.0"
    assert info.download_url == "https://x/zip"


async def test_no_update_when_versions_equal(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.latest_version == "0.1.0"


async def test_no_update_when_local_is_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.2.0")
    assert info.has_update is False


async def test_strips_v_prefix(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.latest_version == "0.2.0"   # 不含 v


async def test_non_semver_fallback_to_string_inequality(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("0.1.0")
    # 非 SemVer 走字符串相等回退；不等 → has_update=True
    assert info.has_update is True


async def test_non_semver_equal_string_means_no_update(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("release-2026-05")
    assert info.has_update is False


async def test_adapter_error_returns_no_update_with_error_field(monkeypatch):
    await _patch_fetch(monkeypatch, raises=GitHubReleaseError("network: dns"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.error == "network: dns"
    assert info.current_version == "0.1.0"
    assert info.latest_version is None
