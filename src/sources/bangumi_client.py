"""Bangumi（api.bgm.tv）API 封装。

``BangumiClient`` 定义 ``base_url`` 与 ``default_headers``，超时 / 并发限流 /
重试 / 异常包装由 ``BaseAPIClient`` 提供。端点方法负责拉取响应并解析为类型化的
精简数据结构（``@dataclass(frozen=True)``），业务编排留给 ``services/`` 层。
"""

from dataclasses import dataclass

import httpx

from src.utils.base_api_client import BaseAPIClient
from src.utils.client_config import ClientConfig


@dataclass(frozen=True)
class BangumiRating:
    """Bangumi 评分聚合。

    Attributes:
        score: 加权平均分，可能为空。
        total: 总评分人数，可能为空。
        count: 各分数档人数，形如 ``{"1": 5, "2": 3, ...}``，原样保留。
    """

    score: float | None
    total: int | None
    count: dict[str, int] | None


@dataclass(frozen=True)
class BangumiCollection:
    """Bangumi 收藏统计，各档人数均可能为空。"""

    wish: int | None
    collect: int | None
    doing: int | None
    on_hold: int | None
    dropped: int | None


@dataclass(frozen=True)
class BangumiTag:
    """``tags`` 单个标签及其引用计数。"""

    name: str
    count: int | None


@dataclass(frozen=True)
class BangumiImages:
    """条目封面图各尺寸 URL，均可能为空。"""

    large: str | None
    common: str | None
    medium: str | None
    small: str | None
    grid: str | None


@dataclass(frozen=True)
class BangumiSubject:
    """``/v0/subjects/{subject_id}`` 条目详情（精简后）。

    已去除 ``infobox`` / ``series`` / ``nsfw`` / ``locked``；可空字段以 ``None`` 表示。
    ``rank`` 取自响应 ``rating.rank``，提到顶层与 ``BangumiCalendarItem.rank`` 对齐。
    """

    id: int
    type: int | None
    name: str
    name_cn: str | None
    summary: str | None
    date: str | None
    platform: str | None
    volumes: int | None
    eps: int | None
    total_episodes: int | None
    images: BangumiImages | None
    rating: BangumiRating | None
    rank: int | None
    collection: BangumiCollection | None
    tags: list[BangumiTag]
    meta_tags: list[str]


@dataclass(frozen=True)
class BangumiCalendarItem:
    """``/calendar`` 单条番剧条目（精简后）。

    已去除 ``url`` / ``images`` / ``air_weekday``；可空字段以 ``None`` 表示。
    """

    id: int
    type: int | None
    name: str
    name_cn: str | None
    summary: str | None
    air_date: str | None
    eps: int | None
    eps_count: int | None
    rating: BangumiRating | None
    rank: int | None
    collection: BangumiCollection | None


@dataclass(frozen=True)
class BangumiCalendarDay:
    """``/calendar`` 单个放送日。

    Attributes:
        weekday: 仅保留中文星期，例如 ``"星期一"``。
        items: 当日放送番剧列表。
    """

    weekday: str
    items: list[BangumiCalendarItem]


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

    async def get_calendar(self) -> list[BangumiCalendarDay]:
        """获取每日放送表（``GET /calendar``）。

        返回精简后的结构：``weekday`` 仅保留中文，每个 item 去除
        ``url`` / ``images`` / ``air_weekday``；可空字段以 ``None`` 表示。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        response = await self.get("/calendar")
        return [self._parse_calendar_day(day) for day in response.json()]

    async def get_subject(self, subject_id: int) -> BangumiSubject:
        """获取条目详情（``GET /v0/subjects/{subject_id}``）。

        返回精简后的结构：去除 ``infobox`` / ``series`` / ``nsfw`` / ``locked``；
        可空字段以 ``None`` 表示，``rank`` 取自 ``rating.rank`` 提至顶层。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        response = await self.get(f"/v0/subjects/{subject_id}")
        return self._parse_subject(response.json())

    @staticmethod
    def _parse_rating(raw: dict[str, object] | None) -> BangumiRating | None:
        """解析评分聚合；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return BangumiRating(
            score=_as_float(raw.get("score")),
            total=_as_int(raw.get("total")),
            count=raw.get("count"),  # type: ignore[arg-type]
        )

    @staticmethod
    def _parse_collection(raw: dict[str, object] | None) -> BangumiCollection | None:
        """解析收藏统计；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return BangumiCollection(
            wish=_as_int(raw.get("wish")),
            collect=_as_int(raw.get("collect")),
            doing=_as_int(raw.get("doing")),
            on_hold=_as_int(raw.get("on_hold")),
            dropped=_as_int(raw.get("dropped")),
        )

    @staticmethod
    def _parse_calendar_item(raw: dict[str, object]) -> BangumiCalendarItem:
        """解析单条番剧条目，逐字段容错缺失键 / None。"""
        return BangumiCalendarItem(
            id=_as_int(raw.get("id")) or 0,
            type=_as_int(raw.get("type")),
            name=raw.get("name") or "",
            name_cn=_as_str(raw.get("name_cn")),
            summary=_as_str(raw.get("summary")),
            air_date=_as_str(raw.get("air_date")),
            eps=_as_int(raw.get("eps")),
            eps_count=_as_int(raw.get("eps_count")),
            rating=BangumiClient._parse_rating(raw.get("rating")),  # type: ignore[arg-type]
            rank=_as_int(raw.get("rank")),
            collection=BangumiClient._parse_collection(raw.get("collection")),  # type: ignore[arg-type]
        )

    @staticmethod
    def _parse_calendar_day(raw: dict[str, object]) -> BangumiCalendarDay:
        """解析单个放送日：``weekday`` 取其中文字段。"""
        weekday_raw: dict[str, object] | None = raw.get("weekday")  # type: ignore[assignment]
        weekday = _as_str(weekday_raw.get("cn")) if weekday_raw else None
        items_raw: list[dict[str, object]] = raw.get("items") or []  # type: ignore[assignment]
        return BangumiCalendarDay(
            weekday=weekday or "",
            items=[BangumiClient._parse_calendar_item(item) for item in items_raw],
        )

    @staticmethod
    def _parse_images(raw: dict[str, object] | None) -> BangumiImages | None:
        """解析封面图各尺寸 URL；输入为 falsy 时返回 ``None``。"""
        if not raw:
            return None
        return BangumiImages(
            large=_as_str(raw.get("large")),
            common=_as_str(raw.get("common")),
            medium=_as_str(raw.get("medium")),
            small=_as_str(raw.get("small")),
            grid=_as_str(raw.get("grid")),
        )

    @staticmethod
    def _parse_tag(raw: dict[str, object]) -> BangumiTag:
        """解析单个标签，逐字段容错缺失键 / None。"""
        return BangumiTag(
            name=raw.get("name") or "",
            count=_as_int(raw.get("count")),
        )

    @staticmethod
    def _parse_subject(raw: dict[str, object]) -> BangumiSubject:
        """解析条目详情，逐字段容错缺失键 / None。"""
        rating_raw: dict[str, object] | None = raw.get("rating")  # type: ignore[assignment]
        rating = BangumiClient._parse_rating(rating_raw)
        rank = _as_int(rating_raw.get("rank")) if rating_raw else None
        tags_raw: list[dict[str, object]] = raw.get("tags") or []  # type: ignore[assignment]
        meta_tags_raw: list[object] = raw.get("meta_tags") or []  # type: ignore[assignment]
        return BangumiSubject(
            id=_as_int(raw.get("id")) or 0,
            type=_as_int(raw.get("type")),
            name=raw.get("name") or "",
            name_cn=_as_str(raw.get("name_cn")),
            summary=_as_str(raw.get("summary")),
            date=_as_str(raw.get("date")),
            platform=_as_str(raw.get("platform")),
            volumes=_as_int(raw.get("volumes")),
            eps=_as_int(raw.get("eps")),
            total_episodes=_as_int(raw.get("total_episodes")),
            images=BangumiClient._parse_images(raw.get("images")),  # type: ignore[arg-type]
            rating=rating,
            rank=rank,
            collection=BangumiClient._parse_collection(raw.get("collection")),  # type: ignore[arg-type]
            tags=[BangumiClient._parse_tag(tag) for tag in tags_raw],
            meta_tags=[str(tag) for tag in meta_tags_raw if tag is not None],
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
