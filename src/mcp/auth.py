"""JWT 鉴权：解析 Bearer token → user_id 并注入请求上下文。

streamable-http 连接建立时，``JWTAuthMiddleware`` 读取 ``Authorization: Bearer <JWT>``
头，解码 JWT（仅解码、不校验签名，签名校验由上游网关/反代负责）取 ``sub`` 声明作为
``user.id``（UUID），在 ``user`` 表中 upsert，并将 ``user_id`` 写入
``current_user_id`` ContextVar，供 tool / service 层通过 ``get_current_user_id()``
取用。

- ``user.username`` 取 claims 中的可读名（``name`` / ``preferred_username``），缺失回落 ``sub``；
- 不把整个 JWT 字符串作主键（JWT 带 ``exp`` 会刷新，作主键会导致身份漂移、历史断链）；
- 本地调试（``DANGEROUSLY_OMIT_AUTH=true``，见 ``pixi run inspect``）跳过解析直接放行。
"""

import contextvars
import os
import uuid
from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.storage.database import SessionLocal
from src.storage.models import User

# 请求级 user_id 载体；BaseHTTPMiddleware 下游任务继承当前 context 副本，故 tool 执行可见。
current_user_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


class AuthError(Exception):
    """鉴权失败基类（token 缺失 / 格式错 / sub 缺失 / 解析失败）。"""


def decode_jwt(token: str) -> dict[str, Any]:
    """解码 JWT，不校验签名（信任上游网关已校验）。

    保留 ``exp`` 默认校验作为廉价安全网：若 token 显式带 ``exp`` 且已过期，抛 ``AuthError``。

    Args:
        token: JWT 字符串。

    Returns:
        JWT claims 字典。

    Raises:
        AuthError: token 结构非法或已过期。
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise AuthError(f"JWT 解码失败: {exc}") from exc


def extract_user(token: str) -> tuple[uuid.UUID, str]:
    """从 JWT 提取 user_id（``sub``）与 username。

    Args:
        token: JWT 字符串。

    Returns:
        ``(user_id, username)``。``username`` 取 ``name`` / ``preferred_username``，
        缺失则回落 ``sub`` 字符串。

    Raises:
        AuthError: ``sub`` 缺失或非合法 UUID。
    """
    claims = decode_jwt(token)
    sub = claims.get("sub")
    if not sub:
        raise AuthError("JWT 缺少 sub 声明")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AuthError(f"sub 不是合法 UUID: {sub!r}") from exc
    username = claims.get("name") or claims.get("preferred_username") or str(sub)
    return user_id, username


def upsert_user(user_id: uuid.UUID, username: str) -> None:
    """按主键 ``id`` upsert ``user``：存在则更新 username，否则新建。

    首次见到该 ``user_id`` 时创建记录，后续请求仅刷新 ``username`` / ``updated_at``。
    """
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id, username=username))
        else:
            user.username = username
        session.commit()


def get_current_user_id() -> uuid.UUID:
    """从请求上下文取当前 user_id。

    供 tool / service 层调用。无可用 user_id（如未携带合法 Bearer token）时抛 ``AuthError``。

    Raises:
        AuthError: 上下文中无 user_id。
    """
    user_id = current_user_id.get()
    if user_id is None:
        raise AuthError("上下文中无 user_id（缺少合法 Authorization: Bearer <JWT>）")
    return user_id


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """读取 ``Authorization: Bearer <JWT>`` 头，解码并注入 ``current_user_id``。

    - ``DANGEROUSLY_OMIT_AUTH`` 为真时跳过解析直接放行（仅限本地调试）；
    - 无 Bearer token 时放行（部分工具如 ``search_anime`` 无需鉴权），ContextVar 保持
      ``None``，由需要 user_id 的工具调用 ``get_current_user_id()`` 时报错；
    - 携带 Bearer 但解析失败时返回 401。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Any,
    ) -> Response:
        if os.environ.get("DANGEROUSLY_OMIT_AUTH"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer ") :]
            try:
                user_id, username = extract_user(token)
            except AuthError as exc:
                return JSONResponse(
                    {"error": str(exc)}, status_code=401
                )
            upsert_user(user_id, username)
            token_ctx = current_user_id.set(user_id)
            try:
                return await call_next(request)
            finally:
                current_user_id.reset(token_ctx)

        return await call_next(request)
