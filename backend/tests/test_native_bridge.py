import os
import plistlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from app.native.bridge import (
    _MACOS_CUSTOM_DRAFT_PATH_KEY,
    _MACOS_JIANYING_PLIST_RELATIVE,
    NativeBridge,
)


def _write_jianying_plist(fake_home: Path, payload: dict) -> Path:
    plist_path = fake_home / _MACOS_JIANYING_PLIST_RELATIVE
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(payload, f)
    return plist_path


def test_detect_draft_root_returns_path_when_dir_exists(tmp_path, monkeypatch):
    # 伪造 macOS 下的剪映默认目录存在；无 plist 文件，应回退到默认目录
    fake_home = tmp_path
    draft_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    draft_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(draft_dir)


def test_detect_draft_root_returns_none_when_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # 空目录，剪映目录不存在
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() is None


def test_detect_draft_root_prefers_custom_path_from_plist(tmp_path, monkeypatch):
    fake_home = tmp_path
    # 默认目录也存在，验证自定义优先级高于默认
    default_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    default_dir.mkdir(parents=True)
    custom_dir = fake_home / "Documents/MyDrafts"
    custom_dir.mkdir(parents=True)
    _write_jianying_plist(fake_home, {_MACOS_CUSTOM_DRAFT_PATH_KEY: str(custom_dir)})
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(custom_dir)


def test_detect_draft_root_falls_back_when_custom_path_missing_on_disk(tmp_path, monkeypatch):
    # plist 里写了一个已不存在的目录 → 回退到默认目录
    fake_home = tmp_path
    default_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    default_dir.mkdir(parents=True)
    _write_jianying_plist(
        fake_home,
        {_MACOS_CUSTOM_DRAFT_PATH_KEY: str(fake_home / "nonexistent/drafts")},
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(default_dir)


def test_detect_draft_root_falls_back_when_plist_lacks_key(tmp_path, monkeypatch):
    # plist 存在但没有目标字段 → 回退到默认目录
    fake_home = tmp_path
    default_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    default_dir.mkdir(parents=True)
    _write_jianying_plist(fake_home, {"SomeOtherKey": "value"})
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(default_dir)


def test_detect_draft_root_falls_back_when_plist_corrupted(tmp_path, monkeypatch):
    # plist 文件损坏（非合法 plist 内容）→ 回退到默认目录
    fake_home = tmp_path
    default_dir = fake_home / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
    default_dir.mkdir(parents=True)
    plist_path = fake_home / _MACOS_JIANYING_PLIST_RELATIVE
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(b"this is not a valid plist")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "darwin")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(default_dir)


def test_detect_draft_root_windows_path(tmp_path, monkeypatch):
    fake_home = tmp_path
    draft_dir = fake_home / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
    draft_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", "win32")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() == str(draft_dir)


def test_detect_draft_root_unsupported_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")

    bridge = NativeBridge()
    assert bridge.detect_draft_root() is None


def test_reveal_in_os_normalizes_path_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    bridge = NativeBridge()
    raw = "/Users/x/Movies//JianyingPro/../JianyingPro/draft"
    expected = os.path.normpath(raw)  # 同一份 normpath 算期望值，平台无关
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os(raw)
    mock_run.assert_called_once_with(["open", "-R", expected], check=False)


def test_reveal_in_os_normalizes_path_on_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    bridge = NativeBridge()
    raw = "C:/Users/x/AppData/Local/JianyingPro/draft"
    expected = os.path.normpath(raw)
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os(raw)
    mock_run.assert_called_once_with(["explorer", "/select,", expected], check=False)


def test_reveal_in_os_unsupported_platform_does_nothing(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    bridge = NativeBridge()
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os("/foo/bar")
    mock_run.assert_not_called()


def test_open_url_invokes_webbrowser(monkeypatch):
    from app.native.bridge import NativeBridge

    called = []
    monkeypatch.setattr("webbrowser.open", lambda url: called.append(url))

    bridge = NativeBridge()
    bridge.open_url("https://example.com/foo")
    assert called == ["https://example.com/foo"]
