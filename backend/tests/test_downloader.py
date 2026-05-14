import httpx
import pytest
import respx

from app.core.exceptions import MaterialDownloadError
from app.schemas.timeline import Material
from app.services import downloader


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # 把重试退避时间设为 0，避免测试变慢
    monkeypatch.setattr(downloader, "_BACKOFF_BASE", 0)


def _material(url, filename="clip.mp4"):
    return Material(url=url, type="video", filename=filename)


@respx.mock
async def test_downloads_files_into_dest_dir(tmp_path):
    respx.get("https://x/a.mp4").mock(return_value=httpx.Response(200, content=b"AAAA"))
    respx.get("https://x/b.mp4").mock(return_value=httpx.Response(200, content=b"BBBB"))
    mats = [_material("https://x/a.mp4", "a.mp4"), _material("https://x/b.mp4", "b.mp4")]
    result = await downloader.download_materials(mats, tmp_path)
    assert set(result.keys()) == {"https://x/a.mp4", "https://x/b.mp4"}
    for path in result.values():
        assert path.parent == tmp_path
        assert path.read_bytes() in (b"AAAA", b"BBBB")


@respx.mock
async def test_skips_redownload_when_file_exists(tmp_path):
    route = respx.get("https://x/a.mp4").mock(return_value=httpx.Response(200, content=b"AAAA"))
    mats = [_material("https://x/a.mp4", "a.mp4")]
    await downloader.download_materials(mats, tmp_path)
    await downloader.download_materials(mats, tmp_path)  # 第二次：文件已存在
    assert route.call_count == 1


@respx.mock
async def test_retries_then_raises_on_persistent_failure(tmp_path):
    respx.get("https://x/bad.mp4").mock(return_value=httpx.Response(500))
    mats = [_material("https://x/bad.mp4", "bad.mp4")]
    with pytest.raises(MaterialDownloadError) as exc:
        await downloader.download_materials(mats, tmp_path, retries=2)
    assert "bad.mp4" in str(exc.value)
