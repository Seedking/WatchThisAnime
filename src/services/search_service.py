"""Anime search service.

The service searches three sources, fetches source details, stores source records
by their platform ids, merges likely same-anime records, and returns the compact
shape required by the MCP tool.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.sources.bangumi_client import BangumiClient, BangumiSubject
from src.sources.jikan_client import JikanAnime, JikanClient
from src.sources.moegirl_client import MoegirlClient, MoegirlPage, MoegirlSearchPage
from src.storage.database import SessionLocal
from src.storage.models import Anime, BangumiRecord, JikanRecord, MoegirlRecord

SourceName = Literal["bangumi", "jikan", "moegirl"]

DEFAULT_SOURCE_LIMIT = 5


class SearchError(ValueError):
    """Search request validation failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class SourceAnime:
    source: SourceName
    source_id: str
    title: str
    titles: list[str]
    year: int | None
    summary: str
    score: float | None
    tags: list[str]
    url: str
    cover: str | None
    raw: dict[str, Any]
    existing_anime_id: uuid.UUID | None = None


@dataclass
class AnimeGroup:
    items: list[SourceAnime]
    anime_id: uuid.UUID | None = None
    local_title: str | None = None


def search_anime(
    anime_name: str,
    anime_tag: list[str] | None = None,
    *,
    limit: int = DEFAULT_SOURCE_LIMIT,
) -> dict[str, Any]:
    """Synchronous wrapper used by MCP tools."""
    return asyncio.run(search_anime_async(anime_name, anime_tag, limit=limit))


async def search_anime_async(
    anime_name: str,
    anime_tag: list[str] | None = None,
    *,
    limit: int = DEFAULT_SOURCE_LIMIT,
    bangumi_client: Any | None = None,
    jikan_client: Any | None = None,
    moegirl_client: Any | None = None,
) -> dict[str, Any]:
    """Search all sources, upsert records, and return compact results."""
    query = anime_name.strip() if isinstance(anime_name, str) else ""
    if not query:
        raise SearchError("invalid_query", "anime_name 不能为空")

    requested_tags = _normalize_requested_tags(anime_tag)
    local_groups = _search_local(query, requested_tags, limit)
    if local_groups:
        return _build_response(query, requested_tags, local_groups, [])

    own_clients: list[Any] = []
    if bangumi_client is None:
        bangumi_client = BangumiClient()
        own_clients.append(bangumi_client)
    if jikan_client is None:
        jikan_client = JikanClient()
        own_clients.append(jikan_client)
    if moegirl_client is None:
        moegirl_client = MoegirlClient()
        own_clients.append(moegirl_client)

    try:
        source_results = await asyncio.gather(
            _search_bangumi(bangumi_client, query, limit),
            _search_jikan(jikan_client, query, limit),
            _search_moegirl(moegirl_client, query, limit),
            return_exceptions=True,
        )
    finally:
        for client in own_clients:
            await client.aclose()

    warnings: list[str] = []
    source_items: list[SourceAnime] = []
    for source_name, result in zip(
        ("bangumi", "jikan", "moegirl"),
        source_results,
        strict=True,
    ):
        if isinstance(result, Exception):
            warnings.append(f"{source_name} 搜索失败")
        else:
            source_items.extend(result)

    if not source_items:
        return _build_response(query, requested_tags, [], warnings)

    with SessionLocal() as session:
        for item in source_items:
            item.existing_anime_id = _find_existing_anime_id(session, item)

        groups = _group_source_items(source_items, warnings)
        _upsert_groups(session, groups, warnings)
        session.commit()

    visible_groups = [
        group for group in groups if _matches_tags(group, requested_tags)
    ]
    return _build_response(query, requested_tags, visible_groups, warnings)


def _search_local(
    query: str,
    requested_tags: list[str],
    limit: int,
) -> list[AnimeGroup]:
    """Return matching local groups without contacting external sources."""
    if limit <= 0:
        return []
    with SessionLocal() as session:
        animes = session.scalars(
            select(Anime).options(
                selectinload(Anime.bangumi_records),
                selectinload(Anime.jikan_records),
                selectinload(Anime.moegirl_records),
            )
        ).all()
        groups: list[AnimeGroup] = []
        for anime in animes:
            group = _local_group(anime)
            if not _matches_local_name(group, query):
                continue
            if not _matches_tags(group, requested_tags):
                continue
            groups.append(group)
            if len(groups) >= limit:
                break
        return groups


def _local_group(anime: Anime) -> AnimeGroup:
    group = AnimeGroup(
        items=[],
        anime_id=anime.id,
        local_title=anime.canonical_title,
    )
    for record in anime.bangumi_records:
        group.items.append(_source_from_local_bangumi(record, anime))
    for record in anime.jikan_records:
        group.items.append(_source_from_local_jikan(record, anime))
    for record in anime.moegirl_records:
        group.items.append(_source_from_local_moegirl(record, anime))
    return group


def _source_from_local_bangumi(
    record: BangumiRecord,
    anime: Anime,
) -> SourceAnime:
    return SourceAnime(
        source="bangumi",
        source_id=record.source_id,
        title=record.name_cn or record.name or anime.canonical_title or "",
        titles=_dedupe([record.name, record.name_cn, anime.canonical_title]),
        year=_year_from_text(record.air_date),
        summary=record.summary or "",
        score=record.score,
        tags=_dedupe(record.tags or []),
        url=record.url or "",
        cover=record.cover,
        raw=record.raw or {},
        existing_anime_id=anime.id,
    )


def _source_from_local_jikan(
    record: JikanRecord,
    anime: Anime,
) -> SourceAnime:
    return SourceAnime(
        source="jikan",
        source_id=record.source_id,
        title=record.title or anime.canonical_title or "",
        titles=_dedupe(
            [
                record.title,
                record.title_english,
                record.title_japanese,
                anime.canonical_title,
            ]
            + (record.title_synonyms or [])
        ),
        year=record.year,
        summary=record.synopsis or "",
        score=record.score,
        tags=_dedupe(record.tags or []),
        url=record.url or "",
        cover=record.cover,
        raw=record.raw or {},
        existing_anime_id=anime.id,
    )


def _source_from_local_moegirl(
    record: MoegirlRecord,
    anime: Anime,
) -> SourceAnime:
    return SourceAnime(
        source="moegirl",
        source_id=record.source_id,
        title=record.title or record.page_key or anime.canonical_title or "",
        titles=_dedupe([record.title, record.page_key, anime.canonical_title]),
        year=_year_from_text(record.latest_timestamp),
        summary=record.summary or "",
        score=record.score,
        tags=_dedupe(record.tags or []),
        url=record.url or "",
        cover=record.cover,
        raw=record.raw or {},
        existing_anime_id=anime.id,
    )


async def _search_bangumi(
    client: Any,
    query: str,
    limit: int,
) -> list[SourceAnime]:
    response = await client.search_subjects(keyword=query, limit=limit, offset=0)
    detail_tasks = [client.get_subject(subject.id) for subject in response.data[:limit]]
    details = await asyncio.gather(*detail_tasks, return_exceptions=True)
    items: list[SourceAnime] = []
    for fallback, detail in zip(response.data[:limit], details, strict=True):
        subject = detail if isinstance(detail, BangumiSubject) else fallback
        items.append(_source_from_bangumi(subject))
    return items


async def _search_jikan(client: Any, query: str, limit: int) -> list[SourceAnime]:
    response = await client.search_anime(q=query, limit=limit)
    detail_tasks = [client.get_anime(anime.mal_id) for anime in response.data[:limit]]
    details = await asyncio.gather(*detail_tasks, return_exceptions=True)
    items: list[SourceAnime] = []
    for fallback, detail_response in zip(response.data[:limit], details, strict=True):
        detail = getattr(detail_response, "data", None)
        anime = detail if isinstance(detail, JikanAnime) else fallback
        items.append(_source_from_jikan(anime))
    return items


async def _search_moegirl(client: Any, query: str, limit: int) -> list[SourceAnime]:
    response = await client.search(q=query, limit=limit)
    pages = response.pages[:limit]
    detail_tasks = [client.get_page(key=page.key or page.title) for page in pages]
    details = await asyncio.gather(*detail_tasks, return_exceptions=True)
    items: list[SourceAnime] = []
    for fallback, detail in zip(pages, details, strict=True):
        page = detail if isinstance(detail, MoegirlPage) else _page_from_search(fallback)
        items.append(_source_from_moegirl(page, fallback))
    return items


def _source_from_bangumi(subject: BangumiSubject) -> SourceAnime:
    tags = _dedupe([tag.name for tag in subject.tags] + subject.meta_tags)
    titles = _dedupe([subject.name, subject.name_cn])
    cover = None
    if subject.images is not None:
        cover = subject.images.large or subject.images.common or subject.images.medium
    return SourceAnime(
        source="bangumi",
        source_id=str(subject.id),
        title=subject.name_cn or subject.name,
        titles=titles,
        year=_year_from_text(subject.date),
        summary=subject.summary or "",
        score=subject.rating.score if subject.rating else None,
        tags=tags,
        url=f"https://bgm.tv/subject/{subject.id}",
        cover=cover,
        raw=asdict(subject),
    )


def _source_from_jikan(anime: JikanAnime) -> SourceAnime:
    tags = _dedupe(
        [entity.name for entity in anime.genres]
        + [entity.name for entity in anime.themes]
        + [entity.name for entity in anime.demographics]
    )
    titles = _dedupe(
        [anime.title, anime.title_english, anime.title_japanese]
        + anime.title_synonyms
        + [title.title for title in anime.titles]
    )
    return SourceAnime(
        source="jikan",
        source_id=str(anime.mal_id),
        title=anime.title,
        titles=titles,
        year=anime.year,
        summary=anime.synopsis or "",
        score=anime.score,
        tags=tags,
        url=anime.url or "",
        cover=None,
        raw=asdict(anime),
    )


def _source_from_moegirl(
    page: MoegirlPage,
    fallback: MoegirlSearchPage | None = None,
) -> SourceAnime:
    source = page.source or ""
    tags = _extract_moegirl_categories(source)
    summary = _extract_moegirl_summary(source)
    titles = _dedupe([page.title, page.key] + _extract_moegirl_aliases(source))
    return SourceAnime(
        source="moegirl",
        source_id=str(page.id),
        title=page.title or (fallback.title if fallback else ""),
        titles=titles,
        year=_year_from_text(source),
        summary=summary or (fallback.description if fallback else "") or "",
        score=None,
        tags=tags,
        url=page.url,
        cover=None,
        raw=asdict(page),
    )


def _page_from_search(page: MoegirlSearchPage) -> MoegirlPage:
    return MoegirlPage(
        id=page.id,
        key=page.key,
        title=page.title,
        content_model=None,
        latest=None,
        license=None,
        html_url=None,
        source=None,
        url=MoegirlClient.page_url(page.id) if page.id else "",
    )


def _find_existing_anime_id(session: Session, item: SourceAnime) -> uuid.UUID | None:
    record_cls = _record_class(item.source)
    record = session.scalar(
        select(record_cls).where(record_cls.source_id == item.source_id)
    )
    return record.anime_id if record is not None else None


def _group_source_items(
    items: list[SourceAnime],
    warnings: list[str],
) -> list[AnimeGroup]:
    groups: list[AnimeGroup] = []
    for item in items:
        matched_group: AnimeGroup | None = None
        for group in groups:
            if any(_is_same_anime(item, existing) for existing in group.items):
                matched_group = group
                break
        if matched_group is None:
            groups.append(AnimeGroup(items=[item], anime_id=item.existing_anime_id))
            continue

        existing_ids = {
            anime_id
            for anime_id in [matched_group.anime_id, item.existing_anime_id]
            if anime_id is not None
        }
        if len(existing_ids) > 1:
            warnings.append(
                "跨源合并冲突，已保留为独立结果: "
                f"{matched_group.items[0].title} / {item.title}"
            )
            groups.append(AnimeGroup(items=[item], anime_id=item.existing_anime_id))
            continue

        matched_group.items.append(item)
        if matched_group.anime_id is None:
            matched_group.anime_id = item.existing_anime_id

    return groups


def _upsert_groups(
    session: Session,
    groups: list[AnimeGroup],
    warnings: list[str],
) -> None:
    for group in groups:
        if group.anime_id is None:
            anime = Anime(canonical_title=_canonical_title(group))
            session.add(anime)
            session.flush()
            group.anime_id = anime.id
        else:
            anime = session.get(Anime, group.anime_id)
            if anime is not None and not anime.canonical_title:
                anime.canonical_title = _canonical_title(group)

        for item in group.items:
            _upsert_source_record(session, item, group.anime_id, warnings)


def _upsert_source_record(
    session: Session,
    item: SourceAnime,
    anime_id: uuid.UUID,
    warnings: list[str],
) -> None:
    record_cls = _record_class(item.source)
    record = session.scalar(
        select(record_cls).where(record_cls.source_id == item.source_id)
    )
    if record is not None and record.anime_id != anime_id:
        warnings.append(f"{item.source}:{item.source_id} 已绑定其他 Anime，跳过重绑")
        anime_id = record.anime_id

    if item.source == "bangumi":
        _upsert_bangumi(session, item, anime_id, record)
    elif item.source == "jikan":
        _upsert_jikan(session, item, anime_id, record)
    else:
        _upsert_moegirl(session, item, anime_id, record)


def _upsert_bangumi(
    session: Session,
    item: SourceAnime,
    anime_id: uuid.UUID,
    record: BangumiRecord | None,
) -> None:
    subject = item.raw
    images = subject.get("images") if isinstance(subject.get("images"), dict) else {}
    if record is None:
        record = BangumiRecord(source_id=item.source_id, anime_id=anime_id)
        session.add(record)
    record.name = _as_optional_str(subject.get("name"))
    record.name_cn = _as_optional_str(subject.get("name_cn"))
    record.summary = item.summary
    record.air_date = _as_optional_str(subject.get("date"))
    record.platform = _as_optional_str(subject.get("platform"))
    record.rank = _as_optional_int(subject.get("rank"))
    record.score = item.score
    record.total_episodes = _as_optional_int(subject.get("total_episodes"))
    record.tags = item.tags
    record.cover = item.cover or _as_optional_str(images.get("large"))
    record.url = item.url
    record.raw = item.raw


def _upsert_jikan(
    session: Session,
    item: SourceAnime,
    anime_id: uuid.UUID,
    record: JikanRecord | None,
) -> None:
    anime = item.raw
    if record is None:
        record = JikanRecord(source_id=item.source_id, anime_id=anime_id)
        session.add(record)
    record.title = _as_optional_str(anime.get("title"))
    record.title_english = _as_optional_str(anime.get("title_english"))
    record.title_japanese = _as_optional_str(anime.get("title_japanese"))
    record.title_synonyms = anime.get("title_synonyms") or []
    record.synopsis = item.summary
    record.year = item.year
    record.season = _as_optional_str(anime.get("season"))
    record.media_type = _as_optional_str(anime.get("type"))
    record.episodes = _as_optional_int(anime.get("episodes"))
    record.rank = _as_optional_int(anime.get("rank"))
    record.score = item.score
    record.tags = item.tags
    record.cover = item.cover
    record.url = item.url
    record.raw = item.raw


def _upsert_moegirl(
    session: Session,
    item: SourceAnime,
    anime_id: uuid.UUID,
    record: MoegirlRecord | None,
) -> None:
    page = item.raw
    latest = page.get("latest") if isinstance(page.get("latest"), dict) else {}
    if record is None:
        record = MoegirlRecord(source_id=item.source_id, anime_id=anime_id)
        session.add(record)
    record.page_id = _as_optional_int(page.get("id"))
    record.page_key = _as_optional_str(page.get("key"))
    record.title = _as_optional_str(page.get("title"))
    record.summary = item.summary
    record.latest_revision_id = _as_optional_int(latest.get("id"))
    record.latest_timestamp = _as_optional_str(latest.get("timestamp"))
    record.content_model = _as_optional_str(page.get("content_model"))
    record.score = None
    record.tags = item.tags
    record.cover = item.cover
    record.url = item.url
    record.raw = item.raw


def _build_response(
    query: str,
    requested_tags: list[str],
    groups: list[AnimeGroup],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "ok": True,
        "query": {"anime_name": query, "anime_tag": requested_tags},
        "items": [_public_item(group) for group in groups],
        "warnings": warnings,
    }


def _public_item(group: AnimeGroup) -> dict[str, Any]:
    by_source = {item.source: item for item in group.items}
    bangumi = by_source.get("bangumi")
    moegirl = by_source.get("moegirl")
    summary_item = bangumi if bangumi and bangumi.summary else moegirl
    url_item = bangumi if bangumi and bangumi.url else moegirl
    return {
        "title": _canonical_title(group),
        "tags": _merged_tags(group),
        "summary": summary_item.summary if summary_item else "",
        "url": url_item.url if url_item else "",
        "ratings": {
            "bangumi": bangumi.score if bangumi else None,
            "jikan": by_source["jikan"].score if "jikan" in by_source else None,
            "moegirl": None,
        },
    }


def _canonical_title(group: AnimeGroup) -> str:
    for source in ("bangumi", "moegirl", "jikan"):
        for item in group.items:
            if item.source == source and item.title:
                return item.title
    if group.local_title:
        return group.local_title
    for item in group.items:
        if item.title:
            return item.title
    return ""


def _merged_tags(group: AnimeGroup) -> list[str]:
    return _dedupe(tag for item in group.items for tag in item.tags)


def _matches_tags(group: AnimeGroup, requested_tags: list[str]) -> bool:
    if not requested_tags:
        return True
    tag_set = {_normalize_tag(tag) for tag in _merged_tags(group)}
    return all(_normalize_tag(tag) in tag_set for tag in requested_tags)


def _matches_local_name(group: AnimeGroup, query: str) -> bool:
    normalized_query = _normalize_title(query)
    folded_query = query.casefold()
    titles = _dedupe(
        [group.local_title]
        + [item.title for item in group.items]
        + [title for item in group.items for title in item.titles]
    )
    for title in titles:
        if normalized_query:
            if normalized_query in _normalize_title(title):
                return True
        elif folded_query in title.casefold():
            return True
    return False


def _is_same_anime(left: SourceAnime, right: SourceAnime) -> bool:
    left_titles = {_normalize_title(title) for title in left.titles if title}
    right_titles = {_normalize_title(title) for title in right.titles if title}
    left_titles.discard("")
    right_titles.discard("")
    if not left_titles or not right_titles or left_titles.isdisjoint(right_titles):
        return False
    if left.year is not None and right.year is not None:
        return left.year == right.year
    return any(len(title) >= 4 for title in left_titles & right_titles)


def _record_class(source: SourceName) -> type[BangumiRecord | JikanRecord | MoegirlRecord]:
    if source == "bangumi":
        return BangumiRecord
    if source == "jikan":
        return JikanRecord
    return MoegirlRecord


def _normalize_requested_tags(tags: list[str] | None) -> list[str]:
    return _dedupe(tag.strip() for tag in (tags or []) if tag and tag.strip())


def _normalize_title(title: str) -> str:
    return re.sub(r"[\s:：!！._\-~～]+", "", title).casefold()


def _normalize_tag(tag: str) -> str:
    return tag.strip().casefold()


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _year_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def _extract_moegirl_categories(source: str) -> list[str]:
    return _dedupe(
        match.group(1)
        for match in re.finditer(r"\[\[(?:Category|分类):([^\]|]+)", source)
    )


def _extract_moegirl_aliases(source: str) -> list[str]:
    aliases: list[str] = []
    for key in ("原名", "译名", "常用译名", "标题"):
        pattern = (
            r"\|"
            + re.escape(key)
            + r"\s*=\s*(.*?)(?=\n\||\|[\w\u4e00-\u9fff]+\s*=|\}\}|\n)"
        )
        match = re.search(
            pattern,
            source,
        )
        if match:
            aliases.extend(_split_wiki_text(match.group(1)))
    return _dedupe(aliases)


def _extract_moegirl_summary(source: str) -> str:
    text = re.sub(r"\{\{[^{}]*\}\}", "", source)
    text = re.sub(r"\[\[(?:Category|分类):[^\]]+\]\]", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"'''?", "", text)
    for paragraph in re.split(r"\n\s*\n", text):
        cleaned = paragraph.strip()
        if not cleaned or cleaned.startswith(("{{", "|", "=", "[[Category", "[[分类")):
            continue
        if len(cleaned) < 12:
            continue
        return _strip_wiki_markup(cleaned)
    return ""


def _split_wiki_text(text: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"\{\{[^|{}]+\|([^{}]+)\}\}", r"\1", text)
    return [_strip_wiki_markup(part) for part in re.split(r"[\n;/；、]+", text)]


def _strip_wiki_markup(text: str) -> str:
    text = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
