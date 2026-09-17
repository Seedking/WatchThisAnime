"""``src.services.interaction_service`` 单测。"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.services import interaction_service, user_service
from src.services.interaction_service import InteractionError, record_interaction
from src.storage.database import Base
from src.storage.models import (
    Anime,
    AnimeInteraction,
    BangumiRecord,
    TagInteraction,
    User,
)


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    """内存 SQLite，并让交互服务与用户服务共用同一个 session factory。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(user_service, "SessionLocal", test_session)
    monkeypatch.setattr(interaction_service, "SessionLocal", test_session)
    yield test_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def anime_id(memory_db: sessionmaker) -> uuid.UUID:
    """创建一个带标签来源记录的番剧。"""
    item_id = uuid.uuid4()
    with memory_db() as session:
        anime = Anime(id=item_id, canonical_title="Test Anime")
        session.add(anime)
        session.add(
            BangumiRecord(
                source_id="bgm-1",
                anime_id=item_id,
                tags=["奇幻", "治愈"],
            )
        )
        session.commit()
    return item_id


def test_record_anime_interaction_creates_user_and_row(
    memory_db: sessionmaker, anime_id: uuid.UUID
) -> None:
    item = record_interaction(
        user_id="alice",
        target_type="anime",
        target_id=str(anime_id),
        action="viewed",
        rating=8,
    )

    assert item["type"] == "anime"
    assert item["anime_id"] == str(anime_id)
    assert item["action"] == "viewed"
    assert item["rating"] == 8
    with memory_db() as session:
        assert session.get(User, "alice") is not None
        interactions = session.query(AnimeInteraction).all()
        assert len(interactions) == 1


def test_record_anime_interaction_keeps_history(
    memory_db: sessionmaker, anime_id: uuid.UUID
) -> None:
    record_interaction("alice", "anime", str(anime_id), rating=7, action="viewed")
    record_interaction("alice", "anime", str(anime_id), rating=None, action="wishlisted")

    with memory_db() as session:
        interactions = session.query(AnimeInteraction).all()
        assert len(interactions) == 2
        assert interactions[1].rating is None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"target_type": "anime", "target_id": "", "action": "viewed"}, "invalid_anime_id"),
        ({"target_type": "anime", "target_id": "   ", "action": "viewed"}, "invalid_anime_id"),
        ({"target_type": "anime", "target_id": 123, "action": "viewed"}, "invalid_anime_id"),
        ({"target_type": "anime", "target_id": "not-uuid", "action": "viewed"}, "invalid_anime_id"),
        (
            {"target_type": "anime", "target_id": str(uuid.uuid4()), "action": "viewed"},
            "anime_not_found",
        ),
        ({"target_type": "anime", "target_id": str(uuid.uuid4()), "action": None}, "invalid_action"),
        ({"target_type": "anime", "target_id": str(uuid.uuid4()), "action": "dropped"}, "invalid_action"),
        (
            {
                "target_type": "anime",
                "target_id": str(uuid.uuid4()),
                "action": "viewed",
                "rating": True,
            },
            "invalid_rating",
        ),
        (
            {"target_type": "anime", "target_id": str(uuid.uuid4()), "action": "viewed", "rating": 0},
            "invalid_rating",
        ),
        (
            {"target_type": "anime", "target_id": str(uuid.uuid4()), "action": "viewed", "rating": 11},
            "invalid_rating",
        ),
        ({"target_type": "unknown", "target_id": "x"}, "invalid_target_type"),
    ],
)
def test_record_anime_interaction_rejects_invalid_input(
    memory_db: sessionmaker,
    kwargs: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(InteractionError) as exc_info:
        record_interaction(user_id="alice", **kwargs)

    assert exc_info.value.code == code


@pytest.mark.parametrize(
    ("action", "rating"),
    [
        ("viewed", None),
        ("wishlisted", 6),
    ],
)
def test_record_anime_interaction_allows_optional_rating_for_valid_action(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
    action: str,
    rating: int | None,
) -> None:
    item = record_interaction(
        "alice",
        "anime",
        str(anime_id),
        rating=rating,
        action=action,
    )

    assert item["action"] == action
    assert item["rating"] == rating


def test_record_tag_interaction_creates_score(
    memory_db: sessionmaker, anime_id: uuid.UUID
) -> None:
    item = record_interaction(
        user_id="alice",
        target_type="tag",
        target_id="奇幻",
        action="viewed",
        rating=9,
    )

    assert item["type"] == "tag"
    assert item["tag"] == "奇幻"
    assert item["score"] == 9
    with memory_db() as session:
        rows = session.query(TagInteraction).all()
        assert len(rows) == 1
        assert rows[0].score == 9


def test_record_tag_interaction_updates_existing_score(
    memory_db: sessionmaker, anime_id: uuid.UUID
) -> None:
    record_interaction("alice", "tag", "奇幻", rating=4, action=None)
    record_interaction("alice", "tag", "奇幻", rating=10, action="wishlisted")

    with memory_db() as session:
        rows = session.query(TagInteraction).all()
        assert len(rows) == 1
        assert rows[0].score == 10


def test_record_tag_interaction_ignores_action(
    memory_db: sessionmaker, anime_id: uuid.UUID
) -> None:
    item = record_interaction(
        "alice",
        "tag",
        "奇幻",
        rating=8,
        action="not-an-anime-action",
    )

    assert item["type"] == "tag"
    assert item["tag"] == "奇幻"
    assert item["score"] == 8


@pytest.mark.parametrize(
    ("target_id", "rating", "code"),
    [
        ("", 8, "invalid_tag"),
        ("   ", 8, "invalid_tag"),
        ("不存在", 8, "tag_not_found"),
        ("奇幻", None, "invalid_score"),
        ("奇幻", True, "invalid_score"),
        ("奇幻", 0, "invalid_score"),
        ("奇幻", 11, "invalid_score"),
    ],
)
def test_record_tag_interaction_rejects_invalid_input(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
    target_id: str,
    rating: int | None,
    code: str,
) -> None:
    with pytest.raises(InteractionError) as exc_info:
        record_interaction("alice", "tag", target_id, rating=rating, action="viewed")

    assert exc_info.value.code == code


@pytest.mark.parametrize("user_id", ["", "   ", "\t\n"])
def test_record_interaction_rejects_blank_user(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
    user_id: str,
) -> None:
    with pytest.raises(InteractionError) as exc_info:
        record_interaction(user_id, "anime", str(anime_id), action="viewed")

    assert exc_info.value.code == "invalid_user"


def test_record_anime_interaction_rolls_back_database_failure(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = memory_db()
    rollback_called = False
    real_rollback = session.rollback

    def fail_commit() -> None:
        raise SQLAlchemyError("simulated database failure")

    def track_rollback() -> None:
        nonlocal rollback_called
        rollback_called = True
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)
    monkeypatch.setattr(interaction_service, "SessionLocal", lambda: session)

    with pytest.raises(InteractionError) as exc_info:
        record_interaction("alice", "anime", str(anime_id), action="viewed")

    assert exc_info.value.code == "database_error"
    assert rollback_called is True
    with memory_db() as verification_session:
        assert verification_session.query(AnimeInteraction).count() == 0


def test_record_tag_interaction_rolls_back_database_failure(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_interaction("alice", "tag", "奇幻", rating=5, action=None)
    session = memory_db()
    rollback_called = False
    real_rollback = session.rollback

    def fail_commit() -> None:
        raise SQLAlchemyError("simulated database failure")

    def track_rollback() -> None:
        nonlocal rollback_called
        rollback_called = True
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)
    monkeypatch.setattr(interaction_service, "SessionLocal", lambda: session)

    with pytest.raises(InteractionError) as exc_info:
        record_interaction("alice", "tag", "奇幻", rating=10, action="viewed")

    assert exc_info.value.code == "database_error"
    assert rollback_called is True
    with memory_db() as verification_session:
        assert verification_session.query(TagInteraction).one().score == 5
