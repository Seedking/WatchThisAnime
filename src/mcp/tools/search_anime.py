"""search_anime 工具：番剧模糊搜索。"""

from src.mcp.server import mcp


@mcp.tool()
def search_anime(anime_name: str, anime_tag: list[str] | None = None) -> str:
    """按名称与标签模糊搜索番剧。

    只读、无需鉴权。``anime_name`` 跨主表 ``canonical_title`` / ``title_jp`` /
    ``title_zh`` 模糊匹配；``anime_tag`` 按来源记录表 ``tags`` 筛选，与名称为 AND
    关系（空数组则仅按名称）。返回匹配番剧列表。
    """
    return ""
