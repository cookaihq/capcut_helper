import logging
import os
import sys
import unicodedata
from pathlib import Path

from pyJianYingDraft import (
    AudioMaterial,
    AudioSegment,
    DraftFolder,
    TextSegment,
    TrackType,
    VideoMaterial,
    VideoSegment,
    trange,
)

from app.core.exceptions import DraftNameConflict
from app.schemas.timeline import TimelineSpec

logger = logging.getLogger(__name__)


def _diagnose_environment_once() -> None:
    """临时诊断：第一次进 populate_draft 时把运行时环境写日志。
    用于定位 .app 打包后 libmediainfo 打不开 mp4 的根因。
    根因找到后此函数应删除。"""
    if getattr(_diagnose_environment_once, "_done", False):
        return
    _diagnose_environment_once._done = True
    import locale
    try:
        import pymediainfo
        mi_path = pymediainfo.MediaInfo._get_library_paths(False)[0]
    except Exception as e:
        mi_path = f"<error: {e!r}>"
    logger.info(
        "[diagnose] frozen=%s MEIPASS=%s cwd=%s locale=%s "
        "env_LANG=%r env_LC_CTYPE=%r env_LC_ALL=%r "
        "default_encoding=%s filesystem_encoding=%s "
        "pymediainfo_dylib=%s",
        getattr(sys, "frozen", False),
        getattr(sys, "_MEIPASS", None),
        os.getcwd(),
        locale.getlocale(),
        os.environ.get("LANG"),
        os.environ.get("LC_CTYPE"),
        os.environ.get("LC_ALL"),
        sys.getdefaultencoding(),
        sys.getfilesystemencoding(),
        mi_path,
    )


def _diagnose_path(path: str) -> None:
    """临时诊断：每个 VideoMaterial 调用前 log 路径细节。"""
    nfc = unicodedata.normalize("NFC", path)
    nfd = unicodedata.normalize("NFD", path)
    logger.info(
        "[diagnose] video path repr=%r len_chars=%d len_utf8_bytes=%d "
        "is_nfc=%s is_nfd=%s exists=%s readable=%s size=%s",
        path, len(path), len(path.encode("utf-8")),
        path == nfc, path == nfd,
        os.path.exists(path),
        os.access(path, os.R_OK),
        os.path.getsize(path) if os.path.exists(path) else None,
    )

_TRACK_TYPE = {
    "video": TrackType.video,
    "audio": TrackType.audio,
    "text": TrackType.text,
}


def create_empty_draft(draft_root: str, spec: TimelineSpec):
    """建一个空草稿文件夹。注意：allow_replace=True 时 pyJianYingDraft 会 rmtree
    整个草稿文件夹再重建，所以必须先调本函数、再往文件夹里下素材。
    返回 (ScriptFile, draft_dir)。"""
    folder = DraftFolder(draft_root)
    try:
        script = folder.create_draft(
            spec.draft_name,
            spec.canvas.width,
            spec.canvas.height,
            fps=spec.canvas.fps,
            allow_replace=spec.allow_replace,
        )
    except FileExistsError:
        raise DraftNameConflict(f"草稿已存在且未允许覆盖: {spec.draft_name}")
    draft_dir = Path(draft_root) / spec.draft_name
    return script, draft_dir


def populate_draft(script, spec: TimelineSpec, material_paths: dict[str, Path]) -> None:
    """按时间线规格往草稿里逐轨逐段填内容。material_paths 是 {url: 本地路径}。"""
    _diagnose_environment_once()
    for index, track in enumerate(spec.tracks):
        track_name = f"{track.type}_{index}"
        script.add_track(_TRACK_TYPE[track.type], track_name=track_name)
        for seg in track.segments:
            target = trange(seg.timeline.start, seg.timeline.duration)
            source = (
                trange(seg.source.start, seg.source.duration) if seg.source else None
            )
            if track.type == "video":
                video_path = str(material_paths[seg.material.url])
                _diagnose_path(video_path)
                material = VideoMaterial(video_path)
                script.add_segment(
                    VideoSegment(material, target, source_timerange=source),
                    track_name=track_name,
                )
            elif track.type == "audio":
                material = AudioMaterial(str(material_paths[seg.material.url]))
                script.add_segment(
                    AudioSegment(material, target, source_timerange=source),
                    track_name=track_name,
                )
            else:  # text
                script.add_segment(
                    TextSegment(seg.text.content, target), track_name=track_name
                )


def save_draft(script) -> None:
    script.save()
