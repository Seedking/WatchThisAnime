"""Jikan（api.jikan.moe，MyAnimeList 非官方 API）封装。

``JikanClient`` 仅定义 ``base_url`` 与 ``default_headers``，超时 / 并发限流 /
重试 / 异常包装由 ``BaseAPIClient`` 提供。端点方法负责拉取响应并解析为类型化的
精简数据结构（``@dataclass(frozen=True)``），业务编排留给 ``services/`` 层。
"""

from dataclasses import dataclass

import httpx

from src.utils.base_api_client import BaseAPIClient
from src.utils.client_config import ClientConfig


@dataclass(frozen=True)
class JikanTitle:
    """``titles`` 单个标题。

    Attributes:
        type: 标题类型，例如 ``"Default"`` / ``"Japanese"`` / ``"English"``。
        title: 标题文本。
    """

    type: str
    title: str


@dataclass(frozen=True)
class JikanTrailer:
    """预告片信息，各字段均可能为空。"""

    youtube_id: str | None
    url: str | None
    embed_url: str | None


@dataclass(frozen=True)
class JikanAiredPropDate:
    """``aired.prop.from`` / ``aired.prop.to`` 的日期分量，各字段均可能为空。"""

    day: int | None
    month: int | None
    year: int | None


@dataclass(frozen=True)
class JikanAiredProp:
    """``aired.prop`` 日期属性。

    Attributes:
        from_: 起始日期分量（``"from"`` 是 Python 关键字，字段名加下划线）。
        to: 结束日期分量。
        string: 人类可读的日期区间字符串。
    """

    from_: JikanAiredPropDate | None
    to: JikanAiredPropDate | None
    string: str | None


@dataclass(frozen=True)
class JikanAired:
    """``aired`` 放送区间。

    Attributes:
        from_: 起始时间 ISO 字符串（``"from"`` 是 Python 关键字，字段名加下划线）。
        to: 结束时间 ISO 字符串。
        prop: 结构化日期属性。
    """

    from_: str | None
    to: str | None
    prop: JikanAiredProp | None


@dataclass(frozen=True)
class JikanBroadcast:
    """``broadcast`` 放送时间信息，各字段均可能为空。"""

    day: str | None
    time: str | None
    timezone: str | None
    string: str | None


@dataclass(frozen=True)
class JikanEntity:
    """复用于 ``genres`` / ``themes`` / ``demographics`` / ``studios`` /
    ``producers`` / ``licensors`` / ``explicit_genres`` 的 ``{mal_id, type, name, url}`` 实体。

    Attributes:
        mal_id: MAL 主键。
        type: 实体类型，例如 ``"anime"`` / ``"genre"``。
        name: 名称。
        url: MAL 页面地址。
    """

    mal_id: int
    type: str | None
    name: str
    url: str | None


@dataclass(frozen=True)
class JikanAnime:
    """``GET /anime`` 单条番剧（精简后）。

    已去除 ``images``（jpg / webp 封面图）；其余字段按 OpenAPI 原样保留，可空字段以
    ``None`` 表示，缺失的列表字段置 ``[]``。
    """

    mal_id: int
    url: str | None
    trailer: JikanTrailer | None
    approved: bool | None
    titles: list[JikanTitle]
    title: str
    title_english: str | None
    title_japanese: str | None
    title_synonyms: list[str]
    type: str | None
    source: str | None
    episodes: int | None
    status: str | None
    airing: bool | None
    aired: JikanAired | None
    duration: str | None
    rating: str | None
    score: float | None
    scored_by: int | None
    rank: int | None
    popularity: int | None
    members: int | None
    favorites: int | None
    synopsis: str | None
    background: str | None
    season: str | None
    year: int | None
    broadcast: JikanBroadcast | None
    producers: list[JikanEntity]
    licensors: list[JikanEntity]
    studios: list[JikanEntity]
    genres: list[JikanEntity]
    explicit_genres: list[JikanEntity]
    themes: list[JikanEntity]
    demographics: list[JikanEntity]


@dataclass(frozen=True)
class JikanPaginationItems:
    """``pagination.items`` 分页计数，各字段均可能为空。"""

    count: int | None
    total: int | None
    per_page: int | None


@dataclass(frozen=True)
class JikanPagination:
    """``pagination`` 分页信息。

    Attributes:
        last_visible_page: 最后可见页码。
        has_next_page: 是否还有下一页。
        current_page: 当前页码。
        items: 计数信息。
    """

    last_visible_page: int | None
    has_next_page: bool | None
    current_page: int | None
    items: JikanPaginationItems | None


@dataclass(frozen=True)
class JikanSearchResponse:
    """``GET /anime`` 搜索响应。

    Attributes:
        data: 匹配的番剧列表。
        pagination: 分页信息，响应缺失时为 ``None``。
    """

    data: list[JikanAnime]
    pagination: JikanPagination | None


class JikanClient(BaseAPIClient):
    """Jikan HTTP client。"""

    _BASE_URL: str = "https://api.jikan.moe/v4"
    _USER_AGENT: str = "WatchThisAnime/0.1"

    def __init__(
        self,
        config: ClientConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化 Jikan client。

        Args:
            config: 公共配置，缺省时使用 ``ClientConfig()`` 默认值。
            transport: 可选的自定义异步传输层，供测试注入 ``httpx.MockTransport``。
        """
        super().__init__(base_url=self._BASE_URL, config=config, transport=transport)

    @property
    def default_headers(self) -> dict[str, str]:
        """Jikan 默认请求头。"""
        return {"User-Agent": self._USER_AGENT}

    async def search_anime(
        self,
        *,
        q: str | None = None,
        type: str | None = None,
        unapproved: bool | None = None,
        page: int | None = None,
        limit: int | None = None,
        score: float | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        status: str | None = None,
        rating: str | None = None,
        sfw: bool | None = None,
        genres: str | None = None,
        genres_exclude: str | None = None,
        order_by: str | None = None,
        sort: str | None = None,
        letter: str | None = None,
        producers: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> JikanSearchResponse:
        """搜索番剧（``GET /anime``）。

        所有查询参数均为可选；``None`` 的参数不会出现在请求查询串中。``bool`` 参数
        序列化为 ``"true"`` / ``"false"``，``int`` / ``float`` 序列化为字符串。

        Args:
            q: 标题关键词。
            type: 类型，枚举 ``"TV"`` / ``"OVA"`` / ``"Movie"`` / ``"Special"``
                / ``"ONA"`` / ``"Music"`` / ``"CM"`` / ``"PV"`` / ``"TV Special"``。
            unapproved: 是否包含未审核条目。
            page: 页码。
            limit: 每页条数。
            score: 精确评分过滤。
            min_score: 最低评分。
            max_score: 最高评分。
            status: 状态，枚举 ``"airing"`` / ``"complete"`` / ``"upcoming"``。
            rating: 受众分级，枚举 ``"g"`` / ``"pg"`` / ``"pg13"`` / ``"r17"``
                / ``"r"`` / ``"rx"``。
            sfw: 是否过滤成人条目。
            genres: 按流派 ID 过滤，逗号分隔，例如 ``"1,2,3"``。
            genres_exclude: 排除流派 ID，逗号分隔。
            order_by: 排序字段，枚举如 ``"mal_id"`` / ``"title"`` / ``"score"``
                / ``"popularity"`` / ``"members"`` 等。
            sort: 排序方向，枚举 ``"desc"`` / ``"asc"``。
            letter: 按首字母过滤。
            producers: 按制作方 ID 过滤，逗号分隔。
            start_date: 起始日期，格式 ``YYYY-MM-DD``（也接受 ``YYYY`` / ``YYYY-MM``）。
            end_date: 结束日期，格式 ``YYYY-MM-DD``（也接受 ``YYYY`` / ``YYYY-MM``）。

        Returns:
            精简后的搜索响应：``data`` 为番剧列表（已去除 ``images``），
            ``pagination`` 为分页信息。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        params: dict[str, str] = {}
        if q is not None:
            params["q"] = q
        if type is not None:
            params["type"] = type
        if unapproved is not None:
            params["unapproved"] = str(unapproved).lower()
        if page is not None:
            params["page"] = str(page)
        if limit is not None:
            params["limit"] = str(limit)
        if score is not None:
            params["score"] = str(score)
        if min_score is not None:
            params["min_score"] = str(min_score)
        if max_score is not None:
            params["max_score"] = str(max_score)
        if status is not None:
            params["status"] = status
        if rating is not None:
            params["rating"] = rating
        if sfw is not None:
            params["sfw"] = str(sfw).lower()
        if genres is not None:
            params["genres"] = genres
        if genres_exclude is not None:
            params["genres_exclude"] = genres_exclude
        if order_by is not None:
            params["order_by"] = order_by
        if sort is not None:
            params["sort"] = sort
        if letter is not None:
            params["letter"] = letter
        if producers is not None:
            params["producers"] = producers
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = await self.get("/anime", params=params or None)
        return JikanClient._parse_search_response(response.json())

    @staticmethod
    def _parse_title(raw: dict[str, object]) -> JikanTitle:
        """解析单个标题，逐字段容错缺失键 / None。"""
        return JikanTitle(
            type=raw.get("type") or "",
            title=raw.get("title") or "",
        )

    @staticmethod
    def _parse_trailer(raw: dict[str, object] | None) -> JikanTrailer | None:
        """解析预告片信息；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanTrailer(
            youtube_id=_as_str(raw.get("youtube_id")),
            url=_as_str(raw.get("url")),
            embed_url=_as_str(raw.get("embed_url")),
        )

    @staticmethod
    def _parse_aired_prop_date(raw: dict[str, object] | None) -> JikanAiredPropDate | None:
        """解析日期分量；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanAiredPropDate(
            day=_as_int(raw.get("day")),
            month=_as_int(raw.get("month")),
            year=_as_int(raw.get("year")),
        )

    @staticmethod
    def _parse_aired_prop(raw: dict[str, object] | None) -> JikanAiredProp | None:
        """解析 ``aired.prop``；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanAiredProp(
            from_=JikanClient._parse_aired_prop_date(raw.get("from")),  # type: ignore[arg-type]
            to=JikanClient._parse_aired_prop_date(raw.get("to")),  # type: ignore[arg-type]
            string=_as_str(raw.get("string")),
        )

    @staticmethod
    def _parse_aired(raw: dict[str, object] | None) -> JikanAired | None:
        """解析 ``aired``；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanAired(
            from_=_as_str(raw.get("from")),
            to=_as_str(raw.get("to")),
            prop=JikanClient._parse_aired_prop(raw.get("prop")),  # type: ignore[arg-type]
        )

    @staticmethod
    def _parse_broadcast(raw: dict[str, object] | None) -> JikanBroadcast | None:
        """解析 ``broadcast``；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanBroadcast(
            day=_as_str(raw.get("day")),
            time=_as_str(raw.get("time")),
            timezone=_as_str(raw.get("timezone")),
            string=_as_str(raw.get("string")),
        )

    @staticmethod
    def _parse_entity(raw: dict[str, object]) -> JikanEntity:
        """解析单个 ``{mal_id, type, name, url}`` 实体，逐字段容错缺失键 / None。"""
        return JikanEntity(
            mal_id=_as_int(raw.get("mal_id")) or 0,
            type=_as_str(raw.get("type")),
            name=raw.get("name") or "",
            url=_as_str(raw.get("url")),
        )

    @staticmethod
    def _parse_entity_list(raw: list[dict[str, object]] | None) -> list[JikanEntity]:
        """解析实体列表；输入为 falsy 时返回 ``[]``。"""
        if not raw:
            return []
        return [JikanClient._parse_entity(item) for item in raw]

    @staticmethod
    def _parse_anime(raw: dict[str, object]) -> JikanAnime:
        """解析单条番剧，逐字段容错缺失键 / None；``images`` 不解析。"""
        titles_raw: list[dict[str, object]] = raw.get("titles") or []  # type: ignore[assignment]
        synonyms_raw: list[object] = raw.get("title_synonyms") or []  # type: ignore[assignment]
        return JikanAnime(
            mal_id=_as_int(raw.get("mal_id")) or 0,
            url=_as_str(raw.get("url")),
            trailer=JikanClient._parse_trailer(raw.get("trailer")),  # type: ignore[arg-type]
            approved=_as_bool(raw.get("approved")),
            titles=[JikanClient._parse_title(title) for title in titles_raw],
            title=raw.get("title") or "",
            title_english=_as_str(raw.get("title_english")),
            title_japanese=_as_str(raw.get("title_japanese")),
            title_synonyms=[str(s) for s in synonyms_raw if s is not None],
            type=_as_str(raw.get("type")),
            source=_as_str(raw.get("source")),
            episodes=_as_int(raw.get("episodes")),
            status=_as_str(raw.get("status")),
            airing=_as_bool(raw.get("airing")),
            aired=JikanClient._parse_aired(raw.get("aired")),  # type: ignore[arg-type]
            duration=_as_str(raw.get("duration")),
            rating=_as_str(raw.get("rating")),
            score=_as_float(raw.get("score")),
            scored_by=_as_int(raw.get("scored_by")),
            rank=_as_int(raw.get("rank")),
            popularity=_as_int(raw.get("popularity")),
            members=_as_int(raw.get("members")),
            favorites=_as_int(raw.get("favorites")),
            synopsis=_as_str(raw.get("synopsis")),
            background=_as_str(raw.get("background")),
            season=_as_str(raw.get("season")),
            year=_as_int(raw.get("year")),
            broadcast=JikanClient._parse_broadcast(raw.get("broadcast")),  # type: ignore[arg-type]
            producers=JikanClient._parse_entity_list(raw.get("producers")),  # type: ignore[arg-type]
            licensors=JikanClient._parse_entity_list(raw.get("licensors")),  # type: ignore[arg-type]
            studios=JikanClient._parse_entity_list(raw.get("studios")),  # type: ignore[arg-type]
            genres=JikanClient._parse_entity_list(raw.get("genres")),  # type: ignore[arg-type]
            explicit_genres=JikanClient._parse_entity_list(raw.get("explicit_genres")),  # type: ignore[arg-type]
            themes=JikanClient._parse_entity_list(raw.get("themes")),  # type: ignore[arg-type]
            demographics=JikanClient._parse_entity_list(raw.get("demographics")),  # type: ignore[arg-type]
        )

    @staticmethod
    def _parse_pagination_items(raw: dict[str, object] | None) -> JikanPaginationItems | None:
        """解析 ``pagination.items``；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanPaginationItems(
            count=_as_int(raw.get("count")),
            total=_as_int(raw.get("total")),
            per_page=_as_int(raw.get("per_page")),
        )

    @staticmethod
    def _parse_pagination(raw: dict[str, object] | None) -> JikanPagination | None:
        """解析 ``pagination``；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return JikanPagination(
            last_visible_page=_as_int(raw.get("last_visible_page")),
            has_next_page=_as_bool(raw.get("has_next_page")),
            current_page=_as_int(raw.get("current_page")),
            items=JikanClient._parse_pagination_items(raw.get("items")),  # type: ignore[arg-type]
        )

    @staticmethod
    def _parse_search_response(raw: dict[str, object]) -> JikanSearchResponse:
        """解析搜索响应；``data`` 缺失时置 ``[]``。"""
        data_raw: list[dict[str, object]] = raw.get("data") or []  # type: ignore[assignment]
        return JikanSearchResponse(
            data=[JikanClient._parse_anime(item) for item in data_raw],
            pagination=JikanClient._parse_pagination(raw.get("pagination")),  # type: ignore[arg-type]
        )


def _as_int(value: object) -> int | None:
    """将值转为 ``int``，``None`` / 非数值返回 ``None``。"""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    """将值转为 ``float``，``None`` / 非数值返回 ``None``。"""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    """将值转为 ``str``，``None`` 返回 ``None``。"""
    if value is None:
        return None
    return str(value)


def _as_bool(value: object) -> bool | None:
    """将值转为 ``bool``，``None`` 返回 ``None``。"""
    if value is None:
        return None
    return bool(value)
