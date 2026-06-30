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
    """``GET /rest.php/v1/search/page`` 单条搜索结果（精简后）。

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
    """``GET /rest.php/v1/search/page`` 搜索响应。

    Attributes:
        pages: 匹配的页面列表（已去除 ``thumbnail``）。
    """

    pages: list[MoegirlSearchPage]


@dataclass(frozen=True)
class MoegirlPageLatest:
    """REST page object 的 ``latest`` 字段（最近一次修订）。"""

    id: int
    timestamp: str | None


@dataclass(frozen=True)
class MoegirlPageLicense:
    """REST page object 的 ``license`` 字段。"""

    url: str | None
    title: str | None


@dataclass(frozen=True)
class MoegirlPage:
    """``GET /rest.php/v1/page/{key}`` 单页结果（精简后）。

    入参为页面 key/title（REST 按 title 查询）；``url`` 为按响应里的 page id
    生成的稳定 ``curid`` 打开链接，页面改名后仍可用。可空字段以 ``None`` 表示。
    """

    id: int
    key: str
    title: str
    content_model: str | None
    latest: MoegirlPageLatest | None
    license: MoegirlPageLicense | None
    html_url: str | None
    url: str  # 按响应 page id 生成的稳定「打开页面」URL（index.php?curid=）


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

    @staticmethod
    def page_url(page_id: int) -> str:
        """按 MediaWiki page ID 生成「打开页面」的稳定 URL。

        使用 ``index.php?curid={id}``：MediaWiki 重定向到该 page ID 对应页面的当前
        标题，页面改名 / 移动后链接仍有效（区别于按 title 的链接）。

        Args:
            page_id: MediaWiki 页面 ID。

        Returns:
            形如 ``https://zh.moegirl.org.cn/index.php?curid=9228`` 的 URL。
        """
        return f"{MoegirlClient._BASE_URL}/index.php?curid={page_id}"

    async def search(
        self,
        *,
        q: str,
        limit: int | None = None,
    ) -> MoegirlSearchResponse:
        """搜索页面（``GET /rest.php/v1/search/page``）。

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

        response = await self.get("/rest.php/v1/search/page", params=params)
        return MoegirlClient._parse_search_response(response.json())

    async def get_page(self, *, key: str) -> MoegirlPage:
        """按页面 key/title 拉取页面（``GET /rest.php/v1/page/{key}``）。

        通过 MediaWiki REST API 按标题/key 查询单页，返回精简后的 ``MoegirlPage``，
        含最近修订、许可证、html_url，以及按响应里的 page id 生成的稳定 ``curid``
        打开链接（页面改名后仍可用）。

        Args:
            key: 页面 key（URL slug，如 ``Earth``）；REST 按标题查询。

        Returns:
            精简后的 ``MoegirlPage``。

        Raises:
            APIClientHTTPError: 非 2xx（含页面不存在时的 404）。
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
        """
        response = await self.get(f"/rest.php/v1/page/{key}")
        return MoegirlClient._parse_page(response.json())

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

    @staticmethod
    def _parse_latest(raw: dict[str, object]) -> MoegirlPageLatest:
        """解析 REST page object 的 ``latest`` 字段。"""
        return MoegirlPageLatest(
            id=_as_int(raw.get("id")) or 0,
            timestamp=_as_str(raw.get("timestamp")),
        )

    @staticmethod
    def _parse_license(raw: dict[str, object]) -> MoegirlPageLicense:
        """解析 REST page object 的 ``license`` 字段。"""
        return MoegirlPageLicense(
            url=_as_str(raw.get("url")),
            title=_as_str(raw.get("title")),
        )

    @staticmethod
    def _parse_page(raw: dict[str, object]) -> MoegirlPage:
        """解析 REST page object，逐字段容错缺失键 / None。"""
        page_id = _as_int(raw.get("id")) or 0
        latest_raw = raw.get("latest")
        license_raw = raw.get("license")
        return MoegirlPage(
            id=page_id,
            key=raw.get("key") or "",
            title=raw.get("title") or "",
            content_model=_as_str(raw.get("content_model")),
            latest=(
                MoegirlClient._parse_latest(latest_raw)
                if isinstance(latest_raw, dict)
                else None
            ),
            license=(
                MoegirlClient._parse_license(license_raw)
                if isinstance(license_raw, dict)
                else None
            ),
            html_url=_as_str(raw.get("html_url")),
            url=MoegirlClient.page_url(page_id) if page_id else "",
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
