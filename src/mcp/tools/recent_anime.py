"""recent_anime 工具：最近动漫推荐。"""

from src.mcp.server import mcp


@mcp.tool()
def recent_anime() -> str:
    """最近动漫推荐工具。

    返回最近番剧的推荐列表。``user_id`` 从 JWT 上下文取，不作为参数暴露。
    """
    return ""
