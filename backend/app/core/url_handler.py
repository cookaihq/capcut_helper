"""capcut-helper:// URL Scheme 的解析与校验。

URL 格式：
    capcut-helper://<action>?<query>

目前仅支持一个 action：
    capcut-helper://trust?origin=<urlencoded_origin>

origin 必须形如 http(s)://host[:port]（不含路径、查询、片段）。这是为了
防止外部链接通过 path/query 注入非法白名单条目；浏览器发的 Origin header
本身也只含 scheme + host + port，跟这个约束一致。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

URL_SCHEME = "capcut-helper"
TRUST_ACTION = "trust"

# scheme + host(可含字母数字、点、中划线) + 可选 :port
# 不接受路径、查询串、片段、通配符、IPv6（[::1] 形式）
_ORIGIN_RE = re.compile(r"^https?://[a-zA-Z0-9.\-]+(:\d{1,5})?$")


class URLParseError(ValueError):
    """capcut-helper:// URL 不符合契约。"""


@dataclass
class TrustRequest:
    """trust action 解析结果。"""

    origin: str


def is_valid_origin(origin: str) -> bool:
    """校验 origin 是否符合 http(s)://host[:port] 形式（Pydantic 校验、API 校验通用）。"""
    return isinstance(origin, str) and bool(_ORIGIN_RE.match(origin))


def parse_trust_url(url: str) -> TrustRequest:
    """解析 capcut-helper://trust?origin=... URL。格式错误抛 URLParseError。"""
    try:
        parsed = urlparse(url)
    except Exception as e:  # noqa: BLE001 — 包装为 URLParseError 统一上层处理
        raise URLParseError(f"invalid URL: {e}") from e

    if parsed.scheme != URL_SCHEME:
        raise URLParseError(f"unexpected scheme {parsed.scheme!r}, want {URL_SCHEME!r}")

    # urlparse 对 capcut-helper://trust?origin=... 把 "trust" 放在 netloc，不在 path
    action = parsed.netloc or parsed.path.lstrip("/")
    if action != TRUST_ACTION:
        raise URLParseError(f"unsupported action {action!r}, want {TRUST_ACTION!r}")

    qs = parse_qs(parsed.query, keep_blank_values=False)
    origins = qs.get("origin") or []
    if not origins:
        raise URLParseError("missing origin query param")

    origin = origins[0]
    if not is_valid_origin(origin):
        raise URLParseError(f"invalid origin format: {origin!r}")

    return TrustRequest(origin=origin)
