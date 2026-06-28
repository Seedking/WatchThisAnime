"""入口：以 streamable-http 传输启动 MCP 服务器。

导入 ``tools`` / ``prompts`` 包以触发各 ``@mcp.tool()`` / ``@mcp.prompt()``
装饰器完成注册，随后运行服务器。
"""

from src.mcp import prompts, tools  # noqa: F401  注册工具与提示
from src.mcp.server import mcp
from src.storage.database import init_db


def main() -> None:
    # 启动时建表，确保 schema 先于服务对外（init_db 内部会导入 models 触发注册）。
    init_db()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
