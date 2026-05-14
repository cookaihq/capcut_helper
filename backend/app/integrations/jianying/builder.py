from pathlib import Path

import pyJianYingDraft as draft
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
    for index, track in enumerate(spec.tracks):
        track_name = f"{track.type}_{index}"
        script.add_track(_TRACK_TYPE[track.type], track_name=track_name)
        for seg in track.segments:
            target = trange(seg.timeline.start, seg.timeline.duration)
            source = (
                trange(seg.source.start, seg.source.duration) if seg.source else None
            )
            if track.type == "video":
                material = VideoMaterial(str(material_paths[seg.material.url]))
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
