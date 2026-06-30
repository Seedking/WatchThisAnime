"""``MoegirlClient`` 单测。

沿用 ``test_jikan_client.py`` 风格：``asyncio.run`` 包裹异步体，``httpx.MockTransport``
注入，不起真实网络请求。末尾的 ``test_get_page_live`` 为真实网络联调测试，默认跳过。
"""

import asyncio
import os

import httpx
import pytest

from src.sources.moegirl_client import MoegirlClient, MoegirlPage

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
        assert captured["url"].startswith("https://zh.moegirl.org.cn/rest.php/v1/search/page")
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


# 取自 MediaWiki REST page object 文档样例（``GET /rest.php/v1/page/{key}``）。
_SAMPLE_PAGE = {
    "id": 9228,
    "key": "Earth",
    "title": "Earth",
    "latest": {"id": 963613515, "timestamp": "2020-06-20T20:05:55Z"},
    "content_model": "wikitext",
    "license": {
        "url": "//creativecommons.org/licenses/by-sa/3.0/",
        "title": "Creative Commons Attribution-Share Alike 3.0",
    },
    "html_url": "https://en.wikipedia.org/w/rest.php/v1/page/Earth/html",
}


def test_get_page_parses_response() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_SAMPLE_PAGE)

    async def run() -> None:
        client = MoegirlClient(transport=httpx.MockTransport(handler))
        page = await client.get_page(key="Earth")
        await client.aclose()

        # 请求落点与 User-Agent。
        assert captured["url"] == "https://zh.moegirl.org.cn/rest.php/v1/page/Earth"
        assert captured["ua"].startswith("WatchThisAnime")

        # 标量字段解析。
        assert page.id == 9228
        assert page.key == "Earth"
        assert page.title == "Earth"
        assert page.content_model == "wikitext"
        assert page.html_url == "https://en.wikipedia.org/w/rest.php/v1/page/Earth/html"

        # latest 嵌套对象。
        assert page.latest is not None
        assert page.latest.id == 963613515
        assert page.latest.timestamp == "2020-06-20T20:05:55Z"

        # license 嵌套对象。
        assert page.license is not None
        assert page.license.url == "//creativecommons.org/licenses/by-sa/3.0/"
        assert page.license.title.startswith("Creative Commons")

        # 按 id 生成的稳定 curid 打开链接。
        assert page.url == "https://zh.moegirl.org.cn/index.php?curid=9228"

    asyncio.run(run())


def test_get_page_handles_none_fields() -> None:
    """latest / license / content_model / html_url 缺失时安全置 None；url 仍由 id 生成。"""
    payload = {"id": 649332, "key": "当前、正被打扰中！", "title": "当前、正被打扰中！"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> None:
        client = MoegirlClient(transport=httpx.MockTransport(handler))
        page = await client.get_page(key="当前、正被打扰中！")
        await client.aclose()

        assert page.id == 649332
        assert page.title == "当前、正被打扰中！"
        assert page.content_model is None
        assert page.latest is None
        assert page.license is None
        assert page.html_url is None
        assert page.url == "https://zh.moegirl.org.cn/index.php?curid=649332"

    asyncio.run(run())


def test_page_url_builder() -> None:
    """page_url 按 page id 生成 index.php?curid= 形式的稳定 URL。"""
    assert (
        MoegirlClient.page_url(649332)
        == "https://zh.moegirl.org.cn/index.php?curid=649332"
    )
    assert MoegirlClient.page_url(1) == "https://zh.moegirl.org.cn/index.php?curid=1"


_LIVE = os.environ.get("RUN_LIVE") == "1"


@pytest.mark.skipif(not _LIVE, reason="需真实网络；设置 RUN_LIVE=1 启用")
def test_get_page_live() -> None:
    """真实网络联调：拉取 page ID 649332（「当前、正被打扰中！」）。

    REST ``/page/{key}`` 按 key/title 查询，故用该页面的 key 取页，再校验响应
    里的 ``id == 649332`` 与生成的 ``curid`` 打开链接。
    """
    async def run() -> None:
        async with MoegirlClient() as client:
            page = await client.get_page(key="当前、正被打扰中！")

        assert isinstance(page, MoegirlPage)
        assert page.id == 649332
        assert page.title == "当前、正被打扰中！"
        # 按 id 生成的稳定「打开页面」链接。
        assert page.url == "https://zh.moegirl.org.cn/index.php?curid=649332"

    asyncio.run(run())
