"""Bangumi（api.bgm.tv）API 封装。

``BangumiClient`` 仅定义 ``base_url`` 与 ``default_headers``，超时 / 并发限流 /
重试 / 异常包装由 ``BaseAPIClient`` 提供。具体业务端点方法待 services 层接入时补全。
"""

import httpx

from src.utils.base_api_client import BaseAPIClient
from src.utils.client_config import ClientConfig


class BangumiClient(BaseAPIClient):
    """Bangumi HTTP client。

    Bangumi 要求请求携带 ``User-Agent``，否则会被拒绝。
    """

    _BASE_URL: str = "https://api.bgm.tv"
    _USER_AGENT: str = "WatchThisAnime/0.1 (https://github.com/Seedking/WatchThisAnime)"

    def __init__(
        self,
        config: ClientConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化 Bangumi client。

        Args:
            config: 公共配置，缺省时使用 ``ClientConfig()`` 默认值。
            transport: 可选的自定义异步传输层，供测试注入 ``httpx.MockTransport``。
        """
        super().__init__(base_url=self._BASE_URL, config=config, transport=transport)

    @property
    def default_headers(self) -> dict[str, str]:
        """Bangumi 默认请求头：满足其 ``User-Agent`` 要求。"""
        return {"User-Agent": self._USER_AGENT}
