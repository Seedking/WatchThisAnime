# WatchThisAnime MCP

基于 Bangumi、萌娘百科、Jikan 等多源番剧数据的推荐 MCP 服务器。它可以把搜索结果合并写入本地 SQLite，也可以记录用户看过、想看和标签偏好，为后续推荐提供数据基础。

## 5 分钟体验

```bash
# 写入 6 部演示番剧、三个来源记录和 demo-user 交互数据
pixi run demo

# 启动 MCP 服务器
pixi run serve
```

另开终端启动 MCP Inspector，即可查看并调用工具：

```bash
pixi run inspect
```

Inspector 中连接 `http://127.0.0.1:8000/mcp` 即可访问当前服务器。

演示脚本完全离线，重复执行不会产生重复番剧或来源记录。生成的本地数据库为 `watchthisanime.db`。

## MCP 工具

| Tool | 当前能力 |
|---|---|
| `search_anime(anime_name, anime_tag)` | 可用。优先查本地库；未命中时实时搜索 Bangumi、萌娘百科和 Jikan，按标题与标签筛选，并把来源记录合并写入本地库。联网搜索时单个来源失败会返回 warning。 |
| `record_user_interaction(user_id, target_type, target_id, rating, action)` | 可用。记录 `anime` 的 `viewed` / `wishlisted` 历史，或按 `tag` 新增/更新 1-10 偏好分。 |
| `recommend_anime(user_id)` | 可用。交互少于 3 部时按来源评分冷启动；达到阈值后结合标签偏好与历史评分排序，并排除已看条目。 |
| `recent_anime(user_id)` | 可用。返回用户最近交互过的番剧，重复交互按番剧去重并保留最新动作。 |

建议调用侧始终显式传入 `user_id`。服务端不做鉴权，`demo-user` 只是演示数据的固定标识。

## 常用命令

```bash
pixi run demo       # 写入离线演示数据
pixi run serve      # 以 streamable-http 启动 MCP 服务器
pixi run inspect    # 启动 MCP Inspector
pixi run lint       # ruff check src/
pixi run pytest     # 离线测试；live 网络测试默认跳过
pixi run clean-db   # 删除本地 watchthisanime.db
```

## 测试

默认测试无需网络：

```bash
pixi run pytest
```

外部 API 的 live 测试通过 `RUN_LIVE=1` 启用。PowerShell 示例：

```powershell
$env:RUN_LIVE=1
pixi run pytest tests/test_sources/test_bangumi_client.py -k live
```

新增或修改 Bangumi、萌娘百科、Jikan 的请求路径、参数或前缀时，必须同步补 live 测试并实跑对应用例。

## 项目结构

```text
src/
├── mcp/          # MCP server、tools 与 prompt 注册
├── services/     # 搜索、推荐、交互记录、用户等业务编排
├── sources/      # Bangumi、萌娘百科、Jikan client
├── storage/      # SQLAlchemy engine、session 与 ORM 模型
└── utils/        # HTTP client 等通用能力
scripts/
└── seed_demo.py  # 离线演示数据入口
tests/            # 单元测试与默认跳过的 live 测试
```

## 数据边界

- 依赖方向固定为 `mcp/ -> services/ -> sources/ 或 storage/ -> utils/`。
- MCP tool 只负责协议注册、参数校验、错误转译和调用 service。
- `sources/` 只请求和解析外部数据，不写数据库；搜索结果入库由 `services/` 编排。
- 本地数据保存在 SQLite；当前尚未接入 GitHub 数据集自动同步。

更完整的开发规则见 [AGENTS.md](./AGENTS.md)。
