from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Canvas(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(default=30, gt=0)


class Material(BaseModel):
    url: str = Field(min_length=1)
    type: Literal["video", "image", "audio"]
    filename: str = Field(min_length=1)


class TimeRange(BaseModel):
    start: int = Field(ge=0)       # 微秒
    duration: int = Field(gt=0)    # 微秒


class TextContent(BaseModel):
    content: str = Field(min_length=1)
    style: dict = Field(default_factory=dict)


class Segment(BaseModel):
    material: Optional[Material] = None
    timeline: TimeRange
    source: Optional[TimeRange] = None
    text: Optional[TextContent] = None


class Track(BaseModel):
    type: Literal["video", "audio", "text"]
    segments: list[Segment] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_segment_payload(self):
        for seg in self.segments:
            if self.type in ("video", "audio") and seg.material is None:
                raise ValueError(f"{self.type} 轨道的片段必须含 material")
            if self.type == "text" and seg.text is None:
                raise ValueError("text 轨道的片段必须含 text")
        return self


class TimelineSpec(BaseModel):
    draft_name: str = Field(min_length=1)
    allow_replace: bool = False
    canvas: Canvas
    tracks: list[Track] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_draft_name(self):
        if "/" in self.draft_name or "\\" in self.draft_name:
            raise ValueError("draft_name 不能包含路径分隔符")
        return self

    def material_urls(self) -> list[Material]:
        """按 URL 去重，返回所有需要下载的素材。"""
        seen: dict[str, Material] = {}
        for track in self.tracks:
            for seg in track.segments:
                if seg.material and seg.material.url not in seen:
                    seen[seg.material.url] = seg.material
        return list(seen.values())
