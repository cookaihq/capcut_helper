"""capcut-helper:// URL 解析与 origin 校验的单元测试。"""
import pytest

from app.core.url_handler import (
    TRUST_ACTION,
    URL_SCHEME,
    URLParseError,
    is_valid_origin,
    parse_trust_url,
)


# ============ is_valid_origin ============

@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3182",
        "https://example.com",
        "https://app.canvas4me.com",
        "https://a.b.c.d",
        "http://10.0.0.1:5173",
        "https://my-app-2.example.com:443",
    ],
)
def test_valid_origin_accepts_well_formed(origin):
    assert is_valid_origin(origin) is True


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "example.com",                       # 缺 scheme
        "ftp://example.com",                 # 非 http(s)
        "https://example.com/",              # 带路径（即使只是 /）
        "https://example.com/foo",           # 带路径
        "https://example.com?q=1",           # 带查询
        "https://example.com#frag",          # 带片段
        "https://*.example.com",             # 通配符
        "https://[::1]:8080",                # IPv6（暂不支持）
        "javascript:alert(1)",               # 攻击向量
    ],
)
def test_valid_origin_rejects_ill_formed(origin):
    assert is_valid_origin(origin) is False


# ============ parse_trust_url ============

def test_parse_trust_url_happy_path():
    req = parse_trust_url("capcut-helper://trust?origin=https%3A%2F%2Fexample.com")
    assert req.origin == "https://example.com"


def test_parse_trust_url_with_port():
    req = parse_trust_url("capcut-helper://trust?origin=http%3A%2F%2Flocalhost%3A3182")
    assert req.origin == "http://localhost:3182"


def test_parse_trust_url_constants_match():
    """守护常量与本测试期望一致——动了常量记得改文档和前端。"""
    assert URL_SCHEME == "capcut-helper"
    assert TRUST_ACTION == "trust"


def test_parse_trust_url_rejects_wrong_scheme():
    with pytest.raises(URLParseError, match="scheme"):
        parse_trust_url("https://trust?origin=https%3A%2F%2Fexample.com")


def test_parse_trust_url_rejects_unknown_action():
    with pytest.raises(URLParseError, match="action"):
        parse_trust_url("capcut-helper://unknown?origin=https%3A%2F%2Fexample.com")


def test_parse_trust_url_rejects_missing_origin():
    with pytest.raises(URLParseError, match="origin"):
        parse_trust_url("capcut-helper://trust")


def test_parse_trust_url_rejects_invalid_origin_format():
    """origin 必须是 http(s)://host[:port]，不能塞路径或通配符。"""
    with pytest.raises(URLParseError, match="origin format"):
        parse_trust_url("capcut-helper://trust?origin=https%3A%2F%2Fexample.com%2Fpath")
    with pytest.raises(URLParseError, match="origin format"):
        parse_trust_url("capcut-helper://trust?origin=javascript%3Aalert(1)")


def test_parse_trust_url_takes_first_origin_when_repeated():
    """重复 origin 参数取第一个（标准 parse_qs 行为，避免歧义）。"""
    req = parse_trust_url(
        "capcut-helper://trust?origin=https%3A%2F%2Fa.com&origin=https%3A%2F%2Fb.com"
    )
    assert req.origin == "https://a.com"
