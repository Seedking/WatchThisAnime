"""recent_anime 工具：最近动漫推荐。"""

from src.mcp.server import mcp
from src.services.user_service import UserError, ensure_user


@mcp.tool()
def recent_anime(user_id: str) -> str:
    """最近动漫推荐工具。

    返回最近番剧的推荐列表。``user_id`` 由调用方传入（字符串用户标识），
    首次访问时创建用户记录。
    """
    try:
        ensure_user(user_id)
    except UserError as exc:
        return f"错误：{exc}"
    return ""
