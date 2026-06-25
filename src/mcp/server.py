"""MCP 交互层：FastMCP 实例与鉴权中间件。

当前阶段仅创建 FastMCP 实例。JWT 鉴权中间件（解析 Bearer token → user_id）
与 ``auth.py`` 待后续阶段实现。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WatchThisAnime")

# TODO: 接入 JWT 鉴权中间件（Authorization: Bearer <JWT> → user_id），见 src/mcp/auth.py
