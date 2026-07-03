# WatchThisAnime MCP

基于 Bangumi、萌娘百科、Jikan 等多源番剧数据的推荐 MCP 服务器。项目当前处于基础设施已成型、核心推荐/搜索服务待补全阶段。

## 当前状态

- 已有 MCP 服务器入口、tools/prompts 注册骨架、SQLite + SQLAlchemy 模型、统一 HTTP client。
- 已实现 Bangumi、萌娘百科、Jikan 的 source client，并配有 mock 单测与默认跳过的 live 测试。
- `recommend_anime`、`record_user_interaction`、`search_anime`、`recent_anime` 目前主要还是工具骨架，业务逻辑需要继续下沉到 `services/`。
- GitHub 数据集同步、推荐服务、搜索服务、交互记录服务尚未完成。

## 快速开始

```bash
pixi run serve      # 启动 MCP 服务器
pixi run inspect    # 启动 MCP Inspector，本地调试用
pixi run lint       # ruff check src/
pixi run pytest     # 运行默认测试，live 网络测试会跳过
pixi run code       # 在 VSCode 中打开项目
```

其他命令：

```bash
pixi run clean-db   # 删除本地 watchthisanime.db
```

> `pixi.toml` 当前尚未定义 `sync` 任务。GitHub 数据集同步完成后再补 `pixi run sync`。

## MCP 工具状态

| Tool | 状态 | 说明 |
|---|---|---|
| `recommend_anime(user_id)` | 骨架 | 已创建用户记录，推荐编排未实现 |
| `record_user_interaction(user_id, anime_id, action, rating)` | 骨架 | 已创建用户记录，交互入库未实现 |
| `search_anime(anime_name, anime_tag)` | 骨架 | 名称与标签搜索未实现 |
| `recent_anime(user_id)` | 占位 | 本期可保持空结果，后续补真实逻辑 |

## 文档入口

- [AGENTS.md](./AGENTS.md)：Codex 和其他 AI 编程助手的主入口，包含分层边界、开发规则和真实网络测试要求。
- [AI_NEXT_STEPS.md](./AI_NEXT_STEPS.md)：当前最适合 AI 接手的轻量任务索引。
- [IMPROVEMENT_ANALYSIS.md](./IMPROVEMENT_ANALYSIS.md)：阶段性进度与改进分析，适合需要全局背景时阅读。

## 开发约定

- 包管理器使用 Pixi，不直接使用 `pip install`。
- Python 版本由 `pixi.toml` 约束为 `>=3.14.5,<3.15`。
- 默认测试命令是 `pixi run pytest`。
- 新增或修改外部 API 请求路径时，必须按 `AGENTS.md` 补 live 测试，并用 `RUN_LIVE=1` 本地实跑对应用例。
- 业务逻辑放在 `services/`，MCP tool 层只做参数校验、错误转译和转发。
