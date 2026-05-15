import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from app.native.bridge import NativeBridge


def test_detect_draft_root_returns_path_when_dir_exists(tmp_path, monkeypatch):
    # 伪造 macOS 下的剪映默认目录存在
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
