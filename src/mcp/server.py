"""MCP 交互层：FastMCP 实例与鉴权中间件。

``WatchThisAnimeMCP`` 覆盖 ``streamable_http_app``，在返回的 Starlette app 上挂载
``JWTAuthMiddleware``（解析 ``Authorization: Bearer <JWT>`` → ``user_id`` 并注入请求
上下文，见 ``src/mcp/auth.py``），使 ``mcp.run(transport="streamable-http")`` 自动
带上鉴权。
"""

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from src.mcp.auth import JWTAuthMiddleware


class WatchThisAnimeMCP(FastMCP):
    """FastMCP 子类：在 streamable-http app 上挂载 JWT 鉴权中间件。"""

    def streamable_http_app(self) -> Starlette:
        app = super().streamable_http_app()
        # add_middleware 须在 app 首次处理请求前调用；此处早于 uvicorn 启动，安全。
        app.add_middleware(JWTAuthMiddleware)
        return app


mcp = WatchThisAnimeMCP("WatchThisAnime")
