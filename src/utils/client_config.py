"""HTTP client 公共配置。

所有 sources 层 client（bangumi / moegirl / jikan / github_dataset）共享同一份
配置。当前仅包含请求超时时间与单个 client 的最大并发请求数量；后续如需从环境
变量覆盖，可再 ``pixi add pydantic-settings`` 升级为 ``BaseSettings``。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientConfig:
    """所有 HTTP client 共享的公共配置。

    Attributes:
        timeout: 单次请求超时时间（秒）。
        max_concurrent_requests: 单个 client 实例允许的在途并发请求数量；
            达到上限后后续请求排队等待空位（并发限流，非请求总量配额）。
    """

    timeout: float = 10.0
    max_concurrent_requests: int = 10
