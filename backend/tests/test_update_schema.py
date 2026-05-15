from app.schemas.update import UpdateInfo


def test_update_info_minimal_fields():
    info = UpdateInfo(current_version="0.1.0", has_update=False)
    assert info.current_version == "0.1.0"
    assert info.has_update is False
    assert info.latest_version is None
    assert info.release_url is None
    assert info.download_url is None
    assert info.notes is None
    assert info.error is None


def test_update_info_full_fields():
    info = UpdateInfo(
        current_version="0.1.0",
        latest_version="0.2.0",
        has_update=True,
        release_url="https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
        download_url="https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper.zip",
        notes="- 新增...",
    )
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.error is None
