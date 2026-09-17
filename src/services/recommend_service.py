"""Anime recommendation and recent-history service."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.services.user_service import UserError, ensure_user
from src.storage.database import SessionLocal
from src.storage.models import (
    Anime,
    AnimeInteraction,
    BangumiRecord,
    JikanRecord,
    MoegirlRecord,
    TagInteraction,
)

MIN_PERSONALIZED_INTERACTIONS = 3
_RECOMMENDATION_LIMIT = 10
_RECENT_LIMIT = 10
_SOURCE_ORDER = ("bangumi", "jikan", "moegirl")


class RecommendationError(ValueError):
    """Recommendation request validation failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def recommend_anime(user_id: str) -> dict[str, Any]:
    """Return deterministic cold-start or personalized recommendations."""
    _ensure_user(user_id)

    with SessionLocal() as session:
        interactions = list(
            session.scalars(
                select(AnimeInteraction)
                .where(AnimeInteraction.user_id == user_id)
                .order_by(AnimeInteraction.id)
            )
        )
        tag_rows = list(
            session.scalars(
                select(TagInteraction)
                .where(TagInteraction.user_id == user_id)
                .order_by(TagInteraction.tag)
            )
        )
        animes = list(session.scalars(select(Anime).order_by(Anime.id)))
        if not animes:
            return {"phase": "cold_start", "items": []}

        source_map = _load_source_summaries(session)
        latest_interactions = _latest_interactions(interactions)
        phase = (
            "personalized"
            if len(latest_interactions) >= MIN_PERSONALIZED_INTERACTIONS
            else "cold_start"
        )

        blocked_ids = {
            anime_id
            for anime_id, interaction in latest_interactions.items()
            if interaction.action == "viewed"
        }
        tag_preferences, history_preferences = _build_preferences(
            tag_rows,
            latest_interactions,
            source_map,
        )

        candidates: list[tuple[float, str, str, dict[str, Any]]] = []
        for anime in animes:
            if anime.id in blocked_ids:
                continue

            sources = source_map.get(anime.id, [])
            title = _anime_title(anime, sources)
            base_score = _source_score(sources)
            reasons = [_source_reason(sources)]

            if phase == "personalized":
                tags = _source_tags(sources)
                affinity, matched_tags, history_tags = _preference_affinity(
                    tags,
                    tag_preferences,
                    history_preferences,
                )
                score = base_score + (1.5 * affinity)
                if matched_tags:
                    reasons.append("偏好标签：" + "、".join(matched_tags))
                if history_tags:
                    reasons.append("历史高分标签：" + "、".join(history_tags))

                latest = latest_interactions.get(anime.id)
                if latest is not None and latest.action == "wishlisted":
                    score += 0.2
                    reasons.append("已在想看列表")
            else:
                score = base_score

            score = round(score, 6)
            item = {
                "anime_id": str(anime.id),
                "title": title,
                "score": score,
                "reasons": reasons,
                "sources": sources,
            }
            candidates.append((score, title.casefold(), str(anime.id), item))

        candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
        return {
            "phase": phase,
            "items": [candidate[3] for candidate in candidates[:_RECOMMENDATION_LIMIT]],
        }


def recent_anime(user_id: str) -> dict[str, Any]:
    """Return the user's most recently interacted anime."""
    _ensure_user(user_id)

    with SessionLocal() as session:
        interactions = list(
            session.scalars(
                select(AnimeInteraction)
                .where(AnimeInteraction.user_id == user_id)
                .order_by(AnimeInteraction.created_at.desc(), AnimeInteraction.id.desc())
            )
        )
        if not interactions:
            return {"items": []}

        selected: list[AnimeInteraction] = []
        seen_ids: set[uuid.UUID] = set()
        for interaction in interactions:
            if interaction.anime_id in seen_ids:
                continue
            seen_ids.add(interaction.anime_id)
            selected.append(interaction)
            if len(selected) == _RECENT_LIMIT:
                break

        source_map = _load_source_summaries(session)
        items = []
        for interaction in selected:
            anime = session.get(Anime, interaction.anime_id)
            if anime is None:
                continue
            sources = source_map.get(anime.id, [])
            items.append(
                {
                    "anime_id": str(anime.id),
                    "title": _anime_title(anime, sources),
                    "action": interaction.action,
                    "rating": interaction.rating,
                    "created_at": (
                        interaction.created_at.isoformat()
                        if interaction.created_at is not None
                        else None
                    ),
                    "sources": sources,
                }
            )

        return {"items": items}


def _ensure_user(user_id: str) -> None:
    try:
        ensure_user(user_id)
    except UserError as exc:
        raise RecommendationError("invalid_user", str(exc)) from exc


def _latest_interactions(
    interactions: list[AnimeInteraction],
) -> dict[uuid.UUID, AnimeInteraction]:
    latest: dict[uuid.UUID, AnimeInteraction] = {}
    for interaction in interactions:
        latest[interaction.anime_id] = interaction
    return latest


def _build_preferences(
    tag_rows: list[TagInteraction],
    latest_interactions: dict[uuid.UUID, AnimeInteraction],
    source_map: dict[uuid.UUID, list[dict[str, Any]]],
) -> tuple[dict[str, float], dict[str, float]]:
    explicit: dict[str, float] = {}
    for row in tag_rows:
        explicit[_normalize_tag(row.tag)] = (row.score - 5.5) / 4.5

    history_values: dict[str, list[float]] = defaultdict(list)
    for anime_id, interaction in latest_interactions.items():
        if interaction.rating is None:
            continue
        weight = (interaction.rating - 5.5) / 4.5
        for tag in _source_tags(source_map.get(anime_id, [])):
            history_values[_normalize_tag(tag)].append(weight)

    history = {
        tag: sum(values) / len(values)
        for tag, values in history_values.items()
        if values
    }
    return explicit, history


def _preference_affinity(
    tags: list[str],
    explicit: dict[str, float],
    history: dict[str, float],
) -> tuple[float, list[str], list[str]]:
    matched_explicit: list[str] = []
    matched_history: list[str] = []
    values: list[float] = []
    for tag in tags:
        normalized = _normalize_tag(tag)
        explicit_score = explicit.get(normalized)
        history_score = history.get(normalized)
        if explicit_score is not None:
            matched_explicit.append(tag)
            values.append(explicit_score * 0.65)
        if history_score is not None:
            matched_history.append(tag)
            values.append(history_score * 0.35)

    if not values:
        return 0.0, matched_explicit, matched_history
    return sum(values) / len(values), matched_explicit, matched_history


def _load_source_summaries(session: Session) -> dict[uuid.UUID, list[dict[str, Any]]]:
    summaries: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)

    bangumi_rows = session.scalars(
        select(BangumiRecord).order_by(BangumiRecord.anime_id, BangumiRecord.source_id)
    )
    for record in bangumi_rows:
        summaries[record.anime_id].append(
            {
                "name": "bangumi",
                "source_id": record.source_id,
                "title": record.name_cn or record.name or "",
                "score": record.score,
                "rank": record.rank,
                "year": _year_from_text(record.air_date),
                "tags": _dedupe_strings(record.tags),
                "url": record.url,
            }
        )

    jikan_rows = session.scalars(
        select(JikanRecord).order_by(JikanRecord.anime_id, JikanRecord.source_id)
    )
    for record in jikan_rows:
        summaries[record.anime_id].append(
            {
                "name": "jikan",
                "source_id": record.source_id,
                "title": record.title or "",
                "score": record.score,
                "rank": record.rank,
                "year": record.year,
                "tags": _dedupe_strings(record.tags),
                "url": record.url,
            }
        )

    moegirl_rows = session.scalars(
        select(MoegirlRecord).order_by(MoegirlRecord.anime_id, MoegirlRecord.source_id)
    )
    for record in moegirl_rows:
        summaries[record.anime_id].append(
            {
                "name": "moegirl",
                "source_id": record.source_id,
                "title": record.title or "",
                "score": record.score,
                "rank": None,
                "year": None,
                "tags": _dedupe_strings(record.tags),
                "url": record.url,
            }
        )

    for records in summaries.values():
        records.sort(key=lambda item: _SOURCE_ORDER.index(item["name"]))
    return summaries


def _anime_title(anime: Anime, sources: list[dict[str, Any]]) -> str:
    if anime.canonical_title and anime.canonical_title.strip():
        return anime.canonical_title.strip()
    for source in sources:
        title = source.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return "Untitled Anime"


def _source_score(sources: list[dict[str, Any]]) -> float:
    scores = [
        float(source["score"])
        for source in sources
        if isinstance(source.get("score"), (int, float))
    ]
    if not scores:
        return 0.0

    best_score = max(scores)
    coverage_bonus = min(len(sources), 3) * 0.03
    ranks = [
        int(source["rank"])
        for source in sources
        if isinstance(source.get("rank"), int) and source["rank"] > 0
    ]
    rank_bonus = max(0.0, (101 - min(ranks)) / 10000) if ranks else 0.0
    return round((best_score / 10) + coverage_bonus + rank_bonus, 6)


def _source_reason(sources: list[dict[str, Any]]) -> str:
    scores = [
        float(source["score"])
        for source in sources
        if isinstance(source.get("score"), (int, float))
    ]
    if not scores:
        return "暂无来源评分"
    return f"来源综合评分 {max(scores):.1f}"


def _source_tags(sources: list[dict[str, Any]]) -> list[str]:
    return _dedupe_strings(
        tag
        for source in sources
        for tag in source.get("tags", [])
    )


def _dedupe_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = value.strip()
        normalized = _normalize_tag(text)
        if text and normalized not in seen:
            seen.add(normalized)
            result.append(text)
    return result


def _normalize_tag(tag: str) -> str:
    return tag.strip().casefold()


def _year_from_text(value: str | None) -> int | None:
    if not value:
        return None
    for index in range(0, max(0, len(value) - 3)):
        candidate = value[index : index + 4]
        if candidate.isdigit() and candidate.startswith(("19", "20")):
            return int(candidate)
    return None
