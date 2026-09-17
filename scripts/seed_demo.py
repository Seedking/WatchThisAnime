"""写入无需联网即可体验的演示数据。

脚本只使用本地 SQLite 和现有 ORM 模型。重复执行会按固定 Anime UUID 或来源
``source_id`` 更新同一批记录，并复用 ``demo-user`` 的交互数据。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

# 直接执行 scripts/seed_demo.py 时，确保可以从仓库根目录导入 src 包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.database import SessionLocal, init_db  # noqa: E402
from src.storage.models import (  # noqa: E402
    Anime,
    AnimeInteraction,
    BangumiRecord,
    JikanRecord,
    MoegirlRecord,
    TagInteraction,
    User,
)

DEMO_USER_ID = "demo-user"


@dataclass(frozen=True)
class DemoAnime:
    """演示番剧及其三个来源记录的稳定数据。"""

    anime_id: uuid.UUID
    canonical_title: str
    title_japanese: str
    title_english: str
    aliases: tuple[str, ...]
    summary: str
    tags: tuple[str, ...]
    year: int
    season: str
    episodes: int
    bangumi_source_id: str
    bangumi_score: float
    bangumi_rank: int
    bangumi_air_date: str
    jikan_source_id: str
    jikan_score: float
    jikan_rank: int
    moegirl_source_id: str
    moegirl_page_id: int
    moegirl_page_key: str


DEMO_ANIMES: tuple[DemoAnime, ...] = (
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0001-4d20-9001-000000000001"),
        canonical_title="葬送的芙莉莲",
        title_japanese="葬送のフリーレン",
        title_english="Frieren: Beyond Journey's End",
        aliases=("Frieren", "葬送のフリーレン"),
        summary="勇者一行击败魔王后，精灵魔法使芙莉莲重新理解时间、告别与人与人的联系。",
        tags=("奇幻", "冒险", "治愈", "魔法"),
        year=2023,
        season="fall",
        episodes=28,
        bangumi_source_id="400602",
        bangumi_score=9.4,
        bangumi_rank=1,
        bangumi_air_date="2023-09-29",
        jikan_source_id="52991",
        jikan_score=9.31,
        jikan_rank=1,
        moegirl_source_id="demo-moegirl-frieren",
        moegirl_page_id=900001,
        moegirl_page_key="葬送的芙莉莲",
    ),
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0002-4d20-9002-000000000002"),
        canonical_title="钢之炼金术师 FULLMETAL ALCHEMIST",
        title_japanese="鋼の錬金術師 FULLMETAL ALCHEMIST",
        title_english="Fullmetal Alchemist: Brotherhood",
        aliases=("钢之炼金术师 FA", "钢炼 FA"),
        summary="爱德华与阿尔冯斯兄弟为找回失去的身体踏上旅程，并逐步触及国家炼金术背后的真相。",
        tags=("奇幻", "冒险", "战斗", "剧情"),
        year=2009,
        season="spring",
        episodes=64,
        bangumi_source_id="1890",
        bangumi_score=9.0,
        bangumi_rank=2,
        bangumi_air_date="2009-04-05",
        jikan_source_id="5114",
        jikan_score=9.1,
        jikan_rank=2,
        moegirl_source_id="demo-moegirl-fma",
        moegirl_page_id=900002,
        moegirl_page_key="钢之炼金术师 FULLMETAL ALCHEMIST",
    ),
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0003-4d20-9003-000000000003"),
        canonical_title="命运石之门",
        title_japanese="STEINS;GATE",
        title_english="Steins;Gate",
        aliases=("Steins;Gate", "石头门"),
        summary="自称疯狂科学家的冈部伦太郎意外造出能改变过去的装置，并被迫面对时间线收束的代价。",
        tags=("科幻", "悬疑", "剧情", "时间旅行"),
        year=2011,
        season="spring",
        episodes=24,
        bangumi_source_id="10380",
        bangumi_score=9.1,
        bangumi_rank=3,
        bangumi_air_date="2011-04-06",
        jikan_source_id="9253",
        jikan_score=9.07,
        jikan_rank=3,
        moegirl_source_id="demo-moegirl-steinsgate",
        moegirl_page_id=900003,
        moegirl_page_key="命运石之门",
    ),
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0004-4d20-9004-000000000004"),
        canonical_title="夏目友人帐",
        title_japanese="夏目友人帳",
        title_english="Natsume's Book of Friends",
        aliases=("Natsume Yuujinchou",),
        summary="能看见妖怪的少年夏目贵志继承外祖母的友人帐，与猫咪老师一起归还妖怪名字。",
        tags=("治愈", "妖怪", "日常", "奇幻"),
        year=2008,
        season="summer",
        episodes=13,
        bangumi_source_id="1432",
        bangumi_score=8.7,
        bangumi_rank=18,
        bangumi_air_date="2008-07-08",
        jikan_source_id="4081",
        jikan_score=8.65,
        jikan_rank=135,
        moegirl_source_id="demo-moegirl-natsume",
        moegirl_page_id=900004,
        moegirl_page_key="夏目友人帐",
    ),
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0005-4d20-9005-000000000005"),
        canonical_title="孤独摇滚！",
        title_japanese="ぼっち・ざ・ろっく！",
        title_english="Bocchi the Rock!",
        aliases=("Bocchi the Rock!",),
        summary="极度怕生的吉他手后藤一里加入结束乐队，在舞台与日常中一点点走出自己的世界。",
        tags=("音乐", "日常", "喜剧", "青春"),
        year=2022,
        season="fall",
        episodes=12,
        bangumi_source_id="335242",
        bangumi_score=8.8,
        bangumi_rank=12,
        bangumi_air_date="2022-10-09",
        jikan_source_id="47917",
        jikan_score=8.76,
        jikan_rank=58,
        moegirl_source_id="demo-moegirl-bocchi",
        moegirl_page_id=900005,
        moegirl_page_key="孤独摇滚",
    ),
    DemoAnime(
        anime_id=uuid.UUID("7a1c3f10-0006-4d20-9006-000000000006"),
        canonical_title="辉夜大小姐想让我告白",
        title_japanese="かぐや様は告らせたい",
        title_english="Kaguya-sama: Love Is War",
        aliases=("Kaguya-sama: Love Is War",),
        summary="秀知院学园的学生会长与副会长互有好感，却都把告白当成一场必须赢下的心理战。",
        tags=("恋爱", "喜剧", "校园", "日常"),
        year=2019,
        season="winter",
        episodes=12,
        bangumi_source_id="268544",
        bangumi_score=8.4,
        bangumi_rank=44,
        bangumi_air_date="2019-01-12",
        jikan_source_id="40456",
        jikan_score=8.4,
        jikan_rank=174,
        moegirl_source_id="demo-moegirl-kaguya",
        moegirl_page_id=900006,
        moegirl_page_key="辉夜大小姐想让我告白",
    ),
)

DEMO_ANIME_INTERACTIONS: tuple[tuple[int, str, int], ...] = (
    (0, "viewed", 10),
    (2, "viewed", 9),
    (4, "wishlisted", 8),
)

DEMO_TAG_INTERACTIONS: tuple[tuple[str, int], ...] = (
    ("奇幻", 9),
    ("科幻", 9),
    ("治愈", 8),
    ("音乐", 8),
)


def _upsert_anime(session: Session, seed: DemoAnime) -> uuid.UUID:
    """优先复用任一来源已绑定的 Anime，否则使用固定 UUID 创建。"""
    record_specs: tuple[tuple[type[Any], str], ...] = (
        (BangumiRecord, seed.bangumi_source_id),
        (JikanRecord, seed.jikan_source_id),
        (MoegirlRecord, seed.moegirl_source_id),
    )
    existing_ids: set[uuid.UUID] = set()
    for record_type, source_id in record_specs:
        record = session.scalar(
            select(record_type).where(record_type.source_id == source_id)
        )
        if record is not None:
            existing_ids.add(record.anime_id)

    if len(existing_ids) > 1:
        raise RuntimeError(f"{seed.canonical_title} 的来源记录绑定了多个 Anime")

    anime_id = next(iter(existing_ids), seed.anime_id)
    anime = session.get(Anime, anime_id)
    if anime is None:
        anime = Anime(id=anime_id, canonical_title=seed.canonical_title)
        session.add(anime)
    else:
        anime.canonical_title = seed.canonical_title
    session.flush()
    return anime.id


def _upsert_bangumi(
    session: Session,
    seed: DemoAnime,
    anime_id: uuid.UUID,
) -> None:
    record = session.scalar(
        select(BangumiRecord).where(
            BangumiRecord.source_id == seed.bangumi_source_id
        )
    )
    if record is None:
        record = BangumiRecord(
            source_id=seed.bangumi_source_id,
            anime_id=anime_id,
        )
        session.add(record)
    record.anime_id = anime_id
    record.name = seed.title_japanese
    record.name_cn = seed.canonical_title
    record.summary = seed.summary
    record.air_date = seed.bangumi_air_date
    record.platform = "TV"
    record.rank = seed.bangumi_rank
    record.score = seed.bangumi_score
    record.total_episodes = seed.episodes
    record.tags = list(seed.tags)
    record.cover = None
    record.url = f"https://bgm.tv/subject/{seed.bangumi_source_id}"
    record.raw = {"demo": True, "source": "bangumi"}


def _upsert_jikan(
    session: Session,
    seed: DemoAnime,
    anime_id: uuid.UUID,
) -> None:
    record = session.scalar(
        select(JikanRecord).where(JikanRecord.source_id == seed.jikan_source_id)
    )
    if record is None:
        record = JikanRecord(
            source_id=seed.jikan_source_id,
            anime_id=anime_id,
        )
        session.add(record)
    record.anime_id = anime_id
    record.title = seed.title_english
    record.title_english = seed.title_english
    record.title_japanese = seed.title_japanese
    record.title_synonyms = list(seed.aliases)
    record.synopsis = seed.summary
    record.year = seed.year
    record.season = seed.season
    record.media_type = "TV"
    record.episodes = seed.episodes
    record.rank = seed.jikan_rank
    record.score = seed.jikan_score
    record.tags = list(seed.tags)
    record.cover = None
    record.url = f"https://myanimelist.net/anime/{seed.jikan_source_id}"
    record.raw = {"demo": True, "source": "jikan"}


def _upsert_moegirl(
    session: Session,
    seed: DemoAnime,
    anime_id: uuid.UUID,
) -> None:
    record = session.scalar(
        select(MoegirlRecord).where(
            MoegirlRecord.source_id == seed.moegirl_source_id
        )
    )
    if record is None:
        record = MoegirlRecord(
            source_id=seed.moegirl_source_id,
            anime_id=anime_id,
        )
        session.add(record)
    record.anime_id = anime_id
    record.page_id = seed.moegirl_page_id
    record.page_key = seed.moegirl_page_key
    record.title = seed.canonical_title
    record.summary = seed.summary
    record.latest_revision_id = None
    record.latest_timestamp = None
    record.content_model = "wikitext"
    record.score = None
    record.tags = list(seed.tags)
    record.cover = None
    record.url = f"https://zh.moegirl.org.cn/{seed.moegirl_page_key}"
    record.raw = {"demo": True, "source": "moegirl"}


def _seed_user_interactions(
    session: Session,
    anime_ids: list[uuid.UUID],
) -> None:
    if session.get(User, DEMO_USER_ID) is None:
        session.add(User(id=DEMO_USER_ID))
    session.flush()

    for anime_index, action, rating in DEMO_ANIME_INTERACTIONS:
        anime_id = anime_ids[anime_index]
        existing = session.scalar(
            select(AnimeInteraction).where(
                AnimeInteraction.user_id == DEMO_USER_ID,
                AnimeInteraction.anime_id == anime_id,
                AnimeInteraction.action == action,
                AnimeInteraction.rating == rating,
            )
        )
        if existing is None:
            session.add(
                AnimeInteraction(
                    user_id=DEMO_USER_ID,
                    anime_id=anime_id,
                    action=action,
                    rating=rating,
                )
            )

    for tag, score in DEMO_TAG_INTERACTIONS:
        existing = session.scalar(
            select(TagInteraction).where(
                TagInteraction.user_id == DEMO_USER_ID,
                TagInteraction.tag == tag,
            )
        )
        if existing is None:
            session.add(
                TagInteraction(
                    user_id=DEMO_USER_ID,
                    tag=tag,
                    score=score,
                )
            )
        else:
            existing.score = score


def _count_rows(session: Session) -> dict[str, int]:
    bangumi_source_ids = [seed.bangumi_source_id for seed in DEMO_ANIMES]
    jikan_source_ids = [seed.jikan_source_id for seed in DEMO_ANIMES]
    moegirl_source_ids = [seed.moegirl_source_id for seed in DEMO_ANIMES]
    return {
        "anime": 0
        + session.scalar(
            select(func.count(func.distinct(BangumiRecord.anime_id)))
            .select_from(BangumiRecord)
            .where(BangumiRecord.source_id.in_(bangumi_source_ids))
        ),
        "bangumi": 0
        + session.scalar(
            select(func.count())
            .select_from(BangumiRecord)
            .where(BangumiRecord.source_id.in_(bangumi_source_ids))
        ),
        "jikan": 0
        + session.scalar(
            select(func.count())
            .select_from(JikanRecord)
            .where(JikanRecord.source_id.in_(jikan_source_ids))
        ),
        "moegirl": 0
        + session.scalar(
            select(func.count())
            .select_from(MoegirlRecord)
            .where(MoegirlRecord.source_id.in_(moegirl_source_ids))
        ),
        "anime_interactions": 0
        + session.scalar(
            select(func.count())
            .select_from(AnimeInteraction)
            .where(AnimeInteraction.user_id == DEMO_USER_ID)
        ),
        "tag_interactions": 0
        + session.scalar(
            select(func.count())
            .select_from(TagInteraction)
            .where(TagInteraction.user_id == DEMO_USER_ID)
        ),
    }


def seed_demo_data() -> dict[str, object]:
    """建表并幂等写入演示番剧、来源记录和用户交互。"""
    init_db()
    with SessionLocal() as session:
        anime_ids: list[uuid.UUID] = []
        for seed in DEMO_ANIMES:
            anime_id = _upsert_anime(session, seed)
            _upsert_bangumi(session, seed, anime_id)
            _upsert_jikan(session, seed, anime_id)
            _upsert_moegirl(session, seed, anime_id)
            anime_ids.append(anime_id)

        _seed_user_interactions(session, anime_ids)
        session.commit()
        counts = _count_rows(session)

    return {
        "ok": True,
        "database": "watchthisanime.db",
        "demo_user": DEMO_USER_ID,
        "rows": counts,
        "message": "演示数据已就绪；重复运行会更新固定记录，不会重复插入。",
    }


def main() -> None:
    """命令行入口。"""
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(seed_demo_data(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
