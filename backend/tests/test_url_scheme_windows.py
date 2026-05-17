"""Windows URL Scheme 单实例转发逻辑的单元测试（不依赖 Win32 API，可在 Mac 跑）。"""
import json
from io import BytesIO
from unittest.mock import patch

import pytest

from app.native import _url_scheme_windows as winurl


# ============ detect_url_arg ============

@pytest.mark.parametrize(
    "argv,expected",
    [
        (["capcut_helper.exe"], None),
        (["capcut_helper.exe", "capcut-helper://trust?origin=https%3A%2F%2Fa.com"],
         "capcut-helper://trust?origin=https%3A%2F%2Fa.com"),
        (["capcut_helper.exe", "--debug", "capcut-helper://trust?origin=x"],
         "capcut-helper://trust?origin=x"),
        (["capcut_helper.exe", "https://example.com"], None),  # 不是本 scheme
        (["capcut_helper.exe", ""], None),
    ],
)
def test_detect_url_arg(argv, expected):
    assert winurl.detect_url_arg(argv) == expected


# ============ try_forward_to_existing ============

class _FakeHTTPResponse:
    """伪装 urllib HTTPResponse 上下文管理器，封装一个 JSON body 与 status。"""

    def __init__(self, body: dict, status: int = 200):
        self._body = json.dumps(body).encode("utf-8")
        self.status = status

    def __enter__(self):
        return BytesIO(self._body)

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class _FakeStatusOnly:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_forward_succeeds_on_first_matching_port():
    """探到第一个端口就是 capcut_helper，转发应该立即成功。"""
    calls = []

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        calls.append(url)
        if url.endswith("/api/v1/health"):
            return _FakeHTTPResponse({"data": {"service": "capcut_helper", "version": "x"}})
        if url.endswith("/api/v1/internal/handle-url"):
            return _FakeStatusOnly(200)
        raise AssertionError(f"unexpected url: {url}")

    with patch.object(winurl.urllib.request, "urlopen", side_effect=fake_urlopen):
        ok = winurl.try_forward_to_existing(
            "capcut-helper://trust?origin=https%3A%2F%2Fexample.com",
            [9527, 9528],
        )

    assert ok is True
    assert calls[0] == "http://127.0.0.1:9527/api/v1/health"
    assert calls[1] == "http://127.0.0.1:9527/api/v1/internal/handle-url"


def test_forward_skips_unrelated_service_on_port():
    """端口被本机别的服务（如 jupyter）占着，health 返回不是 capcut_helper → 跳过到下一个端口。"""
    calls = []

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        calls.append(url)
        if url == "http://127.0.0.1:9527/api/v1/health":
            # 假装是别的服务（service 字段不匹配）
            return _FakeHTTPResponse({"data": {"service": "jupyter"}})
        if url == "http://127.0.0.1:9528/api/v1/health":
            return _FakeHTTPResponse({"data": {"service": "capcut_helper"}})
        if url == "http://127.0.0.1:9528/api/v1/internal/handle-url":
            return _FakeStatusOnly(200)
        raise AssertionError(f"unexpected url: {url}")

    with patch.object(winurl.urllib.request, "urlopen", side_effect=fake_urlopen):
        ok = winurl.try_forward_to_existing("capcut-helper://trust?origin=https%3A%2F%2Fx.com", [9527, 9528])

    assert ok is True
    # 9527 health 探了一次（被识别为不是 capcut_helper，不发 POST）
    # 9528 health + POST
    assert calls == [
        "http://127.0.0.1:9527/api/v1/health",
        "http://127.0.0.1:9528/api/v1/health",
        "http://127.0.0.1:9528/api/v1/internal/handle-url",
    ]


def test_forward_returns_false_when_no_helper_running():
    """端口段全部无响应（典型「helper 没启动」场景）→ 返回 False，调用方走「自己启动」分支。"""
    def fake_urlopen(req, timeout=None):
        raise winurl.urllib.error.URLError("Connection refused")

    with patch.object(winurl.urllib.request, "urlopen", side_effect=fake_urlopen):
        ok = winurl.try_forward_to_existing("capcut-helper://trust?origin=https%3A%2F%2Fx.com", [9527, 9528])

    assert ok is False


def test_forward_returns_false_when_health_ok_but_post_fails():
    """探到 capcut_helper 但 POST 转发失败（例如对方刚退出）→ False，调用方回退。"""
    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/api/v1/health"):
            return _FakeHTTPResponse({"data": {"service": "capcut_helper"}})
        # POST 失败
        raise winurl.urllib.error.URLError("connection reset")

    with patch.object(winurl.urllib.request, "urlopen", side_effect=fake_urlopen):
        ok = winurl.try_forward_to_existing("capcut-helper://trust?origin=https%3A%2F%2Fx.com", [9527, 9527])

    assert ok is False
