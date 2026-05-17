"""支持热生效的 CORS 中间件。

Starlette 内置的 CORSMiddleware 在构造时把 allow_origins 烤进派生字段
（self.allow_origins / self.allow_all_origins 等），运行期改 config 不会重读。
本模块包一层壳，每次请求前从回调里现场拉最新 origin 列表并刷新派生字段，
让 PUT /api/v1/config 改 cors_origins 后下一次请求立即生效，不用重启进程。

回调抛异常时，origins 退化为空列表（fail-closed：宁可拒绝跨域也不放过）。
"""
from __future__ import annotations

import logging
from typing import Callable, Sequence

from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


class HotReloadCORSMiddleware(CORSMiddleware):
    def __init__(
        self,
        app,
        get_origins: Callable[[], Sequence[str]],
        **kwargs,
    ) -> None:
        # 父类 __init__ 必须有一个初始 allow_origins，传空列表即可——
        # __call__ 每次会覆盖
        super().__init__(app, allow_origins=[], **kwargs)
        self._get_origins = get_origins

    async def __call__(self, scope, receive, send):
        try:
            origins = list(self._get_origins())
        except Exception:  # noqa: BLE001 — fail-closed，不能让 config 异常阻塞所有请求
            logger.exception("HotReloadCORSMiddleware get_origins 失败，本次按空白名单处理")
            origins = []

        # 复用父类对 origins 的派生计算
        self.allow_origins = origins
        self.allow_all_origins = "*" in origins
        return await super().__call__(scope, receive, send)
