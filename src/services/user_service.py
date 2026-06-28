"""用户服务：按外部传入的 ``user_id`` 确保用户记录存在。

鉴权移除后，用户身份由调用方在调用工具时以字符串参数显式传入；用户管理交由外部系统
完成，服务端只在首次见到某 ``user_id`` 时在 ``user`` 表创建记录，后续直接复用。
"""

from src.storage.database import SessionLocal
from src.storage.models import User


class UserError(ValueError):
    """``user_id`` 非法（空串等）。"""


def ensure_user(user_id: str) -> None:
    """确保 ``user`` 表存在指定 ``user_id`` 的记录：存在则跳过，不存在则新建。

    Args:
        user_id: 外部传入的字符串用户标识，作为 ``user.id`` 主键。

    Raises:
        UserError: ``user_id`` 为空串。
    """
    if not user_id:
        raise UserError("user_id 不能为空")

    with SessionLocal() as session:
        if session.get(User, user_id) is None:
            session.add(User(id=user_id))
        session.commit()
