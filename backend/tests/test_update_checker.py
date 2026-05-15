from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseAsset,
    ReleaseRaw,
)
from app.services import update_checker
from app.services.update_checker import _asset_name_for_tag, check_for_update


def _release(tag="v0.2.0", asset_name=None):
    """构造 ReleaseRaw。asset_name=None 时默认匹配 _asset_name_for_tag(tag)；
    传具体名字可以模拟「资产名不匹配」用例。"""
    name = asset_name if asset_name is not None else _asset_name_for_tag(tag)
    return ReleaseRaw(
        tag_name=tag,
        release_url="https://x/release",
        notes="notes",
        assets=[ReleaseAsset(name=name, download_url="https://x/asset")],
    )


async def _patch_fetch(monkeypatch, *, returns=None, raises=None):
    async def fake(owner, repo):
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
    assert info.download_url == "https://x/asset"


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


async def test_no_matching_asset_returns_none_download_url(monkeypatch):
    """release 上传了错名的资产（如 .zip 而非 .dmg）→ has_update 仍 True，但 download_url=None"""
    await _patch_fetch(
        monkeypatch,
        returns=_release(tag="v0.2.0", asset_name="capcut_helper-arm64-v0.2.0.zip"),
    )
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.download_url is None


async def test_empty_assets_returns_none_download_url(monkeypatch):
    """release 完全没传资产 → has_update 仍 True，download_url=None"""
    raw = ReleaseRaw(
        tag_name="v0.2.0",
        release_url="https://x/release",
        notes="notes",
        assets=[],
    )
    await _patch_fetch(monkeypatch, returns=raw)
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.download_url is None
