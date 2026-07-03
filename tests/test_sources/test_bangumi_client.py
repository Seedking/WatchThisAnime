"""``BangumiClient.get_calendar`` 单测。

沿用 ``test_source_clients.py`` 风格：``asyncio.run`` 包裹异步体，``httpx.MockTransport``
注入，不起真实网络请求。
"""

import asyncio
import os
import time

import httpx
import pytest

from src.sources.bangumi_client import BangumiClient
from src.utils.base_api_client import APIClientError

# 取自用户提供的 /calendar 示例（一个 weekday、一个 item）。
_SAMPLE_CALENDAR = [
    {
        "weekday": {
            "en": "Mon",
            "cn": "星期一",
            "ja": "月耀日",
            "id": 1,
        },
        "items": [
            {
                "id": 12,
                "url": "https://bgm.tv/subject/12",
                "type": 2,
                "name": "ちょびっツ",
                "name_cn": "人形电脑天使心",
                "summary": "在不久的将来...",
                "air_date": "2002-04-02",
                "air_weekday": 2,
                "images": {
                    "large": "https://lain.bgm.tv/pic/cover/l/c2/0a/12_24O6L.jpg",
                    "common": "https://lain.bgm.tv/pic/cover/c/c2/0a/12_24O6L.jpg",
                },
                "eps": 27,
                "eps_count": 27,
                "rating": {
                    "total": 2289,
                    "count": {"1": 5, "2": 3, "7": 659, "8": 885},
                    "score": 7.6,
                },
                "rank": 573,
                "collection": {
                    "wish": 608,
                    "collect": 3010,
                    "doing": 103,
                    "on_hold": 284,
                    "dropped": 86,
                },
            }
        ],
    }
]


def test_get_calendar_parses_and_trims_fields() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_SAMPLE_CALENDAR)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        days = await client.get_calendar()
        await client.aclose()

        # 请求落点与 User-Agent。
        assert captured["url"].startswith("https://api.bgm.tv/calendar")
        assert captured["ua"].startswith("WatchThisAnime")

        # 仅一个放送日，weekday 只剩中文。
        assert len(days) == 1
        day = days[0]
        assert day.weekday == "星期一"
        assert len(day.items) == 1

        item = day.items[0]
        # 保留字段正确解析。
        assert item.id == 12
        assert item.type == 2
        assert item.name == "ちょびっツ"
        assert item.name_cn == "人形电脑天使心"
        assert item.air_date == "2002-04-02"
        assert item.eps == 27
        assert item.eps_count == 27
        assert item.rank == 573

        # rating 解析。
        assert item.rating is not None
        assert item.rating.score == 7.6
        assert item.rating.total == 2289
        assert item.rating.count == {"1": 5, "2": 3, "7": 659, "8": 885}

        # collection 解析。
        assert item.collection is not None
        assert item.collection.wish == 608
        assert item.collection.collect == 3010
        assert item.collection.doing == 103
        assert item.collection.on_hold == 284
        assert item.collection.dropped == 86

        # 已去除字段：dataclass 不应持有这些属性。
        for removed in ("url", "images", "air_weekday"):
            assert not hasattr(item, removed)

    asyncio.run(run())


def test_get_calendar_handles_none_fields() -> None:
    """rating / rank / collection 缺失或为 null 时不抛异常，置 None。"""
    payload = [
        {
            "weekday": {"cn": "星期二"},
            "items": [
                {
                    "id": 99,
                    "name": "テスト",
                    "rating": None,
                    "rank": None,
                    "collection": None,
                }
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        days = await client.get_calendar()
        await client.aclose()

        item = days[0].items[0]
        assert item.id == 99
        assert item.rating is None
        assert item.rank is None
        assert item.collection is None
        # 缺失的字符串 / 整数字段同样安全置 None / 默认。
        assert item.name_cn is None
        assert item.summary is None
        assert item.eps is None
        assert item.type is None

    asyncio.run(run())


def test_get_calendar_empty_items() -> None:
    """某放送日 items 为空或缺失时返回空列表。"""
    payload = [
        {"weekday": {"cn": "星期三"}, "items": []},
        {"weekday": {"cn": "星期四"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        days = await client.get_calendar()
        await client.aclose()

        assert [d.weekday for d in days] == ["星期三", "星期四"]
        assert days[0].items == []
        assert days[1].items == []

    asyncio.run(run())


# 取自用户提供的 /v0/subjects/{subject_id} 示例（含 images / rating(带 rank) /
# collection / tags / meta_tags / infobox，其中 infobox 应被裁剪）。
_SAMPLE_SUBJECT = {
    "id": 12,
    "type": 2,
    "name": "ちょびっツ",
    "name_cn": "人形电脑天使心",
    "summary": "在不久的将来...",
    "series": False,
    "nsfw": False,
    "locked": False,
    "date": "2002-04-02",
    "platform": "TV",
    "images": {
        "large": "https://lain.bgm.tv/pic/cover/l/c2/0a/12_24O6L.jpg",
        "common": "https://lain.bgm.tv/pic/cover/c/c2/0a/12_24O6L.jpg",
        "medium": "https://lain.bgm.tv/pic/cover/m/c2/0a/12_24O6L.jpg",
        "small": "https://lain.bgm.tv/pic/cover/s/c2/0a/12_24O6L.jpg",
        "grid": "https://lain.bgm.tv/pic/cover/g/c2/0a/12_24O6L.jpg",
    },
    "infobox": [{"key": "话数", "value": 27}],
    "volumes": 0,
    "eps": 27,
    "total_episodes": 27,
    "rating": {
        "rank": 573,
        "total": 2289,
        "count": {"1": 5, "2": 3, "7": 659, "8": 885},
        "score": 7.6,
    },
    "collection": {
        "wish": 608,
        "collect": 3010,
        "doing": 103,
        "on_hold": 284,
        "dropped": 86,
    },
    "meta_tags": ["科幻", "恋爱"],
    "tags": [
        {"name": "科幻", "count": 800},
        {"name": "恋爱", "count": 600},
    ],
}


def test_get_subject_parses_and_trims_fields() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_SAMPLE_SUBJECT)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        subject = await client.get_subject(12)
        await client.aclose()

        # 请求落点与 User-Agent。
        assert captured["url"].startswith("https://api.bgm.tv/v0/subjects/12")
        assert captured["ua"].startswith("WatchThisAnime")

        # 基本字段。
        assert subject.id == 12
        assert subject.type == 2
        assert subject.name == "ちょびっツ"
        assert subject.name_cn == "人形电脑天使心"
        assert subject.summary == "在不久的将来..."
        assert subject.date == "2002-04-02"
        assert subject.platform == "TV"
        assert subject.volumes == 0
        assert subject.eps == 27
        assert subject.total_episodes == 27

        # images 解析。
        assert subject.images is not None
        assert subject.images.large.endswith("12_24O6L.jpg")
        assert subject.images.common.endswith("12_24O6L.jpg")
        assert subject.images.medium is not None
        assert subject.images.small is not None
        assert subject.images.grid is not None

        # rating（复用 BangumiRating）+ rank 取自 rating.rank。
        assert subject.rating is not None
        assert subject.rating.score == 7.6
        assert subject.rating.total == 2289
        assert subject.rating.count == {"1": 5, "2": 3, "7": 659, "8": 885}
        assert subject.rank == 573

        # collection 解析。
        assert subject.collection is not None
        assert subject.collection.wish == 608
        assert subject.collection.collect == 3010
        assert subject.collection.doing == 103
        assert subject.collection.on_hold == 284
        assert subject.collection.dropped == 86

        # tags / meta_tags。
        assert [t.name for t in subject.tags] == ["科幻", "恋爱"]
        assert [t.count for t in subject.tags] == [800, 600]
        assert subject.meta_tags == ["科幻", "恋爱"]

        # 已裁剪字段：dataclass 不应持有这些属性。
        for removed in ("infobox", "series", "nsfw", "locked"):
            assert not hasattr(subject, removed)

    asyncio.run(run())


def test_get_subject_handles_none_fields() -> None:
    """rating / collection / images 为 null、tags / meta_tags 缺失时安全置空。"""
    payload = {
        "id": 99,
        "name": "テスト",
        "rating": None,
        "collection": None,
        "images": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        subject = await client.get_subject(99)
        await client.aclose()

        assert subject.id == 99
        assert subject.rating is None
        assert subject.rank is None
        assert subject.collection is None
        assert subject.images is None
        # 缺失的列表字段安全置空。
        assert subject.tags == []
        assert subject.meta_tags == []
        # 缺失的标量字段同样安全置 None。
        assert subject.name_cn is None
        assert subject.summary is None
        assert subject.date is None
        assert subject.eps is None
        assert subject.type is None

    asyncio.run(run())


def test_access_token_attaches_authorization_header() -> None:
    """传入 access_token 时，所有请求携带 ``Authorization: Bearer <token>`` 头。"""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=_SAMPLE_SUBJECT)

    async def run() -> None:
        client = BangumiClient(
            access_token="test-token", transport=httpx.MockTransport(handler)
        )
        await client.get_subject(12)
        await client.aclose()

    asyncio.run(run())
    assert captured["auth"] == "Bearer test-token"


def test_no_access_token_omits_authorization_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """未提供 token（且环境变量未设）时，请求不带 ``Authorization`` 头。"""
    monkeypatch.delenv("BANGUMI_ACCESS_TOKEN", raising=False)
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=_SAMPLE_SUBJECT)

    async def run() -> None:
        client = BangumiClient(transport=httpx.MockTransport(handler))
        await client.get_subject(12)
        await client.aclose()

    asyncio.run(run())
    assert captured["auth"] == ""


_LIVE = os.environ.get("RUN_LIVE") == "1"
_WEEKDAYS = {"星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"}


@pytest.mark.skipif(not _LIVE, reason="需真实网络；设置 RUN_LIVE=1 启用")
def test_get_calendar_live() -> None:
    """真实网络联调：拉取每日放送表，校验 weekday 中文与条目结构。

    ``bgm.tv`` 的 ``/calendar`` 端点较重，上游网关间歇性返回 502（实测同 UA 同库
    连续三次返回 200 / 502 / 200）。client 自带的 5xx 重试不足以覆盖其抖动窗口，
    故在测试层再重试若干次穿过瞬时 502；这不是掩盖 client 缺陷——端点正常时路径、
    UA、解析均正确（200 响应体约 73KB）。
    """
    async def run() -> None:
        days = None
        last_exc: Exception | None = None
        for _ in range(6):
            try:
                async with BangumiClient() as client:
                    days = await client.get_calendar()
                break
            except APIClientError as exc:
                last_exc = exc
                time.sleep(1.0)
        if days is None:
            raise AssertionError(f"/calendar 多次重试仍失败：{last_exc}")

        assert len(days) >= 1
        assert all(d.weekday in _WEEKDAYS for d in days)
        # 放送表应至少有一部番剧条目；抽样校验关键字段。
        total = sum(len(d.items) for d in days)
        assert total >= 1
        sample = next(d.items[0] for d in days if d.items)
        assert sample.id > 0
        assert sample.name  # 非空

    asyncio.run(run())


@pytest.mark.skipif(not _LIVE, reason="需真实网络；设置 RUN_LIVE=1 启用")
def test_get_subject_live() -> None:
    """真实网络联调：拉取 subject 12（「人形电脑天使心」），校验请求落点与字段解析。"""
    async def run() -> None:
        async with BangumiClient() as client:
            subject = await client.get_subject(12)

        assert subject.id == 12
        assert subject.name == "ちょびっツ"
        assert subject.name_cn == "人形电脑天使心"
        assert subject.date == "2002-04-02"

    asyncio.run(run())
