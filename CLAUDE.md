# WatchThisAnime

基于多源（Bangumi / 萌娘百科 / Jikan）番剧数据的推荐 MCP 服务器。

## 快速命令

```bash
pixi run serve      # 启动 MCP 服务器（python -m src）
pixi run lint       # ruff 代码检查（ruff check src/）
pixi run sync       # 手动触发 GitHub 数据集同步（待添加到 pixi.toml）
pixi run inspect    # MCP Inspector 调试（仅限本地开发使用）
pixi run code       # 在 VSCode 中打开项目
pixi run test       # 运行测试（pytest）
```

> **注意**：`pixi run inspect` 设置了 `DANGEROUSLY_OMIT_AUTH=true`，仅限本地交互式调试使用，不得用于生产环境。

## 当前项目结构

```
.
├── pixi.toml           # Pixi 项目配置，Python >=3.14.5, <3.15
├── pixi.lock           # 依赖锁定文件
├── .gitignore
├── .vscode/
│   ├── launch.json     # Debug 配置（debugpy + pixi 解释器）
│   └── settings.json   # Python 解释器指向 .pixi/envs/default/python.exe
└── .pixi/              # Pixi 虚拟环境（gitignore 忽略）
```

> **当前状态**：`src/` 和 `tests/` 目录尚不存在，项目正在初始化阶段。

## 目标架构（蓝图）

以下目录和模块尚未创建，是计划中的实现目标。项目划分为五个功能部分：

1. **MCP 交互层（`mcp/`）** —— 与 agent 交互的协议层，暴露 tools / prompts / resources。
2. **业务服务层（`services/`）** —— MCP 调用的实现/入口函数合集，承载推荐编排等子函数。
3. **持久化层（`storage/`）** —— SQLite 数据结构与 session 管理。
4. **数据源层（`sources/`）** —— 获取 GitHub 上事先整理好的数据集，以及对接 Bangumi / 萌娘百科 / Jikan。
5. **工具层（`utils/`）** —— `base_api_client` 集中处理 HTTP 请求。

```
src/
├── __main__.py                     # 入口：mcp.run(transport="streamable-http")
├── mcp/                            # [1] MCP 交互层
│   ├── __init__.py
│   ├── server.py                   # FastMCP 实例 + JWT 鉴权中间件（解析 Bearer token）
│   ├── auth.py                     # JWT 解析：Authorization: Bearer <JWT> → user_id (sub)
│   ├── tools/__init__.py           # 统一注册点：recommend_anime, record_user_interaction, recent_anime, search_anime
│   ├── prompts/__init__.py         # 含 recommend prompt（指导 LLM 使用推荐工具）
│   └── resources/__init__.py
├── services/                       # [2] 业务服务层（入口函数合集）
│   ├── __init__.py
│   ├── recommend_service.py        # 聚合 recommend_anime 的编排 + 冷启动/个性化子函数
│   ├── interaction_service.py      # record_user_interaction 实现：JWT 上下文取 user_id，写 anime_interactions
│   └── search_service.py           # search_anime 实现：按名称 + 标签模糊搜索
├── sources/                        # [4] 数据源层
│   ├── __init__.py
│   ├── github_dataset_client.py    # GitHub 预整理数据集：启动同步 + 定时同步
│   ├── bangumi_client.py           # Bangumi API 封装
│   ├── moegirl_client.py           # 萌娘百科 API 封装
│   └── jikan_client.py             # Jikan (MyAnimeList) API 封装
├── storage/                        # [3] 持久化层
│   ├── __init__.py
│   ├── database.py                 # SQLAlchemy 引擎和 session 管理
│   └── models.py                   # anime 主表(UUID PK) + 三张来源记录表 + user + anime_interactions + tag_interactions
└── utils/                          # [5] 工具层
    ├── __init__.py
    └── base_api_client.py          # BaseAPIClient 抽象基类
tests/
├── __init__.py
├── conftest.py                     # pytest 共享 fixtures
├── test_mcp/                       # MCP 层测试
├── test_services/                  # 业务服务层测试
├── test_sources/                   # 数据源层测试
└── test_storage/                   # 持久化层测试
```

## 架构要点

- **分层依赖**：`mcp/`（协议层）→ `services/`（业务服务层）→ `sources/`（数据源层）/ `storage/`（持久化层）→ `utils/`（工具层）。上层依赖下层，禁止跨层或反向依赖。
- **鉴权与用户解析**：streamable-http 连接建立时，服务端读取 `Authorization: Bearer <JWT>` 头 → 校验并解码 JWT → 取 `sub` 声明作为 `user.id`（UUID）→ 在 `user` 表中 upsert（首次见到则创建）→ 将 `user_id` 注入工具调用上下文。`recommend_anime` 与 `record_user_interaction` 均从上下文取 `user_id`，**不接收 `user_id` 参数**。`user.username` 取 JWT claims 中的可读名（如 `name` / `preferred_username`），缺失则回落到 `sub`。不把整个 JWT 字符串作主键（JWT 带 `exp` 会刷新，作主键会导致身份漂移、历史断链）。
- **MCP 交互层**：所有 tools / prompts / resources 在 `src/mcp/tools/__init__.py` 等统一 import 并注册到 server 实例。tool 函数仅做参数校验与转发，业务逻辑下沉到 `services/`。
- **业务服务层**：`recommend_service.py` 承载 `recommend_anime` 的两阶段编排及其子函数；`interaction_service.py` 承载 `record_user_interaction` 的实现。
- **`recommend_anime` 两阶段**：
  - **冷启动阶段**：用户无足够交互历史时，基于 GitHub 数据集中的热度 / 标签 / 类型元数据生成推荐，不依赖个人画像。
  - **个性化阶段**：用户交互记录达到阈值后，基于 `anime_interactions`（行为 + 评分）与 `tag_interactions`（标签偏好）中的信号召回与排序。
  - 服务层按用户历史量自动选择阶段，对外仍是单一 `recommend_anime` 工具。
- **多表数据模型**：`anime` 主表使用 **UUID 主键** + 跨来源共享字段；每个来源（Bangumi / 萌娘百科 / Jikan）各有一张独立记录表，通过外键关联主表，来源 ID 在各自表内唯一（详见「数据模型」）。来源记录可后于主表存在，运行时逐步补全。UUID 主键便于同步 GitHub 上新增的映射记录时分配稳定标识。
- **交互数据模型**：用户对番的行为与评分记录在 `anime_interactions`（含 `action` + `rating`），用户对标签/题材的偏好打分记录在 `tag_interactions`，两表解耦；`action` 保留用于用户状态分析，个性化阶段可同时利用两表。
- **GitHub 数据集同步**：通过 `sources/github_dataset_client.py` 完成，服务器启动时执行首次同步（拉取 → 解析 → upsert 入库），并提供定时同步任务；同步只负责写 `anime` 主表与对应来源记录表。
- **HTTP 客户端**：通过 `utils/base_api_client.py` 的 `BaseAPIClient` 抽象基类封装 httpx，子类（bangumi / moegirl / jikan / github_dataset client）只需定义 `base_url` 和 `default_headers`，内置统一超时和重试机制。
- **数据库**：SQLAlchemy 2.0 style + SQLite，通过 session factory 管理数据库会话。
- **依赖注入**：在初始化阶段注入客户端和数据库实例，避免在 tool / service 函数内部直接创建依赖。

## 数据模型

- `anime(id PK UUID, canonical_title, title_jp, title_zh, airing_date, season)` —— 跨来源共享的中性元数据；UUID 由 GitHub 数据集同步时分配，保证稳定。
- `bangumi_records(source_id UNIQUE, anime_id FK→anime.id(UUID), score, tags, cover, url, raw, updated_at)` —— Bangumi 来源专属字段。
- `moegirl_records(source_id UNIQUE, anime_id FK→anime.id(UUID), ...)` —— 萌娘百科来源专属字段，结构与上同构。
- `jikan_records(source_id UNIQUE, anime_id FK→anime.id(UUID), ...)` —— Jikan 来源专属字段，结构与上同构。
- `user(id PK UUID = JWT sub, username, created_at, updated_at)` —— 由 JWT 解析自动 upsert；`username` 取 claims 可读名，缺失回落 `sub`。
- `anime_interactions(id PK, user_id FK→user.id, anime_id FK→anime.id, action, rating, created_at)` —— `record_user_interaction` 写入此表，作用户对番的评分历史；`action ∈ {viewed, wishlisted}`（本期仅这两种），`rating` 整数 1-10 可空（`viewed`/`wishlisted` 未必伴随打分）。
- `tag_interactions(id PK, user_id FK→user.id, tag, score 1-10, updated_at, UNIQUE(user_id, tag))` —— 用户对标签/题材的独立打分，与具体番剧解耦；录入入口计划中，待后续补充。

> 一部 `anime` 可对应 0~3 条来源记录。GitHub 数据集通常只带部分来源 ID，写入时先 upsert 主表再 upsert 对应来源表。

## 工具契约

- `recommend_anime(...)`：聚合推荐工具，`user_id` 从 JWT 上下文取。内部按用户交互历史量判定阶段 → 调用冷启动或个性化子函数 → 返回聚合推荐列表。函数文档字符串作为 MCP 工具描述。
- `record_user_interaction(anime_id, action, rating)`：用户行为反馈工具，`user_id` 从 JWT 上下文取。`anime_id` 为 `anime` 表 UUID 主键；`action ∈ {viewed, wishlisted}`；`rating` 整数 1-10 可空。写入 `anime_interactions`，为后续个性化推荐积累信号。
- `search_anime(anime_name, anime_tag)`：模糊搜索工具，只读、无需鉴权。`anime_name` 跨主表 `canonical_title` / `title_jp` / `title_zh` 模糊匹配；`anime_tag`（字符串数组）按来源记录表 `tags` 筛选，与名称为 AND 关系（空数组则仅按名称）；返回匹配番剧列表（含 `anime.id` UUID 与命中来源摘要）。
- `recent_anime()`：最近动漫推荐工具，`user_id` 从 JWT 上下文取，不接收参数。返回最近番剧的推荐列表（本期为占位，返回空字符串）。

## Prompt 契约

- **Prompt `recommend`**：用 `@mcp.prompt()` 定义，输出一段说明指导 LLM 如何使用推荐工具集——何时调用 `recommend_anime`、如何用 `record_user_interaction` 反馈、冷启动与个性化两阶段的区别等。

## 代码规范

- **类型注解**：所有函数参数和返回值必须带有类型注解
- **导入顺序**：标准库 → 第三方库 → 本地模块，各段之间空行分隔
- **命名约定**：模块名和函数名使用 `snake_case`，类名使用 `PascalCase`，常量使用 `UPPER_CASE`
- **错误处理**：使用自定义异常层次结构，不暴露原始 HTTP 错误给 MCP 客户端
- **ruff 检查**：提交前运行 `pixi run lint`，确保无错误通过
- **测试**：使用 pytest，测试文件放在 `tests/` 目录，与被测模块路径对应

## 开发环境

- **包管理器**：[Pixi](https://pixi.sh)（conda-forge 频道），**不要**使用 `pip install` 直接安装依赖
- **Python 版本**：3.14.5 - 3.15（由 `pixi.toml` 约束）
- **添加依赖**：`pixi add <package>`，之后提交更新的 `pixi.toml` 和 `pixi.lock`
- **VSCode 调试**：使用 `.vscode/launch.json` 中的 "Debug Python with pixi" 配置（debugpy + pixi 解释器）
- **解释器路径**：`.pixi/envs/default/python.exe`（已在 `.vscode/settings.json` 中配置）
- **工作目录**：`F:\GitRepo\WatchThisAnime`

## MCP 约定

- **Tool 装饰器**：所有工具使用 `@mcp.tool()` 装饰器，函数的文档字符串作为工具的描述
- **Prompt 装饰器**：使用 `@mcp.prompt()` 装饰器定义提示模板
- **Resource 装饰器**：使用 `@mcp.resource()` 装饰器暴露数据资源
- **传输方式**：使用 Streamable HTTP，入口为 `mcp.run(transport="streamable-http")`
- **鉴权**：streamable-http 连接通过 `Authorization: Bearer <JWT>` 鉴权并解析用户身份（`sub` → `user.id`），详见「架构要点 → 鉴权与用户解析」
- **调试**：使用 `pixi run inspect` 启动 MCP Inspector 进行交互式调试
