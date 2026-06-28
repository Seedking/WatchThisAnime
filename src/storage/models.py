"""ORM 数据模型。

定义跨来源共享的中性主表 ``anime``、三个来源记录表（bangumi / moegirl / jikan）、
``user`` 表，以及两张交互表 ``anime_interactions`` / ``tag_interactions``。

- ``anime`` 主表使用 UUID 主键，UUID 由 GitHub 数据集同步时分配（``uuid4`` 作兜底默认）；
- 三个来源记录表结构同构，各自表内 ``source_id`` 唯一，通过外键关联 ``anime.id``；
- ``user.id`` 为外部传入的字符串用户标识，首次访问时创建（见 ``services.user_service.ensure_user``）；
- 两张交互表本期列结构一致，``tag_interactions`` 为占位，待后续按 CLAUDE.md
  （``tag`` + ``score`` + ``UNIQUE(user_id, tag)``）调整。
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.storage.database import Base


class Anime(Base):
    """番剧主表：跨来源共享的中性元数据。

    UUID 主键由 GitHub 数据集同步时分配，保证稳定；``uuid4`` 仅作兜底默认。
    """

    __tablename__ = "anime"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical_title: Mapped[str | None] = mapped_column(String, nullable=True)
    title_jp: Mapped[str | None] = mapped_column(String, nullable=True)
    title_zh: Mapped[str | None] = mapped_column(String, nullable=True)
    airing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    season: Mapped[str | None] = mapped_column(String, nullable=True)

    bangumi_records: Mapped[list["BangumiRecord"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    moegirl_records: Mapped[list["MoegirlRecord"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    jikan_records: Mapped[list["JikanRecord"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    anime_interactions: Mapped[list["AnimeInteraction"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    tag_interactions: Mapped[list["TagInteraction"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Anime id={self.id} canonical_title={self.canonical_title!r}>"


class BangumiRecord(Base):
    """Bangumi 来源记录表。

    Attributes:
        source_id: Bangumi 侧条目 ID，本表内唯一。
        anime_id: 关联的 ``anime.id``（UUID）。
        score: Bangumi 评分。
        tags: Bangumi 标签列表（JSON）。
        cover: 封面图 URL。
        url: Bangumi 条目页 URL。
        raw: 原始 API 响应（JSON）。
    """

    __tablename__ = "bangumi_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, unique=True)
    anime_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anime.id"))
    score: Mapped[float | None] = mapped_column(nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cover: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    anime: Mapped["Anime"] = relationship(back_populates="bangumi_records")

    def __repr__(self) -> str:
        return f"<BangumiRecord source_id={self.source_id!r} anime_id={self.anime_id}>"


class MoegirlRecord(Base):
    """萌娘百科来源记录表，结构与 ``BangumiRecord`` 同构。"""

    __tablename__ = "moegirl_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, unique=True)
    anime_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anime.id"))
    score: Mapped[float | None] = mapped_column(nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cover: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    anime: Mapped["Anime"] = relationship(back_populates="moegirl_records")

    def __repr__(self) -> str:
        return f"<MoegirlRecord source_id={self.source_id!r} anime_id={self.anime_id}>"


class JikanRecord(Base):
    """Jikan (MyAnimeList) 来源记录表，结构与 ``BangumiRecord`` 同构。"""

    __tablename__ = "jikan_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, unique=True)
    anime_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anime.id"))
    score: Mapped[float | None] = mapped_column(nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cover: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    anime: Mapped["Anime"] = relationship(back_populates="jikan_records")

    def __repr__(self) -> str:
        return f"<JikanRecord source_id={self.source_id!r} anime_id={self.anime_id}>"


class User(Base):
    """用户表：``id`` 为外部传入的字符串用户标识，首次访问时创建。

    用户管理由外部系统完成；服务端只在首次见到某 ``user_id`` 时插入一行，后续直接复用。
    """

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    anime_interactions: Mapped[list["AnimeInteraction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tag_interactions: Mapped[list["TagInteraction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r}>"


class AnimeInteraction(Base):
    """用户对番的行为与评分记录。

    ``record_user_interaction`` 工具写入此表。``action ∈ {viewed, wishlisted}``（本期
    仅这两种），``rating`` 整数 1-10 可空（``viewed``/``wishlisted`` 未必伴随打分）。
    """

    __tablename__ = "anime_interactions"
    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 10", name="ck_anime_interactions_rating"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    anime_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anime.id"))
    action: Mapped[str] = mapped_column(String(20))
    rating: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship(back_populates="anime_interactions")
    anime: Mapped["Anime"] = relationship(back_populates="anime_interactions")

    def __repr__(self) -> str:
        return (
            f"<AnimeInteraction user_id={self.user_id!r} anime_id={self.anime_id} "
            f"action={self.action!r} rating={self.rating}>"
        )


class TagInteraction(Base):
    """用户对标签/题材的打分记录（占位）。

    本期列结构暂同 ``AnimeInteraction``，待后续按 CLAUDE.md 调整为
    ``tag`` + ``score`` + ``UNIQUE(user_id, tag)``。
    """

    __tablename__ = "tag_interactions"
    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 10", name="ck_tag_interactions_rating"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    anime_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anime.id"))
    action: Mapped[str] = mapped_column(String(20))
    rating: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship(back_populates="tag_interactions")
    anime: Mapped["Anime"] = relationship(back_populates="tag_interactions")

    def __repr__(self) -> str:
        return (
            f"<TagInteraction user_id={self.user_id!r} anime_id={self.anime_id} "
            f"action={self.action!r} rating={self.rating}>"
        )
