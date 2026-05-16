import configparser
import os
import plistlib
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

# macOS 剪映把用户自定义草稿目录写在这个 plist 的这个字段里（实测剪映 10.5）
_MACOS_JIANYING_PLIST_RELATIVE = (
    "Library/Containers/com.lemon.lvpro/Data/Library/Preferences/com.bytedance.JianyingPro.plist"
)
_MACOS_CUSTOM_DRAFT_PATH_KEY = "GlobalSettings.History.currentCustomDraftPath"


def _read_macos_custom_draft_path() -> Optional[str]:
    """读剪映 plist 中用户设置的草稿目录；任何异常都返回 None 让上层回退到默认目录。"""
    plist_path = Path.home() / _MACOS_JIANYING_PLIST_RELATIVE
    try:
        with plist_path.open("rb") as f:
            data = plistlib.load(f)
    except (FileNotFoundError, PermissionError, plistlib.InvalidFileException, ValueError):
        return None
    value = data.get(_MACOS_CUSTOM_DRAFT_PATH_KEY)
    if not isinstance(value, str) or not value:
        return None
    return value if Path(value).is_dir() else None


def _read_windows_custom_draft_path() -> Optional[str]:
    """读剪映 Win 版 globalSetting 里的 currentCustomDraftPath；任何异常返回 None 让上层回退到默认。

    实测剪映 10.5+：%LOCALAPPDATA%\\JianyingPro\\User Data\\Config\\globalSetting 是 INI 格式，
    [General] 段下 currentCustomDraftPath= 写入用户在剪映设置里改过的草稿目录。值通常是 \\\\ 转义
    的 Windows 路径（也可能是正斜杠），读出来后还原一次再判断目录存在性。
    """
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        return None
    config_path = Path(localappdata) / "JianyingPro" / "User Data" / "Config" / "globalSetting"
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    raw = parser.get("General", "currentCustomDraftPath", fallback=None)
    if not isinstance(raw, str) or not raw:
        return None
    value = raw.replace("\\\\", "\\")
    return value if Path(value).is_dir() else None


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
        normalized = os.path.normpath(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", normalized], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", normalized], check=False)

    def detect_draft_root(self) -> Optional[str]:
        """优先读剪映配置里的自定义草稿目录，读不到则回退到平台默认目录。"""
        if sys.platform == "darwin":
            custom = _read_macos_custom_draft_path()
            if custom is not None:
                return custom
        elif sys.platform == "win32":
            custom = _read_windows_custom_draft_path()
            if custom is not None:
                return custom
        relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
        if relative is None:
            return None
        candidate = Path.home() / relative
        return str(candidate) if candidate.is_dir() else None

    def open_url(self, url: str) -> None:
        """用系统默认浏览器打开 URL（跳出 pywebview 窗口）。"""
        import webbrowser
        webbrowser.open(url)
