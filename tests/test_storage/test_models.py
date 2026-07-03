"""ORM 模型约束测试。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.storage.database import Base
from src.storage.models import (
    Anime,
    BangumiRecord,
    JikanRecord,
    MoegirlRecord,
    TagInteraction,
    User,
)


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


def test_anime_model_keeps_only_canonical_title(memory_db: sessionmaker) -> None:
    with memory_db() as session:
        anime = Anime(canonical_title="Cowboy Bebop")
        session.add(anime)
        session.commit()

        assert anime.canonical_title == "Cowboy Bebop"
        assert not hasattr(anime, "title_jp")
        assert not hasattr(anime, "title_zh")
        assert not hasattr(anime, "airing_date")
        assert not hasattr(anime, "season")


def test_source_models_have_platform_specific_fields(memory_db: sessionmaker) -> None:
    with memory_db() as session:
        anime = Anime(canonical_title="Cowboy Bebop")
        session.add(anime)
        session.flush()
        session.add(
            BangumiRecord(
                source_id="253",
                anime_id=anime.id,
                name="カウボーイビバップ",
                name_cn="星际牛仔",
                summary="Bangumi summary",
                air_date="1998-10-23",
                platform="TV",
                rank=4,
                score=9.1,
                total_episodes=26,
            )
        )
        session.add(
            JikanRecord(
                source_id="1",
                anime_id=anime.id,
                title="Cowboy Bebop",
                title_japanese="カウボーイビバップ",
                year=1998,
                season="spring",
                media_type="TV",
                episodes=26,
                rank=183,
                score=8.75,
            )
        )
        session.add(
            MoegirlRecord(
                source_id="651317",
                anime_id=anime.id,
                page_id=651317,
                page_key="尼古喵喵",
                title="尼古喵喵",
                latest_revision_id=8564985,
                content_model="wikitext",
            )
        )
        session.commit()

        assert session.query(BangumiRecord).one().name_cn == "星际牛仔"
        assert session.query(JikanRecord).one().year == 1998
        assert session.query(MoegirlRecord).one().page_key == "尼古喵喵"


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
