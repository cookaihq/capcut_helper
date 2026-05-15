"""集中式 logging 初始化。

- 文件路径：platformdirs.user_log_dir("capcut_helper")，按日切分，保留 7 天
- 控制台 handler 方便 dev / pytest -s 时看输出
- 整个进程只初始化一次（pytest 多 fixture 反复 import 时不重复加 handler）
"""
import logging
import logging.handlers
import os
from pathlib import Path

from platformdirs import user_log_dir

LOG_DIR = Path(user_log_dir("capcut_helper"))
LOG_FILE = LOG_DIR / "capcut_helper.log"

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    """初始化 root logger。可重复调用（幂等）。"""
    global _initialized
    if _initialized:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)

    # 文件 handler：按日切分（午夜滚动），保留 7 个文件
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE, when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 控制台 handler：dev / pytest -s 时可见
    if os.isatty(2):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    _initialized = True
