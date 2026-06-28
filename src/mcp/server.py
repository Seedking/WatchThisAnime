"""MCP 交互层：FastMCP 实例。

用户身份不再由服务端鉴权层解析，而是由调用方在调用工具时以 ``user_id`` 字符串参数
显式传入（见各 tool 签名与 ``services.user_service.ensure_user``）。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WatchThisAnime")
