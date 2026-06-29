"""萌娘百科（zh.moegirl.org.cn，MediaWiki API）封装。

``MoegirlClient`` 仅定义 ``base_url`` 与 ``default_headers``，超时 / 并发限流 /
重试 / 异常包装由 ``BaseAPIClient`` 提供。端点方法负责拉取响应并解析为类型化的
精简数据结构（``@dataclass(frozen=True)``），业务编排留给 ``services/`` 层。
"""

from dataclasses import dataclass

import httpx

from src.utils.base_api_client import BaseAPIClient
from src.utils.client_config import ClientConfig


@dataclass(frozen=True)
class MoegirlSearchPage:
    """``GET /w/rest.php/v1/search/page`` 单条搜索结果（精简后）。

    已去除 ``thumbnail``（缩略图）；其余字段按 MediaWiki REST API 原样保留，
    可空字段以 ``None`` 表示。
    """

    id: int
    key: str
    title: str
    excerpt: str | None
    matched_title: str | None
    description: str | None


@dataclass(frozen=True)
class MoegirlSearchResponse:
    """``GET /w/rest.php/v1/search/page`` 搜索响应。

    Attributes:
        pages: 匹配的页面列表（已去除 ``thumbnail``）。
    """

    pages: list[MoegirlSearchPage]


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

    async def search(
        self,
        *,
        q: str,
        limit: int | None = None,
    ) -> MoegirlSearchResponse:
        """搜索页面（``GET /w/rest.php/v1/search/page``）。

        ``q`` 必填；``limit`` 可选，``None`` 时不进入查询串。``int`` 序列化为字符串。

        Args:
            q: 搜索关键词。
            limit: 返回条数上限。

        Returns:
            精简后的搜索响应：``pages`` 为页面列表（已去除 ``thumbnail``）。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        params: dict[str, str] = {"q": q}
        if limit is not None:
            params["limit"] = str(limit)

        response = await self.get("/w/rest.php/v1/search/page", params=params)
        return MoegirlClient._parse_search_response(response.json())

    @staticmethod
    def _parse_search_page(raw: dict[str, object]) -> MoegirlSearchPage:
        """解析单条搜索结果，逐字段容错缺失键 / None；``thumbnail`` 不解析。"""
        return MoegirlSearchPage(
            id=_as_int(raw.get("id")) or 0,
            key=raw.get("key") or "",
            title=raw.get("title") or "",
            excerpt=_as_str(raw.get("excerpt")),
            matched_title=_as_str(raw.get("matched_title")),
            description=_as_str(raw.get("description")),
        )

    @staticmethod
    def _parse_search_response(raw: dict[str, object]) -> MoegirlSearchResponse:
        """解析搜索响应；``pages`` 缺失时置 ``[]``。"""
        pages_raw: list[dict[str, object]] = raw.get("pages") or []  # type: ignore[assignment]
        return MoegirlSearchResponse(
            pages=[MoegirlClient._parse_search_page(item) for item in pages_raw],
        )


def _as_int(value: object) -> int | None:
    """将值转为 ``int``，``None`` / 非数值返回 ``None``。"""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    """将值转为 ``str``，``None`` 返回 ``None``。"""
    if value is None:
        return None
    return str(value)
