"""MCP tool 层测试。"""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.mcp.tools.record_user_interaction import record_user_interaction
from src.mcp.tools import search_anime as search_tool
from src.mcp.tools.search_anime import search_anime
from src.services import interaction_service, user_service
from src.services.search_service import SearchError
from src.storage.database import Base
from src.storage.models import Anime, BangumiRecord, TagInteraction


@pytest.fixture
def memory_db(monkeypatch: pytest.MonkeyPatch):
    """内存 SQLite，并让 tool 调用链路使用同一个临时库。"""
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
    item_id = uuid.uuid4()
    with memory_db() as session:
        session.add(Anime(id=item_id, canonical_title="Tool Anime"))
        session.add(
            BangumiRecord(
                source_id="bgm-tool",
                anime_id=item_id,
                tags=["科幻"],
            )
        )
        session.commit()
    return item_id


def test_record_user_interaction_tool_returns_success_json_for_anime(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
) -> None:
    payload = json.loads(
        record_user_interaction(
            user_id="alice",
            target_type="anime",
            target_id=str(anime_id),
            action="viewed",
            rating=8,
        )
    )

    assert payload["ok"] is True
    assert payload["item"]["type"] == "anime"
    assert payload["item"]["anime_id"] == str(anime_id)


def test_record_user_interaction_tool_returns_success_json_for_tag(
    memory_db: sessionmaker,
    anime_id: uuid.UUID,
) -> None:
    payload = json.loads(
        record_user_interaction(
            user_id="alice",
            target_type="tag",
            target_id="科幻",
            action="viewed",
            rating=9,
        )
    )

    assert payload["ok"] is True
    assert payload["item"]["type"] == "tag"
    assert payload["item"]["score"] == 9
    with memory_db() as session:
        assert session.query(TagInteraction).one().tag == "科幻"


def test_record_user_interaction_tool_returns_error_json(
    memory_db: sessionmaker,
) -> None:
    payload = json.loads(
        record_user_interaction(
            user_id="alice",
            target_type="anime",
            target_id="not-uuid",
            action="viewed",
            rating=8,
        )
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_anime_id"


def test_search_anime_tool_returns_compact_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(anime_name: str, anime_tag: list[str] | None = None) -> dict:
        assert anime_name == "Cowboy Bebop"
        assert anime_tag == ["科幻"]
        return {
            "ok": True,
            "query": {"anime_name": anime_name, "anime_tag": anime_tag},
            "items": [
                {
                    "title": "星际牛仔",
                    "tags": ["科幻"],
                    "summary": "summary",
                    "url": "https://bgm.tv/subject/253",
                    "ratings": {
                        "bangumi": 9.1,
                        "jikan": 8.75,
                        "moegirl": None,
                    },
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr(search_tool, "search_anime_service", fake_search)

    payload = json.loads(search_anime("Cowboy Bebop", ["科幻"]))

    assert payload["ok"] is True
    item = payload["items"][0]
    assert set(item) == {"title", "tags", "summary", "url", "ratings"}
    assert item["ratings"]["moegirl"] is None


def test_search_anime_tool_returns_error_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(anime_name: str, anime_tag: list[str] | None = None) -> dict:
        raise SearchError("invalid_query", "anime_name 不能为空")

    monkeypatch.setattr(search_tool, "search_anime_service", fake_search)

    payload = json.loads(search_anime("", None))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_query"
