"""recommend_anime 工具：聚合推荐。"""

from src.mcp.server import mcp
from src.services.user_service import UserError, ensure_user


@mcp.tool()
def recommend_anime(user_id: str) -> str:
    """聚合推荐工具。

    按用户交互历史量自动选择冷启动或个性化阶段，返回聚合推荐列表。
    ``user_id`` 由调用方传入（字符串用户标识），首次访问时创建用户记录。
    """
    try:
        ensure_user(user_id)
    except UserError as exc:
        return f"错误：{exc}"
    return ""
