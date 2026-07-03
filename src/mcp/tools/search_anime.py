"""search_anime tool."""

import json

from src.mcp.server import mcp
from src.services.search_service import SearchError, search_anime as search_anime_service


@mcp.tool()
def search_anime(anime_name: str, anime_tag: list[str] | None = None) -> str:
    """Search anime across Bangumi, Jikan, and Moegirl."""
    try:
        payload = search_anime_service(anime_name, anime_tag)
    except SearchError as exc:
        payload = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    return json.dumps(payload, ensure_ascii=False)
