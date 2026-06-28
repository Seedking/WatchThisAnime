"""``src.mcp.auth`` 单测。

覆盖 JWT 解码、用户身份解析（含 username 回落）、upsert user、``JWTAuthMiddleware``
（带/不带 token、错误 token、``DANGEROUSLY_OMIT_AUTH`` 旁路）以及 ``get_current_user_id``。
DB 用内存 SQLite（``StaticPool``）隔离，不触碰真实 ``watchthisanime.db``。
"""

import uuid

import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.mcp import auth
from src.mcp.auth import (
    AuthError,
    JWTAuthMiddleware,
    current_user_id,
    decode_jwt,
    extract_user,
    get_current_user_id,
)
from src.storage.database import Base
from src.storage.models import User


def _make_jwt(claims: dict) -> str:
    """用任意密钥签发 HS256 JWT；解码时不校验签名，密钥内容无关。"""
    return jwt.encode(claims, "test-secret", algorithm="HS256")


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    """内存 SQLite + 建表，并把 ``auth.SessionLocal`` 指向它，隔离真实库。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(auth, "SessionLocal", test_session)
    yield test_session
    Base.metadata.drop_all(engine)


def test_decode_jwt_returns_claims() -> None:
    token = _make_jwt({"sub": "abc", "name": "alice"})
    assert decode_jwt(token)["sub"] == "abc"


def test_decode_jwt_malformed_raises() -> None:
    with pytest.raises(AuthError):
        decode_jwt("not.a.jwt")


def test_extract_user_prefers_name() -> None:
    uid = uuid.uuid4()
    token = _make_jwt({"sub": str(uid), "name": "alice"})
    user_id, username = extract_user(token)
    assert user_id == uid
    assert username == "alice"


def test_extract_user_falls_back_to_preferred_username() -> None:
    uid = uuid.uuid4()
    token = _make_jwt({"sub": str(uid), "preferred_username": "bob"})
    user_id, username = extract_user(token)
    assert user_id == uid
    assert username == "bob"


def test_extract_user_falls_back_to_sub() -> None:
    uid = uuid.uuid4()
    token = _make_jwt({"sub": str(uid)})
    user_id, username = extract_user(token)
    assert user_id == uid
    assert username == str(uid)


def test_extract_user_missing_sub_raises() -> None:
    token = _make_jwt({"name": "no-sub"})
    with pytest.raises(AuthError):
        extract_user(token)


def test_extract_user_invalid_uuid_sub_raises() -> None:
    token = _make_jwt({"sub": "not-a-uuid"})
    with pytest.raises(AuthError):
        extract_user(token)


def test_get_current_user_id_requires_context() -> None:
    # ContextVar 默认 None。
    assert current_user_id.get() is None
    with pytest.raises(AuthError):
        get_current_user_id()


def test_get_current_user_id_returns_set_value() -> None:
    uid = uuid.uuid4()
    token_ctx = current_user_id.set(uid)
    try:
        assert get_current_user_id() == uid
    finally:
        current_user_id.reset(token_ctx)


def _whoami(request: Request) -> JSONResponse:
    uid = current_user_id.get()
    return JSONResponse({"user_id": str(uid) if uid else None})


def _build_client() -> TestClient:
    app = Starlette(routes=[Route("/", _whoami)])
    app.add_middleware(JWTAuthMiddleware)
    return TestClient(app)


def test_middleware_valid_bearer_sets_context_and_upserts(
    memory_db: sessionmaker,
) -> None:
    uid = uuid.uuid4()
    token = _make_jwt({"sub": str(uid), "name": "alice"})
    client = _build_client()

    resp = client.get("/", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(uid)

    with memory_db() as session:
        user = session.get(User, uid)
        assert user is not None
        assert user.username == "alice"


def test_middleware_invalid_bearer_returns_401(memory_db: sessionmaker) -> None:
    client = _build_client()
    resp = client.get("/", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_middleware_no_bearer_passes_through(memory_db: sessionmaker) -> None:
    client = _build_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["user_id"] is None


def test_middleware_dangerous_omit_auth_bypasses(
    memory_db: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DANGEROUSLY_OMIT_AUTH", "1")
    client = _build_client()
    # 即便 token 非法也应被旁路放行。
    resp = client.get("/", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] is None
