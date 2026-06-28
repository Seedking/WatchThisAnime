"""``src.services.user_service`` 单测。

覆盖 ``ensure_user`` 的首次创建、幂等与空串校验。DB 用内存 SQLite
（``StaticPool``）隔离，不触碰真实 ``watchthisanime.db``。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.services import user_service
from src.services.user_service import UserError, ensure_user
from src.storage.database import Base
from src.storage.models import User


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    """内存 SQLite + 建表，并把 ``user_service.SessionLocal`` 指向它，隔离真实库。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(user_service, "SessionLocal", test_session)
    yield test_session
    Base.metadata.drop_all(engine)


def test_ensure_user_creates_on_first_access(memory_db: sessionmaker) -> None:
    ensure_user("alice")
    with memory_db() as session:
        user = session.get(User, "alice")
        assert user is not None
        assert user.id == "alice"


def test_ensure_user_is_idempotent(memory_db: sessionmaker) -> None:
    ensure_user("alice")
    ensure_user("alice")
    with memory_db() as session:
        users = session.query(User).filter_by(id="alice").all()
        assert len(users) == 1


def test_ensure_user_empty_raises(memory_db: sessionmaker) -> None:
    with pytest.raises(UserError):
        ensure_user("")
