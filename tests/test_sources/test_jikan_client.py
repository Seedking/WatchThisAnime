"""``JikanClient.search_anime`` 单测。

沿用 ``test_bangumi_client.py`` 风格：``asyncio.run`` 包裹异步体，``httpx.MockTransport``
注入，不起真实网络请求。
"""

import asyncio

import httpx

from src.sources.jikan_client import JikanClient

# 取自用户提供的 getAnimeSearch 响应示例（单条 data + pagination），含 images 以便
# 验证裁剪。
_SAMPLE_SEARCH = {
    "data": [
        {
            "mal_id": 1,
            "url": "https://myanimelist.net/anime/1/Cowboy_Bebop",
            "images": {
                "jpg": {
                    "image_url": "https://cdn.myanimelist.net/images/anime/4/19644.jpg",
                    "small_image_url": "https://cdn.myanimelist.net/images/anime/4/19644t.jpg",
                    "large_image_url": "https://cdn.myanimelist.net/images/anime/4/19644l.jpg",
                },
                "webp": {
                    "image_url": "https://cdn.myanimelist.net/images/anime/4/19644.webp",
                    "small_image_url": "https://cdn.myanimelist.net/images/anime/4/19644t.webp",
                    "large_image_url": "https://cdn.myanimelist.net/images/anime/4/19644l.webp",
                },
            },
            "trailer": {
                "youtube_id": "gY5n3yq",
                "url": "https://www.youtube.com/watch?v=gY5n3yq",
                "embed_url": "https://www.youtube.com/embed/gY5n3yq",
            },
            "approved": True,
            "titles": [
                {"type": "Default", "title": "Cowboy Bebop"},
                {"type": "Japanese", "title": "カウボーイビバップ"},
                {"type": "English", "title": "Cowboy Bebop"},
            ],
            "title": "Cowboy Bebop",
            "title_english": "Cowboy Bebop",
            "title_japanese": "カウボーイビバップ",
            "title_synonyms": ["Cowboy Bebop"],
            "type": "TV",
            "source": "Original",
            "episodes": 26,
            "status": "Finished Airing",
            "airing": False,
            "aired": {
                "from": "1998-04-03T00:00:00+00:00",
                "to": "1999-04-23T00:00:00+00:00",
                "prop": {
                    "from": {"day": 3, "month": 4, "year": 1998},
                    "to": {"day": 23, "month": 4, "year": 1999},
                    "string": "Apr 3, 1998 to Apr 23, 1999",
                },
            },
            "duration": "24 min per ep",
            "rating": "R - 17+ (violence & profanity)",
            "score": 8.75,
            "scored_by": 950000,
            "rank": 183,
            "popularity": 43,
            "members": 1500000,
            "favorites": 90000,
            "synopsis": "In the year 2071...",
            "background": "The anime was produced by Sunrise.",
            "season": "spring",
            "year": 1998,
            "broadcast": {
                "day": "Saturdays",
                "time": "01:00",
                "timezone": "Asia/Tokyo",
                "string": "Saturdays at 01:00 (JST)",
            },
            "producers": [
                {"mal_id": 23, "type": "anime", "name": "Bandai Visual", "url": "https://myanimelist.net/anime/producer/23/Bandai_Visual"}
            ],
            "licensors": [
                {"mal_id": 102, "type": "anime", "name": "Funimation", "url": "https://myanimelist.net/anime/producer/102/Funimation"}
            ],
            "studios": [
                {"mal_id": 14, "type": "anime", "name": "Sunrise", "url": "https://myanimelist.net/anime/producer/14/Sunrise"}
            ],
            "genres": [
                {"mal_id": 1, "type": "anime", "name": "Action", "url": "https://myanimelist.net/anime/genre/1/Action"},
                {"mal_id": 4, "type": "anime", "name": "Adventure", "url": "https://myanimelist.net/anime/genre/4/Adventure"},
            ],
            "explicit_genres": [],
            "themes": [
                {"mal_id": 50, "type": "anime", "name": "Adult Cast", "url": "https://myanimelist.net/anime/genre/50/Adult_Cast"}
            ],
            "demographics": [
                {"mal_id": 42, "type": "anime", "name": "Seinen", "url": "https://myanimelist.net/anime/genre/42/Seinen"}
            ],
        }
    ],
    "pagination": {
        "last_visible_page": 1,
        "has_next_page": False,
        "current_page": 1,
        "items": {"count": 1, "total": 1, "per_page": 25},
    },
}


def test_search_anime_parses_and_drops_images() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_SAMPLE_SEARCH)

    async def run() -> None:
        client = JikanClient(transport=httpx.MockTransport(handler))
        result = await client.search_anime(q="cowboy")
        await client.aclose()

        # 请求落点与 User-Agent。
        assert captured["url"].startswith("https://api.jikan.moe/v4/anime")
        assert captured["ua"].startswith("WatchThisAnime")

        # data 与 pagination 基本结构。
        assert len(result.data) == 1
        assert result.pagination is not None

        anime = result.data[0]
        # 标量字段解析。
        assert anime.mal_id == 1
        assert anime.url == "https://myanimelist.net/anime/1/Cowboy_Bebop"
        assert anime.approved is True
        assert anime.title == "Cowboy Bebop"
        assert anime.title_english == "Cowboy Bebop"
        assert anime.title_japanese == "カウボーイビバップ"
        assert anime.title_synonyms == ["Cowboy Bebop"]
        assert anime.type == "TV"
        assert anime.source == "Original"
        assert anime.episodes == 26
        assert anime.status == "Finished Airing"
        assert anime.airing is False
        assert anime.duration == "24 min per ep"
        assert anime.rating == "R - 17+ (violence & profanity)"
        assert anime.score == 8.75
        assert anime.scored_by == 950000
        assert anime.rank == 183
        assert anime.popularity == 43
        assert anime.members == 1500000
        assert anime.favorites == 90000
        assert anime.season == "spring"
        assert anime.year == 1998

        # titles 解析。
        assert len(anime.titles) == 3
        assert anime.titles[0].type == "Default"
        assert anime.titles[0].title == "Cowboy Bebop"

        # trailer 解析。
        assert anime.trailer is not None
        assert anime.trailer.youtube_id == "gY5n3yq"
        assert anime.trailer.embed_url == "https://www.youtube.com/embed/gY5n3yq"

        # aired 解析（含 prop，from_ 因关键字加下划线）。
        assert anime.aired is not None
        assert anime.aired.from_ == "1998-04-03T00:00:00+00:00"
        assert anime.aired.to == "1999-04-23T00:00:00+00:00"
        assert anime.aired.prop is not None
        assert anime.aired.prop.from_ is not None
        assert anime.aired.prop.from_.year == 1998
        assert anime.aired.prop.to is not None
        assert anime.aired.prop.to.day == 23
        assert anime.aired.prop.string == "Apr 3, 1998 to Apr 23, 1999"

        # broadcast 解析。
        assert anime.broadcast is not None
        assert anime.broadcast.day == "Saturdays"
        assert anime.broadcast.string == "Saturdays at 01:00 (JST)"

        # 实体列表复用 JikanEntity。
        assert [g.name for g in anime.genres] == ["Action", "Adventure"]
        assert anime.genres[0].mal_id == 1
        assert anime.studios[0].name == "Sunrise"
        assert anime.demographics[0].mal_id == 42
        assert anime.explicit_genres == []
        assert len(anime.themes) == 1

        # images 已裁剪：dataclass 不应持有该属性。
        assert not hasattr(anime, "images")

        # pagination 解析。
        pagination = result.pagination
        assert pagination.last_visible_page == 1
        assert pagination.has_next_page is False
        assert pagination.current_page == 1
        assert pagination.items is not None
        assert pagination.items.count == 1
        assert pagination.items.total == 1
        assert pagination.items.per_page == 25

    asyncio.run(run())


def test_search_anime_serializes_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = str(request.url)
        return httpx.Response(200, json={"data": [], "pagination": None})

    async def run() -> None:
        client = JikanClient(transport=httpx.MockTransport(handler))
        await client.search_anime(
            q="frieren",
            type="TV",
            limit=3,
            score=8.5,
            unapproved=True,
            sfw=False,
            order_by="score",
            sort="desc",
            genres="1,2",
            start_date="2023",
        )
        await client.aclose()

        query = captured["query"]
        # 字符串 / 数值参数原样序列化。
        assert "q=frieren" in query
        assert "type=TV" in query
        assert "limit=3" in query
        assert "score=8.5" in query
        assert "order_by=score" in query
        assert "sort=desc" in query
        # 逗号被 httpx URL 编码为 %2C。
        assert "genres=1%2C2" in query
        assert "start_date=2023" in query
        # bool 序列化为 true / false。
        assert "unapproved=true" in query
        assert "sfw=false" in query
        # None 参数不出现在查询串。
        assert "min_score" not in query
        assert "max_score" not in query
        assert "letter" not in query
        assert "producers" not in query
        assert "end_date" not in query

    asyncio.run(run())


def test_search_anime_handles_none_fields() -> None:
    """trailer / aired / broadcast / rating / score 等为 null、列表缺失时安全置空。"""
    payload = {
        "data": [
            {
                "mal_id": 99,
                "title": "テスト",
                "images": {"jpg": {"image_url": "x"}},
                "trailer": None,
                "aired": None,
                "broadcast": None,
                "rating": None,
                "score": None,
                "rank": None,
            }
        ],
        "pagination": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = JikanClient(transport=httpx.MockTransport(handler))
        result = await client.search_anime()
        await client.aclose()

        anime = result.data[0]
        assert anime.mal_id == 99
        assert anime.title == "テスト"
        assert anime.trailer is None
        assert anime.aired is None
        assert anime.broadcast is None
        assert anime.rating is None
        assert anime.score is None
        assert anime.rank is None
        assert anime.approved is None
        assert anime.airing is None
        # 缺失的列表字段安全置空。
        assert anime.titles == []
        assert anime.title_synonyms == []
        assert anime.genres == []
        assert anime.studios == []
        # 缺失的标量字段同样安全置 None。
        assert anime.type is None
        assert anime.episodes is None
        assert anime.year is None
        # pagination 为 null 时整体为 None。
        assert result.pagination is None

    asyncio.run(run())


def test_search_anime_empty_data_and_pagination() -> None:
    """data 为空列表、pagination 含 has_next_page=True 时安全解析。"""
    payload = {
        "data": [],
        "pagination": {
            "last_visible_page": 5,
            "has_next_page": True,
            "current_page": 1,
            "items": {"count": 0, "total": 100, "per_page": 25},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = JikanClient(transport=httpx.MockTransport(handler))
        result = await client.search_anime(page=1)
        await client.aclose()

        assert result.data == []
        assert result.pagination is not None
        assert result.pagination.has_next_page is True
        assert result.pagination.last_visible_page == 5
        assert result.pagination.items is not None
        assert result.pagination.items.total == 100
        assert result.pagination.items.count == 0

    asyncio.run(run())
