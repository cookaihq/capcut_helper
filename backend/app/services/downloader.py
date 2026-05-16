import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path

import httpx

from app.core.exceptions import MaterialDownloadError
from app.schemas.timeline import Material

logger = logging.getLogger(__name__)

_BACKOFF_BASE = 2  # 重试退避基数（秒）；测试中会被 monkeypatch 为 0
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MIN_BYTES = 100  # 小于这个值几乎肯定是错误响应（比如 OSS 的 XML 错误体也常 < 1KB 但内容是 XML）
_REJECTED_CONTENT_TYPES = ("text/", "application/json", "application/xml", "application/problem+")


def _safe_filename(material: Material) -> str:
    """用 URL 哈希前缀 + 清洗后的文件名，避免不同 URL 的同名文件互相覆盖。"""
    digest = hashlib.sha256(material.url.encode("utf-8")).hexdigest()[:8]
    cleaned = _UNSAFE_CHARS.sub("_", material.filename) or "material"
    return f"{digest}_{cleaned}"


def _detect_invalid_content(material: Material, content_type: str, body: bytes) -> str | None:
    """返回 None 表示通过校验，否则返回错误描述。"""
    # 1. Content-Type 黑名单：上游返回错误页面（HTML / JSON / XML 错误体）的最常见模式
    ct_lower = (content_type or "").lower()
    if any(ct_lower.startswith(p) for p in _REJECTED_CONTENT_TYPES):
        return f"上游 Content-Type={content_type!r} 不是二进制媒体"

    # 2. 最小 size：100 字节以下不可能是有效媒体
    if len(body) < _MIN_BYTES:
        return f"响应体过小（{len(body)} 字节），疑似错误响应"

    # 3. magic bytes：仅对 video/image 校验，audio 容器太多元不强制
    if material.type == "video":
        # mp4/mov: byte 4-8 为 'ftyp'；webm/mkv: 0x1A 0x45 0xDF 0xA3
        if not (body[4:8] == b"ftyp" or body[:4] == b"\x1a\x45\xdf\xa3"):
            return f"video 文件 magic bytes 异常（前 8 字节={body[:8].hex()}）"
    elif material.type == "image":
        ok = (
            body[:3] == b"\xff\xd8\xff"            # jpeg
            or body[:8] == b"\x89PNG\r\n\x1a\n"   # png
            or body[:6] in (b"GIF87a", b"GIF89a")  # gif
            or (body[:4] == b"RIFF" and body[8:12] == b"WEBP")  # webp
        )
        if not ok:
            return f"image 文件 magic bytes 异常（前 8 字节={body[:8].hex()}）"
    return None


async def _download_one(
    client: httpx.AsyncClient, material: Material, dest_dir: Path, retries: int
) -> tuple[str, Path]:
    dest = dest_dir / _safe_filename(material)
    if dest.exists():
        return material.url, dest

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.get(material.url, timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            body = resp.content

            invalid_reason = _detect_invalid_content(material, content_type, body)
            if invalid_reason:
                # 把响应头和前 64 字节 hex preview 写到日志，方便排错
                logger.error(
                    "material content invalid: url=%s reason=%s content_type=%s "
                    "size=%d preview=%s headers=%s",
                    material.url, invalid_reason, content_type, len(body),
                    body[:64].hex(), dict(resp.headers),
                )
                # 抛 ValueError 走重试逻辑：上游可能瞬时返回错误页，重试一下也许能拿到正确内容
                raise ValueError(invalid_reason)

            # 必须显式二进制模式："wb"：Windows 上文本模式会把 0x0A 自动转成 0x0D 0x0A，
            # 让 mp4 膨胀且损坏。fsync 强制刷盘：write 后立即被 libmediainfo 通过 C 层 open()
            # 读取，未刷盘可能拿到 metadata 不稳定状态导致解析失败。
            with open(dest, "wb") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            return material.url, dest
        except Exception as exc:  # noqa: BLE001 — 下载失败统一兜底重试
            last_error = exc
            logger.warning(
                "material download attempt %d/%d failed: url=%s error=%r",
                attempt + 1, retries, material.url, exc,
            )
            if attempt < retries - 1:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))

    raise MaterialDownloadError(
        f"素材下载失败: {material.filename} ({material.url}) — {last_error}"
    )


async def download_materials(
    materials: list[Material], dest_dir, retries: int = 3
) -> dict[str, Path]:
    """并发下载素材到 dest_dir，返回 {url: 本地路径}。materials 已按 URL 去重。"""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_download_one(client, m, dest_dir, retries) for m in materials)
        )
    return dict(results)
