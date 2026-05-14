from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir
from pydantic import BaseModel, Field

CONFIG_DIR = Path(user_config_dir("capcut_helper"))
CONFIG_PATH = CONFIG_DIR / "config.json"


class Config(BaseModel):
    draft_root: Optional[str] = None
    port_range: list[int] = Field(default_factory=lambda: [9527, 9536])
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3182", "http://localhost:3183"]
    )


def load_config(path: Optional[Path] = None) -> Config:
    path = path or CONFIG_PATH
    if path.exists():
        return Config.model_validate_json(path.read_text("utf-8"))
    return Config()


def save_config(cfg: Config, path: Optional[Path] = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
