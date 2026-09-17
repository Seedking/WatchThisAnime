"""recent_anime 工具：最近动漫推荐。"""

import json

from src.mcp.server import mcp
from src.services.recommend_service import (
    RecommendationError,
    recent_anime as recent_anime_service,
)


@mcp.tool()
def recent_anime(user_id: str) -> str:
    """最近动漫推荐工具。

    返回最近番剧的推荐列表。``user_id`` 由调用方传入（字符串用户标识），
    首次访问时创建用户记录。
    """
    try:
        payload = recent_anime_service(user_id)
    except RecommendationError as exc:
        return json.dumps(
            {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
