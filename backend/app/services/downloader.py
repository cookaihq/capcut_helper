import asyncio
import hashlib
import re
from pathlib import Path

import httpx

from app.core.exceptions import MaterialDownloadError
from app.schemas.timeline import Material

_BACKOFF_BASE = 2  # 重试退避基数（秒）；测试中会被 monkeypatch 为 0
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(material: Material) -> str:
    """用 URL 哈希前缀 + 清洗后的文件名，避免不同 URL 的同名文件互相覆盖。"""
    digest = hashlib.sha256(material.url.encode("utf-8")).hexdigest()[:8]
    cleaned = _UNSAFE_CHARS.sub("_", material.filename) or "material"
    return f"{digest}_{cleaned}"


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
            dest.write_bytes(resp.content)
            return material.url, dest
        except Exception as exc:  # noqa: BLE001 — 下载失败统一兜底重试
            last_error = exc
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
