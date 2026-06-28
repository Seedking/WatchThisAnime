"""SQLAlchemy 引擎与 session 管理。

提供所有 ORM 模型的声明式基类 ``Base``、模块级 ``engine`` 与 ``SessionLocal``
session factory，以及 ``init_db`` / ``get_session`` 两个入口：

- ``init_db``：建表（``Base.metadata.create_all``），供服务器启动阶段调用；
- ``get_session``：session 生成器，供后续 FastMCP 依赖注入使用。

当前使用硬编码的 SQLite 连接串（最小实现），后续如需从环境变量覆盖，可再引入
``pydantic-settings`` 升级。
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 硬编码 SQLite 数据库路径（最小实现）。
_DATABASE_URL: str = "sqlite:///watchthisanime.db"


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


engine = create_engine(
    _DATABASE_URL,
    connect_args={"check_same_thread": False},  # streamable-http 异步上下文复用连接
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """创建所有已注册模型对应的表。

    在函数内部导入 ``models`` 以触发模型注册，避免与 ``models.py`` 形成顶层循环导入。
    """
    from src.storage import models  # noqa: F401  触发模型注册

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """yield 一个 session，用毕关闭。

    供后续 FastMCP 依赖注入使用，例如::

        @mcp.tool()
        def some_tool(session: Session = Depends(get_session)) -> ...:
            ...
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
