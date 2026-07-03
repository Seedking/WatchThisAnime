"""Inspect Moegirl REST page JSON for one page key."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from src.services.search_service import (
    _extract_moegirl_aliases,
    _extract_moegirl_categories,
    _extract_moegirl_summary,
)
from src.sources.moegirl_client import MoegirlClient


def analyze_page_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compact field summary for a Moegirl page payload."""
    source = str(payload.get("source") or "")
    return {
        "id": payload.get("id"),
        "key": payload.get("key"),
        "title": payload.get("title"),
        "fields": sorted(payload.keys()),
        "has_source": bool(source),
        "has_stable_rating": False,
        "content_model": payload.get("content_model"),
        "latest": payload.get("latest"),
        "categories": _extract_moegirl_categories(source),
        "aliases": _extract_moegirl_aliases(source),
        "summary_candidate": _extract_moegirl_summary(source),
    }


async def fetch_and_analyze(key: str) -> dict[str, Any]:
    """Fetch one page and analyze its REST JSON structure."""
    async with MoegirlClient() as client:
        page = await client.get_page(key=key)
    payload = {
        "id": page.id,
        "key": page.key,
        "title": page.title,
        "latest": (
            None
            if page.latest is None
            else {"id": page.latest.id, "timestamp": page.latest.timestamp}
        ),
        "content_model": page.content_model,
        "license": (
            None
            if page.license is None
            else {"url": page.license.url, "title": page.license.title}
        ),
        "html_url": page.html_url,
        "source": page.source,
        "url": page.url,
    }
    return analyze_page_payload(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one Moegirl REST page.")
    parser.add_argument("key", help="Moegirl page key/title")
    args = parser.parse_args()
    result = asyncio.run(fetch_and_analyze(args.key))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
