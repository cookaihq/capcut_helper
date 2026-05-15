from pydantic import BaseModel


class UpdateInfo(BaseModel):
    current_version: str
    latest_version: str | None = None
    has_update: bool
    release_url: str | None = None
    download_url: str | None = None
    notes: str | None = None
    error: str | None = None
