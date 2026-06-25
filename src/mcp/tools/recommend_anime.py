"""recommend_anime 工具：聚合推荐。"""

from src.mcp.server import mcp


@mcp.tool()
def recommend_anime() -> str:
    """聚合推荐工具。

    按用户交互历史量自动选择冷启动或个性化阶段，返回聚合推荐列表。
    ``user_id`` 从 JWT 上下文取，不作为参数暴露。
    """
    return ""
