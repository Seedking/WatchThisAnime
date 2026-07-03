"""ORM 模型约束测试。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.storage.database import Base
from src.storage.models import TagInteraction, User


@pytest.fixture
def memory_db():
    """内存 SQLite + 建表。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    yield test_session
    Base.metadata.drop_all(engine)


def test_metadata_create_all_builds_schema(memory_db: sessionmaker) -> None:
    with memory_db() as session:
        session.add(User(id="alice"))
        session.commit()

    with memory_db() as session:
        assert session.get(User, "alice") is not None


def test_tag_interaction_user_tag_is_unique(memory_db: sessionmaker) -> None:
    with memory_db() as session:
        session.add(User(id="alice"))
        session.add(TagInteraction(user_id="alice", tag="奇幻", score=8))
        session.add(TagInteraction(user_id="alice", tag="奇幻", score=9))

        with pytest.raises(IntegrityError):
            session.commit()


def test_tag_interaction_same_tag_allows_different_users(memory_db: sessionmaker) -> None:
    with memory_db() as session:
        session.add_all([User(id="alice"), User(id="bob")])
        session.add(TagInteraction(user_id="alice", tag="奇幻", score=8))
        session.add(TagInteraction(user_id="bob", tag="奇幻", score=9))
        session.commit()

        rows = session.query(TagInteraction).all()
        assert len(rows) == 2


@pytest.mark.parametrize("score", [0, 11])
def test_tag_interaction_score_check_constraint(
    memory_db: sessionmaker, score: int
) -> None:
    with memory_db() as session:
        session.add(User(id="alice"))
        session.add(TagInteraction(user_id="alice", tag="奇幻", score=score))

        with pytest.raises(IntegrityError):
            session.commit()
