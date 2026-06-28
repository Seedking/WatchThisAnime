"""工具统一注册点。

导入各工具模块以触发 ``@mcp.tool()`` 装饰器完成注册。
"""

from src.mcp.tools import recommend_anime, record_user_interaction, recent_anime, search_anime  # noqa: F401
