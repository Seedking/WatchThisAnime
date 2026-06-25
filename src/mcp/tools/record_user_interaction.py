"""record_user_interaction 工具：用户行为反馈。"""

from src.mcp.server import mcp


@mcp.tool()
def record_user_interaction(anime_id: str, action: str, rating: int | None = None) -> str:
    """记录用户对番剧的行为与评分。

    ``user_id`` 从 JWT 上下文取。``anime_id`` 为 ``anime`` 表 UUID 主键；
    ``action ∈ {viewed, wishlisted}``；``rating`` 为 1-10 整数可空。
    写入 ``anime_interactions``，为后续个性化推荐积累信号。
    """
    return ""
