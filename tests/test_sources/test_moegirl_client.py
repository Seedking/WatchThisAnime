"""``MoegirlClient.search`` 单测。

沿用 ``test_jikan_client.py`` 风格：``asyncio.run`` 包裹异步体，``httpx.MockTransport``
注入，不起真实网络请求。
"""

import asyncio

import httpx

from src.sources.moegirl_client import MoegirlClient

# 取自用户提供的 MediaWiki REST 搜索响应示例（单条 page），含 thumbnail 以便验证裁剪。
_SAMPLE_SEARCH = {
    "pages": [
        {
            "id": 38930,
            "key": "Jupiter",
            "title": "Jupiter",
            "excerpt": "<span class=\"searchmatch\">Jupiter</span> is the fifth planet "
            "from the Sun and the largest in the Solar System.",
            "matched_title": None,
            "description": "fifth planet from the Sun and largest planet in the Solar System",
            "thumbnail": {
                "mimetype": "image/jpeg",
                "size": None,
                "width": 200,
                "height": 200,
                "duration": None,
                "url": "//upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Jupiter.jpg/200px-Jupiter.jpg",
            },
        }
    ]
}


def test_search_parses_and_drops_thumbnail() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_SAMPLE_SEARCH)

    async def run() -> None:
        client = MoegirlClient(transport=httpx.MockTransport(handler))
        result = await client.search(q="jupiter", limit=20)
        await client.aclose()

        # 请求落点与 User-Agent。
        assert captured["url"].startswith("https://zh.moegirl.org.cn/w/rest.php/v1/search/page")
        assert captured["ua"].startswith("WatchThisAnime")
        # 查询串含 q 与 limit。
        assert "q=jupiter" in captured["url"]
        assert "limit=20" in captured["url"]

        # pages 基本结构。
        assert len(result.pages) == 1

        page = result.pages[0]
        # 标量字段解析。
        assert page.id == 38930
        assert page.key == "Jupiter"
        assert page.title == "Jupiter"
        assert page.excerpt.startswith("<span class=\"searchmatch\">Jupiter</span>")
        assert page.matched_title is None
        assert page.description == "fifth planet from the Sun and largest planet in the Solar System"

        # thumbnail 已裁剪：dataclass 不应持有该属性。
        assert not hasattr(page, "thumbnail")

    asyncio.run(run())


def test_search_serializes_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["with_limit"] = str(request.url)
        return httpx.Response(200, json={"pages": []})

    def handler_no_limit(request: httpx.Request) -> httpx.Response:
        captured["without_limit"] = str(request.url)
        return httpx.Response(200, json={"pages": []})

    async def run() -> None:
        client = MoegirlClient(transport=httpx.MockTransport(handler))
        await client.search(q="frieren", limit=5)
        await client.aclose()

        client2 = MoegirlClient(transport=httpx.MockTransport(handler_no_limit))
        await client2.search(q="frieren")
        await client2.aclose()

        # 传 limit 时查询串含 q 与 limit。
        assert "q=frieren" in captured["with_limit"]
        assert "limit=5" in captured["with_limit"]
        # 不传 limit 时仅含 q，limit 不出现。
        assert "q=frieren" in captured["without_limit"]
        assert "limit" not in captured["without_limit"]

    asyncio.run(run())


def test_search_handles_none_fields_and_empty_pages() -> None:
    """matched_title / description / excerpt 为 null、pages 缺失或空列表时安全置空。"""
    payload = {
        "pages": [
            {
                "id": 99,
                "key": "Test",
                "title": "Test",
                "excerpt": None,
                "matched_title": None,
                "description": None,
                "thumbnail": {"url": "x"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async def run() -> None:
        client = MoegirlClient(transport=httpx.MockTransport(handler))
        result = await client.search(q="test")
        await client.aclose()

        page = result.pages[0]
        assert page.id == 99
        assert page.excerpt is None
        assert page.matched_title is None
        assert page.description is None
        assert not hasattr(page, "thumbnail")

        # pages 缺失时整体置 []。
        client2 = MoegirlClient(transport=httpx.MockTransport(empty_handler))
        empty_result = await client2.search(q="test")
        await client2.aclose()
        assert empty_result.pages == []

    asyncio.run(run())
