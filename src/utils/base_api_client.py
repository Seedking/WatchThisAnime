"""HTTP 客户端抽象基类。

``BaseAPIClient`` 封装 ``httpx.AsyncClient``，对 sources 层各 client 提供统一基类。
子类只需定义 ``default_headers`` 抽象属性，并在构造时通过 ``base_url`` 指定请求网络
地址。内置：

- 统一超时（来自 ``ClientConfig.timeout``）；
- 单个 client 的在途并发限流（``asyncio.Semaphore``），达到 ``max_concurrent_requests``
  后后续请求排队等待空位；
- 对连接错误 / 超时 / 5xx 的指数退避重试；
- 自定义异常层次结构，不向外暴露原始 httpx 异常。
"""

from abc import ABC, abstractmethod
import asyncio
from typing import Any

import httpx

from src.utils.client_config import ClientConfig

# 重试参数：对连接错误 / 超时 / 5xx 最多重试 _MAX_RETRIES 次，指数退避。
_MAX_RETRIES: int = 3
_RETRY_BACKOFF: float = 0.5


class APIClientError(Exception):
    """HTTP client 错误基类。"""


class APIClientConnectionError(APIClientError):
    """网络/连接故障（包装 httpx.TransportError，超时除外）。"""


class APIClientTimeoutError(APIClientError):
    """请求超时（包装 httpx.TimeoutException）。"""


class APIClientHTTPError(APIClientError):
    """非 2xx HTTP 响应。

    Attributes:
        status_code: HTTP 状态码。
    """

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code


class BaseAPIClient(ABC):
    """所有 sources 层 HTTP client 的抽象基类。

    子类需实现 ``default_headers`` 抽象属性，并在构造时传入 ``base_url``。

    Example:
        >>> class BangumiClient(BaseAPIClient):
        ...     def __init__(self, config: ClientConfig | None = None) -> None:
        ...         super().__init__(base_url="https://api.bgm.tv", config=config)
        ...     @property
        ...     def default_headers(self) -> dict[str, str]:
        ...         return {"User-Agent": "WatchThisAnime/0.1"}
    """

    def __init__(
        self,
        base_url: str,
        config: ClientConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化 client。

        Args:
            base_url: 请求网络地址（末尾 ``/`` 会被去除）。
            config: 公共配置，缺省时使用 ``ClientConfig()`` 默认值。
            transport: 可选的自定义异步传输层，供测试注入 ``httpx.MockTransport``。
        """
        self._base_url: str = base_url.rstrip("/")
        self._config: ClientConfig = config or ClientConfig()
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._config.timeout,
            headers=self.default_headers,
            transport=transport,
        )

    @property
    @abstractmethod
    def default_headers(self) -> dict[str, str]:
        """子类提供的默认请求头。"""

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发起 GET 请求。

        Args:
            path: 相对 ``base_url`` 的路径。
            params: 查询参数。
            headers: 本次请求覆盖默认头的额外请求头。

        Returns:
            成功（2xx）时的 ``httpx.Response``。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        return await self._request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        *,
        json: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发起 POST 请求。

        Args:
            path: 相对 ``base_url`` 的路径。
            json: JSON 请求体（与 ``data`` 二选一）。
            data: 表单/原始请求体（与 ``json`` 二选一）。
            headers: 本次请求覆盖默认头的额外请求头。

        Returns:
            成功（2xx）时的 ``httpx.Response``。

        Raises:
            APIClientTimeoutError: 请求超时。
            APIClientConnectionError: 网络/连接故障。
            APIClientHTTPError: 非 2xx 响应。
        """
        return await self._request("POST", path, json=json, data=data, headers=headers)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """执行单次请求，含并发限流、重试与异常包装。

        ``asyncio.Semaphore`` 限制单个 client 的在途并发数；达到上限时新请求在此排队。
        """
        async with self._semaphore:
            last_exc: APIClientError | None = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    response = await self._client.request(method, path, **kwargs)
                except httpx.TimeoutException as exc:
                    # TimeoutException 是 TransportError 的子类，必须先捕获。
                    last_exc = APIClientTimeoutError(f"请求超时: {exc}")
                    retryable = True
                except httpx.TransportError as exc:
                    last_exc = APIClientConnectionError(f"连接故障: {exc}")
                    retryable = True
                else:
                    if response.status_code >= 500 and attempt < _MAX_RETRIES:
                        await asyncio.sleep(_RETRY_BACKOFF * (2**attempt))
                        continue
                    if response.status_code >= 400:
                        raise APIClientHTTPError(response.status_code)
                    return response

                if retryable and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF * (2**attempt))
                    continue
                # 重试耗尽，抛出最后一次的自定义异常。
                raise last_exc

            # 理论不可达：循环必然通过 return 或 raise 退出。
            raise last_exc  # pragma: no cover

    async def aclose(self) -> None:
        """关闭底层 ``httpx.AsyncClient``，释放连接资源。"""
        await self._client.aclose()

    async def __aenter__(self) -> "BaseAPIClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()
