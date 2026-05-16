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


@pytest.fixture
def mp4_bytes(fixture_video_1) -> bytes:
    """真实 mp4 文件字节，magic bytes 校验能通过。"""
    return fixture_video_1.read_bytes()


def _material(url, type_="video", filename="clip.mp4"):
    return Material(url=url, type=type_, filename=filename)


@respx.mock
async def test_downloads_files_into_dest_dir(tmp_path, mp4_bytes):
    respx.get("https://x/a.mp4").mock(
        return_value=httpx.Response(200, content=mp4_bytes, headers={"content-type": "video/mp4"})
    )
    respx.get("https://x/b.mp4").mock(
        return_value=httpx.Response(200, content=mp4_bytes, headers={"content-type": "video/mp4"})
    )
    mats = [_material("https://x/a.mp4", filename="a.mp4"), _material("https://x/b.mp4", filename="b.mp4")]
    result = await downloader.download_materials(mats, tmp_path)
    assert set(result.keys()) == {"https://x/a.mp4", "https://x/b.mp4"}
    for path in result.values():
        assert path.parent == tmp_path
        assert path.read_bytes() == mp4_bytes


@respx.mock
async def test_skips_redownload_when_file_exists(tmp_path, mp4_bytes):
    route = respx.get("https://x/a.mp4").mock(
        return_value=httpx.Response(200, content=mp4_bytes, headers={"content-type": "video/mp4"})
    )
    mats = [_material("https://x/a.mp4", filename="a.mp4")]
    await downloader.download_materials(mats, tmp_path)
    await downloader.download_materials(mats, tmp_path)  # 第二次：文件已存在
    assert route.call_count == 1


@respx.mock
async def test_retries_then_raises_on_persistent_failure(tmp_path):
    respx.get("https://x/bad.mp4").mock(return_value=httpx.Response(500))
    mats = [_material("https://x/bad.mp4", filename="bad.mp4")]
    with pytest.raises(MaterialDownloadError) as exc:
        await downloader.download_materials(mats, tmp_path, retries=2)
    assert "bad.mp4" in str(exc.value)


@respx.mock
async def test_rejects_html_error_page_with_200(tmp_path):
    """上游返回 200 OK 但 body 是 HTML 错误页 → 应被拒绝并重试，最终抛 MaterialDownloadError。
    这是修复 'libmediainfo 打不开 mp4' 那类 bug 的核心防线。"""
    html = b"<html><body>403 Forbidden</body></html>" + b"x" * 200  # 凑过 _MIN_BYTES
    respx.get("https://x/fake.mp4").mock(
        return_value=httpx.Response(200, content=html, headers={"content-type": "text/html"})
    )
    mats = [_material("https://x/fake.mp4", filename="fake.mp4")]
    with pytest.raises(MaterialDownloadError) as exc:
        await downloader.download_materials(mats, tmp_path, retries=2)
    # 错误链上能看到具体原因（Content-Type）
    assert "Content-Type" in str(exc.value) or "text/html" in str(exc.value)
    # 不能落盘
    assert not list(tmp_path.iterdir())


@respx.mock
async def test_rejects_video_with_invalid_magic_bytes(tmp_path):
    """video 类型但内容不是 mp4/webm magic（比如上游返回 OSS XML 错误体经 octet-stream 透传）。"""
    fake = b"\x00" * 1024  # 1KB 全 0，绝不是合法 mp4
    respx.get("https://x/zero.mp4").mock(
        return_value=httpx.Response(200, content=fake, headers={"content-type": "application/octet-stream"})
    )
    mats = [_material("https://x/zero.mp4", filename="zero.mp4")]
    with pytest.raises(MaterialDownloadError) as exc:
        await downloader.download_materials(mats, tmp_path, retries=2)
    assert "magic" in str(exc.value).lower() or "video" in str(exc.value)


@respx.mock
async def test_rejects_too_small_response(tmp_path):
    """响应体小于 100 字节 → 不可能是合法媒体。"""
    respx.get("https://x/tiny.mp4").mock(
        return_value=httpx.Response(200, content=b"x" * 50, headers={"content-type": "video/mp4"})
    )
    mats = [_material("https://x/tiny.mp4", filename="tiny.mp4")]
    with pytest.raises(MaterialDownloadError):
        await downloader.download_materials(mats, tmp_path, retries=2)


@respx.mock
async def test_writes_bytes_verbatim_without_newline_translation(tmp_path):
    """落盘必须是二进制透传：含 0x0A 的字节序列不能被 Windows 文本模式改写成 0x0D 0x0A。
    回归用：os.open 漏 O_BINARY 时 mp4 在 Windows 上会被 LF→CRLF 膨胀并损坏。"""
    # 合法 mp4 magic（ftyp at offset 4）+ 大量 0x0A 字节 + padding，确保过 magic / 大小校验
    body = b"\x00\x00\x00\x18ftypmp42" + (b"\n" * 1000) + (b"x" * 200)
    respx.get("https://x/lf.mp4").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "video/mp4"})
    )
    mats = [_material("https://x/lf.mp4", filename="lf.mp4")]
    result = await downloader.download_materials(mats, tmp_path)
    path = next(iter(result.values()))
    assert path.read_bytes() == body


@respx.mock
async def test_image_magic_bytes_validated(tmp_path):
    """image 类型校验 jpeg/png/gif/webp。"""
    # 真 PNG header + padding
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    respx.get("https://x/ok.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )
    mats = [_material("https://x/ok.png", type_="image", filename="ok.png")]
    result = await downloader.download_materials(mats, tmp_path)
    assert len(result) == 1

    # 假装是 png 但 header 错
    bad = b"NOPE" + b"\x00" * 200
    respx.get("https://x/bad.png").mock(
        return_value=httpx.Response(200, content=bad, headers={"content-type": "image/png"})
    )
    mats = [_material("https://x/bad.png", type_="image", filename="bad.png")]
    with pytest.raises(MaterialDownloadError):
        await downloader.download_materials(mats, tmp_path, retries=2)
