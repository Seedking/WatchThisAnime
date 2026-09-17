"""recommend_anime 工具：聚合推荐。"""

import json

from src.mcp.server import mcp
from src.services.recommend_service import (
    RecommendationError,
    recommend_anime as recommend_anime_service,
)


@mcp.tool()
def recommend_anime(user_id: str) -> str:
    """聚合推荐工具。

    按用户交互历史量自动选择冷启动或个性化阶段，返回聚合推荐列表。
    ``user_id`` 由调用方传入（字符串用户标识），首次访问时创建用户记录。
    """
    try:
        payload = recommend_anime_service(user_id)
    except RecommendationError as exc:
        return json.dumps(
            {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
