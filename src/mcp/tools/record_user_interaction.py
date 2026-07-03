"""record_user_interaction 工具：用户行为反馈。"""

import json
from typing import Literal

from src.mcp.server import mcp
from src.services.interaction_service import InteractionError, record_interaction


@mcp.tool()
def record_user_interaction(
    user_id: str,
    target_type: Literal["anime", "tag"],
    target_id: str,
    rating: int | None = None,
    action: Literal["viewed", "wishlisted"] | None = None,
) -> str:
    """记录用户对番剧或标签的反馈。

    ``user_id`` 由调用方传入（字符串用户标识），首次访问时创建用户记录。
    ``target_type`` 为 ``anime`` 时，``target_id`` 是 ``anime`` 表 UUID 主键，
    ``action`` 必须是 ``viewed`` 或 ``wishlisted``，``rating`` 为 1-10 整数可空。
    ``target_type`` 为 ``tag`` 时，``target_id`` 是标签名，``rating`` 必须是 1-10 整数，
    ``action`` 会被忽略。
    """
    try:
        item = record_interaction(user_id, target_type, target_id, rating, action)
    except InteractionError as exc:
        return json.dumps(
            {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, "item": item}, ensure_ascii=False)
