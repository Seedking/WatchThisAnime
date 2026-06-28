"""萌娘百科（zh.moegirl.org.cn，MediaWiki API）封装。

``MoegirlClient`` 仅定义 ``base_url`` 与 ``default_headers``，超时 / 并发限流 /
重试 / 异常包装由 ``BaseAPIClient`` 提供。具体业务端点方法待 services 层接入时补全。
"""

import httpx

from src.utils.base_api_client import BaseAPIClient
from src.utils.client_config import ClientConfig


class MoegirlClient(BaseAPIClient):
    """萌娘百科 HTTP client。"""

    _BASE_URL: str = "https://zh.moegirl.org.cn"
    _USER_AGENT: str = "WatchThisAnime/0.1"

    def __init__(
        self,
        config: ClientConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化萌娘百科 client。

        Args:
            config: 公共配置，缺省时使用 ``ClientConfig()`` 默认值。
            transport: 可选的自定义异步传输层，供测试注入 ``httpx.MockTransport``。
        """
        super().__init__(base_url=self._BASE_URL, config=config, transport=transport)

    @property
    def default_headers(self) -> dict[str, str]:
        """萌娘百科默认请求头。"""
        return {"User-Agent": self._USER_AGENT}
