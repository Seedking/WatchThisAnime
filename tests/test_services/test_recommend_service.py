"""``src.services.recommend_service`` 单测。"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.services import recommend_service, user_service
from src.services.recommend_service import recommend_anime, recent_anime
from src.storage.database import Base
from src.storage.models import (
    Anime,
    AnimeInteraction,
    BangumiRecord,
    TagInteraction,
)


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(user_service, "SessionLocal", test_session)
    monkeypatch.setattr(recommend_service, "SessionLocal", test_session)
    yield test_session
    Base.metadata.drop_all(engine)


def _add_anime(
    session: sessionmaker,
    *,
    title: str,
    tags: list[str],
    score: float,
    source_id: str,
) -> uuid.UUID:
    anime_id = uuid.uuid4()
    with session() as db:
        db.add(Anime(id=anime_id, canonical_title=title))
        db.add(
            BangumiRecord(
                source_id=source_id,
                anime_id=anime_id,
                name_cn=title,
                tags=tags,
                score=score,
            )
        )
        db.commit()
    return anime_id


def test_empty_database_returns_stable_empty_cold_start(
    memory_db: sessionmaker,
) -> None:
    assert recommend_anime("alice") == {"phase": "cold_start", "items": []}


def test_cold_start_returns_explainable_items_in_score_order(
    memory_db: sessionmaker,
) -> None:
    _add_anime(
        memory_db,
        title="高分番",
        tags=["科幻"],
        score=9.2,
        source_id="bgm-high",
    )
    _add_anime(
        memory_db,
        title="低分番",
        tags=["日常"],
        score=6.5,
        source_id="bgm-low",
    )

    payload = recommend_anime("alice")

    assert payload["phase"] == "cold_start"
    assert [item["title"] for item in payload["items"]] == ["高分番", "低分番"]
    assert set(payload["items"][0]) == {
        "anime_id",
        "title",
        "score",
        "reasons",
        "sources",
    }
    assert payload["items"][0]["score"] > payload["items"][1]["score"]
    assert payload["items"][0]["reasons"] == ["来源综合评分 9.2"]
    assert payload["items"][0]["sources"][0]["name"] == "bangumi"


def test_below_threshold_stays_cold_start(memory_db: sessionmaker) -> None:
    first = _add_anime(
        memory_db,
        title="第一部",
        tags=["奇幻"],
        score=8.0,
        source_id="bgm-first",
    )
    second = _add_anime(
        memory_db,
        title="第二部",
        tags=["奇幻"],
        score=8.0,
        source_id="bgm-second",
    )
    with memory_db() as session:
        session.add_all(
            [
                AnimeInteraction(
                    user_id="alice",
                    anime_id=first,
                    action="viewed",
                    rating=9,
                ),
                AnimeInteraction(
                    user_id="alice",
                    anime_id=second,
                    action="viewed",
                    rating=8,
                ),
            ]
        )
        session.commit()

    assert recommend_anime("alice")["phase"] == "cold_start"


def test_personalized_ranking_uses_tag_and_rating_history(
    memory_db: sessionmaker,
) -> None:
    seen_fantasy = _add_anime(
        memory_db,
        title="看过奇幻",
        tags=["奇幻"],
        score=8.0,
        source_id="bgm-seen-fantasy",
    )
    seen_good = _add_anime(
        memory_db,
        title="另一部高分",
        tags=["奇幻"],
        score=8.5,
        source_id="bgm-seen-good",
    )
    seen_bad = _add_anime(
        memory_db,
        title="低分已看",
        tags=["运动"],
        score=9.5,
        source_id="bgm-seen-bad",
    )
    fantasy = _add_anime(
        memory_db,
        title="奇幻候选",
        tags=["奇幻"],
        score=7.5,
        source_id="bgm-fantasy",
    )
    sports = _add_anime(
        memory_db,
        title="运动候选",
        tags=["运动"],
        score=8.0,
        source_id="bgm-sports",
    )
    with memory_db() as session:
        session.add_all(
            [
                AnimeInteraction(
                    user_id="alice",
                    anime_id=seen_fantasy,
                    action="viewed",
                    rating=9,
                ),
                AnimeInteraction(
                    user_id="alice",
                    anime_id=seen_good,
                    action="viewed",
                    rating=9,
                ),
                AnimeInteraction(
                    user_id="alice",
                    anime_id=seen_bad,
                    action="viewed",
                    rating=2,
                ),
                TagInteraction(user_id="alice", tag="奇幻", score=10),
                TagInteraction(user_id="alice", tag="运动", score=2),
            ]
        )
        session.commit()

    payload = recommend_anime("alice")

    assert payload["phase"] == "personalized"
    assert payload["items"][0]["anime_id"] == str(fantasy)
    assert payload["items"][1]["anime_id"] == str(sports)
    returned_ids = {item["anime_id"] for item in payload["items"]}
    assert str(seen_bad) not in returned_ids
    assert str(seen_fantasy) not in returned_ids
    assert str(seen_good) not in returned_ids
    assert "偏好标签：奇幻" in payload["items"][0]["reasons"]


def test_recent_anime_is_stable_and_deduplicates_history(
    memory_db: sessionmaker,
) -> None:
    first = _add_anime(
        memory_db,
        title="较早番",
        tags=["奇幻"],
        score=8.0,
        source_id="bgm-recent-first",
    )
    second = _add_anime(
        memory_db,
        title="最近番",
        tags=["科幻"],
        score=8.5,
        source_id="bgm-recent-second",
    )
    now = datetime(2026, 9, 17, 12, 0, 0)
    with memory_db() as session:
        session.add_all(
            [
                AnimeInteraction(
                    user_id="alice",
                    anime_id=first,
                    action="viewed",
                    rating=7,
                    created_at=now - timedelta(days=1),
                ),
                AnimeInteraction(
                    user_id="alice",
                    anime_id=second,
                    action="wishlisted",
                    rating=None,
                    created_at=now,
                ),
                AnimeInteraction(
                    user_id="alice",
                    anime_id=second,
                    action="viewed",
                    rating=9,
                    created_at=now + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    payload = recent_anime("alice")

    assert [item["anime_id"] for item in payload["items"]] == [
        str(second),
        str(first),
    ]
    assert payload["items"][0]["action"] == "viewed"
    assert payload["items"][0]["rating"] == 9
    assert set(payload["items"][0]) == {
        "anime_id",
        "title",
        "action",
        "rating",
        "created_at",
        "sources",
    }


def test_recent_anime_empty_history_returns_empty_items(
    memory_db: sessionmaker,
) -> None:
    assert recent_anime("alice") == {"items": []}
