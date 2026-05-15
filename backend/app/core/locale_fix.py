"""macOS .app 启动 locale 兜底。

.app 从 Finder/Dock 启动时不继承 shell 环境变量，LC_CTYPE 默认是 POSIX。
libmediainfo 把 wchar_t 路径转 narrow char (wcstombs) 时，非 ASCII 字符会失败，
导致中文 draft_name 下 MediaInfo_Open 返回 0。

此模块必须在 import pymediainfo（或间接依赖它的 pyJianYingDraft）之前被 import。
"""
import locale
import os
import sys

if sys.platform == "darwin":
    os.environ.setdefault("LC_CTYPE", "en_US.UTF-8")
    os.environ.setdefault("LANG", "en_US.UTF-8")
    try:
        locale.setlocale(locale.LC_CTYPE, "en_US.UTF-8")
    except locale.Error:
        pass
