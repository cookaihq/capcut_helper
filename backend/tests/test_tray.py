from unittest.mock import MagicMock

from app.native.tray import build_tray_callbacks


def test_on_open_shows_window_and_makes_panel_visible():
    """on_open 顺序：set_panel_visible(True) → window.show() → window.restore()。
    顺序对 mac 的 Dock 显示动画有意义。"""
    window = MagicMock()
    platform = MagicMock()

    manager = MagicMock()
    manager.attach_mock(platform.set_panel_visible, "set_panel_visible")
    manager.attach_mock(window.show, "show")
    manager.attach_mock(window.restore, "restore")

    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())
    callbacks.on_open()

    actual_order = [c[0] for c in manager.mock_calls]
    assert actual_order == ["set_panel_visible", "show", "restore"]
    platform.set_panel_visible.assert_called_once_with(True)


def test_on_quit_teardown_before_destroy():
    """on_quit 完整顺序：set_panel_visible(True) → teardown → destroy。
    teardown 必须在 destroy 之前，否则 win 会留 zombie 托盘图标。"""
    window = MagicMock()
    platform = MagicMock()

    manager = MagicMock()
    manager.attach_mock(platform.set_panel_visible, "set_panel_visible")
    manager.attach_mock(platform.teardown, "teardown")
    manager.attach_mock(window.destroy, "destroy")

    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())
    callbacks.on_quit()

    actual_order = [c[0] for c in manager.mock_calls]
    assert actual_order == ["set_panel_visible", "teardown", "destroy"]
    platform.set_panel_visible.assert_called_once_with(True)


def test_on_closing_hides_and_cancels():
    """on_closing 必须返回 False（取消关闭）+ hide + set_panel_visible(False)。"""
    window = MagicMock()
    platform = MagicMock()
    callbacks = build_tray_callbacks(window, platform, on_check_update=MagicMock())

    result = callbacks.on_closing()

    assert result is False
    window.hide.assert_called_once()
    platform.set_panel_visible.assert_called_once_with(False)


def test_on_check_update_is_passed_through():
    """on_check_update 透传，不在 build_tray_callbacks 里包装。"""
    window = MagicMock()
    platform = MagicMock()
    custom = MagicMock()
    callbacks = build_tray_callbacks(window, platform, on_check_update=custom)

    callbacks.on_check_update()

    custom.assert_called_once()
