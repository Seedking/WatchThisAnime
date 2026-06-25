"""``src.utils.base_api_client`` 单元测试。

由于项目未声明 ``pytest-asyncio`` 依赖，每个用例用 ``asyncio.run`` 包裹异步体，
避免新增依赖。HTTP 交互通过 ``httpx.MockTransport`` / 自定义 ``AsyncBaseTransport``
注入，不发起真实网络请求。
"""

import asyncio
import json

import httpx
import pytest

from src.utils import base_api_client
from src.utils.client_config import ClientConfig
from src.utils.base_api_client import (
    APIClientConnectionError,
    APIClientHTTPError,
    APIClientTimeoutError,
    BaseAPIClient,
)


class _DummyClient(BaseAPIClient):
    """``BaseAPIClient`` 的最小可实例化子类，供测试使用。"""

    def __init__(
        self,
        base_url: str = "https://example.test",
        config: ClientConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url=base_url, config=config, transport=transport)

    @property
    def default_headers(self) -> dict[str, str]:
        return {"User-Agent": "WatchThisAnime-test/0.1"}


class _CountingTransport(httpx.AsyncBaseTransport):
    """记录在途并发数并阻塞至 gate 放行的自定义传输，用于验证排队行为。"""

    def __init__(self, gate: asyncio.Event) -> None:
        self.gate: asyncio.Event = gate
        self.in_flight: int = 0
        self.max_in_flight: int = 0
        self.count: int = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.count += 1
        try:
            await self.gate.wait()
        finally:
            self.in_flight -= 1
        return httpx.Response(200, json={"i": self.count})

    async def aclose(self) -> None:
        return None


def test_get_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        resp = await client.get("/foo", params={"q": "1"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert captured["method"] == "GET"
        assert captured["url"] == "https://example.test/foo?q=1"
        await client.aclose()

    asyncio.run(run())


def test_post_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = request.content
        return httpx.Response(201, json={"id": 7})

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        resp = await client.post("/bar", json={"name": "x"})
        assert resp.status_code == 201
        assert resp.json() == {"id": 7}
        assert captured["method"] == "POST"
        assert json.loads(captured["body"]) == {"name": "x"}  # type: ignore[arg-type]
        await client.aclose()

    asyncio.run(run())


def test_concurrency_queueing() -> None:
    """``max_concurrent_requests=2`` 时，5 个并发请求任意时刻在途数 ≤ 2 且全部完成。"""

    async def run() -> None:
        gate = asyncio.Event()
        transport = _CountingTransport(gate)
        client = _DummyClient(
            config=ClientConfig(max_concurrent_requests=2),
            transport=transport,
        )
        tasks = [asyncio.create_task(client.get(f"/{i}")) for i in range(5)]

        # 让前 2 个请求进入传输层并在 gate 处等待，其余应在 semaphore 处排队。
        await asyncio.sleep(0.05)
        assert transport.in_flight == 2

        gate.set()
        responses = await asyncio.gather(*tasks)

        assert len(responses) == 5
        assert all(r.status_code == 200 for r in responses)
        assert transport.max_in_flight == 2
        await client.aclose()

    asyncio.run(run())


def test_retry_on_5xx_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_api_client, "_RETRY_BACKOFF", 0.0)
    calls: dict[str, int] = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        resp = await client.get("/retry")
        assert resp.status_code == 200
        assert calls["n"] == 3
        await client.aclose()

    asyncio.run(run())


def test_connection_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_api_client, "_RETRY_BACKOFF", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        with pytest.raises(APIClientConnectionError):
            await client.get("/err")
        await client.aclose()

    asyncio.run(run())


def test_timeout_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_api_client, "_RETRY_BACKOFF", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        with pytest.raises(APIClientTimeoutError):
            await client.get("/slow")
        await client.aclose()

    asyncio.run(run())


def test_http_error_wrapped() -> None:
    calls: dict[str, int] = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    async def run() -> None:
        client = _DummyClient(transport=httpx.MockTransport(handler))
        with pytest.raises(APIClientHTTPError) as exc:
            await client.get("/missing")
        assert exc.value.status_code == 404
        # 4xx 不重试，仅请求一次。
        assert calls["n"] == 1
        await client.aclose()

    asyncio.run(run())
