import subprocess
import sys
from pathlib import Path
from typing import Optional

import webview

# 各平台剪映默认草稿目录（相对 Path.home()）
_DRAFT_ROOT_RELATIVE = {
    "darwin": "Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
    "win32": "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft",
}


class NativeBridge:
    """pywebview js_api 桥：暴露给前端 window.pywebview.api.* 的系统外壳操作。
    window 在 create_window 之后由 main.py 赋值。"""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> Optional[str]:
        """打开文件夹选择对话框，返回选中目录路径；用户取消返回 None。"""
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def reveal_in_os(self, path: str) -> None:
        """在系统文件管理器里定位该路径。"""
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", path], check=False)

    def detect_draft_root(self) -> Optional[str]:
        """按平台推断剪映默认草稿目录，存在则返回路径字符串，否则 None。"""
        relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
        if relative is None:
            return None
        candidate = Path.home() / relative
        return str(candidate) if candidate.is_dir() else None
