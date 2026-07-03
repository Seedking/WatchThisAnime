"""用户交互记录服务。"""

import uuid
from typing import Any, Literal

from sqlalchemy import select

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

TargetType = Literal["anime", "tag"]
AnimeAction = Literal["viewed", "wishlisted"]

_ANIME_ACTIONS: set[str] = {"viewed", "wishlisted"}


class InteractionError(ValueError):
    """交互记录请求校验失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def record_interaction(
    user_id: str,
    target_type: TargetType | str,
    target_id: str,
    rating: int | None = None,
    action: AnimeAction | str | None = None,
) -> dict[str, Any]:
    """校验并记录一次 anime 或 tag 交互。"""
    try:
        ensure_user(user_id)
    except UserError as exc:
        raise InteractionError("invalid_user", str(exc)) from exc

    if target_type == "anime":
        return _record_anime_interaction(user_id, target_id, action, rating)
    if target_type == "tag":
        return _record_tag_interaction(user_id, target_id, rating)
    raise InteractionError("invalid_target_type", "target_type 必须是 anime 或 tag")


def _record_anime_interaction(
    user_id: str,
    target_id: str,
    action: str | None,
    rating: int | None,
) -> dict[str, Any]:
    if action not in _ANIME_ACTIONS:
        raise InteractionError("invalid_action", "anime action 必须是 viewed 或 wishlisted")
    _validate_optional_rating(rating)

    try:
        anime_id = uuid.UUID(target_id)
    except (TypeError, ValueError) as exc:
        raise InteractionError("invalid_anime_id", "target_id 必须是 Anime UUID") from exc

    with SessionLocal() as session:
        anime = session.get(Anime, anime_id)
        if anime is None:
            raise InteractionError("anime_not_found", "Anime 不存在，无法记录交互")

        interaction = AnimeInteraction(
            user_id=user_id,
            anime_id=anime_id,
            action=action,
            rating=rating,
        )
        session.add(interaction)
        session.commit()
        session.refresh(interaction)

        return {
            "type": "anime",
            "id": interaction.id,
            "user_id": interaction.user_id,
            "anime_id": str(interaction.anime_id),
            "action": interaction.action,
            "rating": interaction.rating,
        }


def _record_tag_interaction(
    user_id: str,
    target_id: str,
    rating: int | None,
) -> dict[str, Any]:
    tag = target_id.strip() if isinstance(target_id, str) else ""
    if not tag:
        raise InteractionError("invalid_tag", "target_id 必须是非空 tag")
    _validate_required_score(rating)

    with SessionLocal() as session:
        if not _tag_exists(session, tag):
            raise InteractionError("tag_not_found", "tag 不存在，无法记录偏好分")

        interaction = session.scalar(
            select(TagInteraction).where(
                TagInteraction.user_id == user_id,
                TagInteraction.tag == tag,
            )
        )
        if interaction is None:
            interaction = TagInteraction(user_id=user_id, tag=tag, score=rating)
            session.add(interaction)
        else:
            interaction.score = rating

        session.commit()
        session.refresh(interaction)

        return {
            "type": "tag",
            "id": interaction.id,
            "user_id": interaction.user_id,
            "tag": interaction.tag,
            "score": interaction.score,
        }


def _validate_optional_rating(rating: int | None) -> None:
    if rating is None:
        return
    _validate_score_value(rating, "rating")


def _validate_required_score(score: int | None) -> None:
    if score is None:
        raise InteractionError("invalid_score", "tag rating 必须是 1-10 整数")
    _validate_score_value(score, "score")


def _validate_score_value(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise InteractionError(f"invalid_{field_name}", f"{field_name} 必须是 1-10 整数")


def _tag_exists(session: Any, tag: str) -> bool:
    for record_type in (BangumiRecord, MoegirlRecord, JikanRecord):
        tag_lists = session.scalars(select(record_type.tags)).all()
        for tags in tag_lists:
            if isinstance(tags, list) and tag in tags:
                return True
    return False
