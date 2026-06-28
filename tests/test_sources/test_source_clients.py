"""三源 client（bangumi / moegirl / jikan）骨架单测。

沿用 ``test_base_api_client.py`` 风格：``asyncio.run`` 包裹异步体，``httpx.MockTransport``
注入，不起真实网络请求。
"""

import asyncio

import httpx
import pytest

from src.sources.bangumi_client import BangumiClient
from src.sources.jikan_client import JikanClient
from src.sources.moegirl_client import MoegirlClient


@pytest.mark.parametrize(
    ("client_cls", "base_url"),
    [
        (BangumiClient, "https://api.bgm.tv"),
        (MoegirlClient, "https://zh.moegirl.org.cn"),
        (JikanClient, "https://api.jikan.moe/v4"),
    ],
)
def test_client_base_url_and_user_agent(client_cls: type, base_url: str) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json={"ok": True})

    async def run() -> None:
        client = client_cls(transport=httpx.MockTransport(handler))
        # default_headers 必须携带 User-Agent 且以项目名开头。
        assert client.default_headers["User-Agent"].startswith("WatchThisAnime")
        resp = await client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # 请求实际发往各自 base_url。
        assert captured["url"].startswith(f"{base_url}/ping")
        assert captured["ua"].startswith("WatchThisAnime")
        await client.aclose()

    asyncio.run(run())
