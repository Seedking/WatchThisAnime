"""Search service tests."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.services import search_service
from src.sources.bangumi_client import (
    BangumiCollection,
    BangumiImages,
    BangumiRating,
    BangumiSubject,
    BangumiTag,
)
from src.sources.jikan_client import (
    JikanAired,
    JikanAnime,
    JikanBroadcast,
    JikanEntity,
    JikanTrailer,
)
from src.sources.moegirl_client import MoegirlPage, MoegirlPageLatest, MoegirlSearchPage
from src.storage.database import Base
from src.storage.models import Anime, BangumiRecord, JikanRecord, MoegirlRecord


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(search_service, "SessionLocal", test_session)
    yield test_session
    Base.metadata.drop_all(engine)


class FakeBangumiClient:
    def __init__(self, subjects: list[BangumiSubject]) -> None:
        self.subjects = subjects

    async def search_subjects(self, **kwargs: object) -> object:
        return SimpleNamespace(data=self.subjects)

    async def get_subject(self, subject_id: int) -> BangumiSubject:
        return self.subjects[0]


class FakeJikanClient:
    def __init__(self, animes: list[JikanAnime]) -> None:
        self.animes = animes

    async def search_anime(self, **kwargs: object) -> object:
        return SimpleNamespace(data=self.animes)

    async def get_anime(self, anime_id: int) -> object:
        return SimpleNamespace(data=self.animes[0] if self.animes else None)


class FakeMoegirlClient:
    def __init__(self, pages: list[MoegirlPage]) -> None:
        self.pages = pages

    async def search(self, **kwargs: object) -> object:
        pages = [
            MoegirlSearchPage(
                id=page.id,
                key=page.key,
                title=page.title,
                excerpt=None,
                matched_title=None,
                description=None,
            )
            for page in self.pages
        ]
        return SimpleNamespace(pages=pages)

    async def get_page(self, *, key: str) -> MoegirlPage:
        return self.pages[0]


def test_search_merges_sources_upserts_and_returns_compact_item(
    memory_db: sessionmaker,
) -> None:
    payload = asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            bangumi_client=FakeBangumiClient([_bangumi_subject()]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([_moegirl_page()]),
        )
    )

    assert payload["ok"] is True
    assert payload["warnings"] == []
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item == {
        "title": "星际牛仔",
        "tags": ["科幻", "TV", "Action", "Seinen", "测试分类"],
        "summary": "Bangumi summary",
        "url": "https://bgm.tv/subject/253",
        "ratings": {"bangumi": 9.1, "jikan": 8.75, "moegirl": None},
    }

    with memory_db() as session:
        assert session.query(Anime).count() == 1
        assert session.query(BangumiRecord).one().source_id == "253"
        assert session.query(JikanRecord).one().source_id == "1"
        assert session.query(MoegirlRecord).one().source_id == "651317"

    second = asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            bangumi_client=FakeBangumiClient([_bangumi_subject()]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([_moegirl_page()]),
        )
    )
    assert len(second["items"]) == 1
    with memory_db() as session:
        assert session.query(Anime).count() == 1
        assert session.query(BangumiRecord).count() == 1
        assert session.query(JikanRecord).count() == 1
        assert session.query(MoegirlRecord).count() == 1


def test_search_filters_tags_after_merge(memory_db: sessionmaker) -> None:
    payload = asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            anime_tag=["Action", "科幻"],
            bangumi_client=FakeBangumiClient([_bangumi_subject()]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([]),
        )
    )

    assert len(payload["items"]) == 1

    empty = asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            anime_tag=["不存在"],
            bangumi_client=FakeBangumiClient([_bangumi_subject()]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([]),
        )
    )

    assert empty["items"] == []


def test_jikan_only_result_keeps_empty_summary_and_url(
    memory_db: sessionmaker,
) -> None:
    payload = asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            bangumi_client=FakeBangumiClient([]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([]),
        )
    )

    item = payload["items"][0]
    assert item["title"] == "Cowboy Bebop"
    assert item["summary"] == ""
    assert item["url"] == ""
    assert item["ratings"] == {"bangumi": None, "jikan": 8.75, "moegirl": None}


def test_existing_source_id_reuses_anime(memory_db: sessionmaker) -> None:
    existing_id = uuid.uuid4()
    with memory_db() as session:
        session.add(Anime(id=existing_id, canonical_title="Existing"))
        session.add(BangumiRecord(source_id="253", anime_id=existing_id))
        session.commit()

    asyncio.run(
        search_service.search_anime_async(
            "Cowboy Bebop",
            bangumi_client=FakeBangumiClient([_bangumi_subject()]),
            jikan_client=FakeJikanClient([_jikan_anime()]),
            moegirl_client=FakeMoegirlClient([]),
        )
    )

    with memory_db() as session:
        assert session.query(Anime).count() == 1
        assert session.query(JikanRecord).one().anime_id == existing_id


def _bangumi_subject() -> BangumiSubject:
    return BangumiSubject(
        id=253,
        type=2,
        name="Cowboy Bebop",
        name_cn="星际牛仔",
        summary="Bangumi summary",
        date="1998-10-23",
        platform="TV",
        volumes=0,
        eps=26,
        total_episodes=26,
        images=BangumiImages(
            large="https://example.test/cowboy.jpg",
            common=None,
            medium=None,
            small=None,
            grid=None,
        ),
        rating=BangumiRating(score=9.1, total=100, count={}),
        rank=4,
        collection=BangumiCollection(
            wish=1,
            collect=2,
            doing=3,
            on_hold=4,
            dropped=5,
        ),
        tags=[BangumiTag(name="科幻", count=100)],
        meta_tags=["TV"],
    )


def _jikan_anime() -> JikanAnime:
    entity = JikanEntity(mal_id=1, type="anime", name="Action", url=None)
    demographic = JikanEntity(mal_id=42, type="anime", name="Seinen", url=None)
    return JikanAnime(
        mal_id=1,
        url="https://myanimelist.net/anime/1/Cowboy_Bebop",
        trailer=JikanTrailer(youtube_id=None, url=None, embed_url=None),
        approved=True,
        titles=[],
        title="Cowboy Bebop",
        title_english="Cowboy Bebop",
        title_japanese="カウボーイビバップ",
        title_synonyms=["星际牛仔"],
        type="TV",
        source="Original",
        episodes=26,
        status="Finished Airing",
        airing=False,
        aired=JikanAired(from_=None, to=None, prop=None),
        duration=None,
        rating=None,
        score=8.75,
        scored_by=100,
        rank=183,
        popularity=1,
        members=1000,
        favorites=100,
        synopsis="Jikan summary",
        background=None,
        season="spring",
        year=1998,
        broadcast=JikanBroadcast(day=None, time=None, timezone=None, string=None),
        producers=[],
        licensors=[],
        studios=[],
        genres=[entity],
        explicit_genres=[],
        themes=[],
        demographics=[demographic],
    )


def _moegirl_page() -> MoegirlPage:
    return MoegirlPage(
        id=651317,
        key="Cowboy_Bebop",
        title="Cowboy Bebop",
        content_model="wikitext",
        latest=MoegirlPageLatest(id=8564985, timestamp="2026-07-03T12:33:44Z"),
        license=None,
        html_url=None,
        source=(
            "{{动画信息|标题 = Cowboy Bebop|译名 = 星际牛仔}}\n\n"
            "Moegirl summary.\n\n[[Category:测试分类]]"
        ),
        url="https://zh.moegirl.org.cn/index.php?curid=651317",
    )
